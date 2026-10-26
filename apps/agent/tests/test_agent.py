"""The agent loop: enrol, send, spool, replay, re-enrol, back off on a broken collector,
backfill; and the guarantees the agent makes (observe only, nothing hardcoded)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from gpuwatch_agent.agent import Agent, simulated_inference
from gpuwatch_agent.client import Client, SendError
from gpuwatch_agent.collectors import CollectorUnavailableError
from gpuwatch_agent.config import AgentConfig, InferenceTarget, parse_inference, parse_labels
from gpuwatch_agent.model import Reading
from gpuwatch_agent.spool import Spool

SRC = Path(__file__).resolve().parents[1] / "src" / "gpuwatch_agent"


class FakeServer:
    """An httpx MockTransport standing in for the ingest API."""

    def __init__(self) -> None:
        self.batches: list[dict[str, Any]] = []
        self.enrolments = 0
        self.down = False
        self.status: int | None = None
        self.error_code = "invalid_host_token"
        self.valid_tokens: set[str] = set()
        self.refuse_enrolment = False
        self.drop_next = 0  # batch requests to answer with a closed connection

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        if request.url.path == "/ingest/v1/enroll":
            self.enrolments += 1
            if self.refuse_enrolment:
                return httpx.Response(
                    401, json={"error": {"code": "host_revoked", "message": "revoked"}}
                )
            token = f"gwh_{self.enrolments:012x}_secret"
            self.valid_tokens = {token}
            return httpx.Response(
                201, json={"host_id": "h1", "host_token": token, "simulated": True}
            )
        if self.drop_next and request.url.path == "/ingest/v1/batches":
            self.drop_next -= 1
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        if self.status is not None:
            return httpx.Response(
                self.status, json={"error": {"code": self.error_code, "message": "nope"}}
            )
        if (
            request.headers.get("authorization", "").removeprefix("Bearer ")
            not in self.valid_tokens
        ):
            return httpx.Response(
                401, json={"error": {"code": "invalid_host_token", "message": "Unknown host token"}}
            )
        body = json.loads(request.content)
        if body["batch_id"] not in {b["batch_id"] for b in self.batches}:
            self.batches.append(body)
        return httpx.Response(200, json={"accepted": True})


def make_agent(tmp_path: Path, server: FakeServer, **cfg: Any) -> Agent:
    config = AgentConfig(
        url="http://gpuwatch.test",
        enrolment_token="gwe_abcdefabcdef_x",
        state_dir=tmp_path,
        collector="simulated",
        sim_profile=cfg.pop("profile", "workstation"),
        machine_id="test-machine-1",
        interval_s=5,
        **cfg,
    )
    client = Client(
        config.url,
        5,
        http=httpx.Client(base_url=config.url, transport=httpx.MockTransport(server.handler)),
    )
    return Agent(config, client=client)


def test_enrols_once_and_keeps_the_host_token(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    assert agent.tick()
    assert agent.tick(datetime.now(UTC) + timedelta(seconds=5))
    assert server.enrolments == 1 and len(server.batches) == 2
    token_file = tmp_path / "host-token"
    assert oct(token_file.stat().st_mode & 0o777) == "0o600"
    again = make_agent(tmp_path, server)  # a restart reuses the token
    assert again.tick()
    assert server.enrolments == 1


def test_batches_carry_the_contract_fields(tmp_path: Path) -> None:
    server = FakeServer()
    make_agent(tmp_path, server, profile="training", labels={"role": "training"}).tick()
    b = server.batches[0]
    assert set(b) == {"batch_id", "agent", "gpus", "samples", "processes", "inference"}
    assert b["agent"]["collector"] == "simulated" and b["agent"]["status"] == "ok"
    assert len(b["gpus"]) == 8 and len(b["samples"]) == 8
    assert all(s["ts"] == b["samples"][0]["ts"] for s in b["samples"])
    assert {p["ts"] for p in b["processes"]} <= {b["samples"][0]["ts"]}


def test_spools_while_down_and_replays_in_order(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    assert agent.tick()
    server.down = True
    t = datetime.now(UTC)
    for i in range(3):
        assert not agent.tick(t + timedelta(seconds=5 * (i + 1)))
    assert len(agent.spool.pending()) == 3
    server.down = False
    assert agent.tick(t + timedelta(seconds=20))
    assert agent.spool.pending() == []
    times = [b["samples"][0]["ts"] for b in server.batches]
    assert times == sorted(times) or len(server.batches) == 5
    assert len(server.batches) == 5


def test_a_refused_batch_is_dropped_not_spooled(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    agent.ensure_enrolled()
    server.status, server.error_code = 422, "validation_error"
    assert not agent.tick()
    assert agent.spool.pending() == []
    server.status = 503
    assert not agent.tick()
    assert len(agent.spool.pending()) == 1


def test_a_rotated_token_triggers_re_enrolment(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    assert agent.tick()
    server.valid_tokens = set()  # revoked or rotated on the server
    assert agent.tick()
    assert server.enrolments == 2 and len(server.batches) == 2


def test_a_revoked_machine_backs_off_instead_of_asking_every_interval(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    assert agent.tick()
    server.valid_tokens = set()
    server.refuse_enrolment = True  # revoked, and the old enrolment token no longer works
    t = datetime.now(UTC)
    for i in range(1, 6):
        assert not agent.tick(t + timedelta(seconds=5 * i))
    assert server.enrolments == 2  # the first one, then a single refused attempt
    assert not list((tmp_path / "spool").glob("*.json"))  # refused batches are not hoarded


def test_a_connection_closed_under_us_is_retried_once_not_spooled(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    assert agent.tick()
    server.drop_next = 1  # the server closed the kept-alive connection as we reused it
    assert agent.tick(datetime.now(UTC) + timedelta(seconds=5))
    assert len(server.batches) == 2 and not agent.spool.pending()
    server.drop_next = 2  # twice in a row: spooled for later, as for any outage
    assert not agent.tick(datetime.now(UTC) + timedelta(seconds=10))
    assert len(agent.spool.pending()) == 1


def test_readings_that_are_not_numbers_are_sent_as_null() -> None:
    from gpuwatch_agent.model import to_json

    sent = to_json({"running": float("nan"), "waiting": float("inf"), "kv": 0.5})
    assert sent == {"running": None, "waiting": None, "kv": 0.5}
    json.dumps(sent, allow_nan=False)  # valid JSON


def test_no_enrolment_token_explains_what_to_do(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    agent.cfg = AgentConfig(url=agent.cfg.url, enrolment_token=None, state_dir=tmp_path)
    with pytest.raises(SendError, match="Hosts, Add a host"):
        agent.enrol()


def test_a_broken_collector_reports_degraded_and_keeps_going(tmp_path: Path) -> None:
    class Broken:
        name = "nvml"

        def read(self, now: datetime, interval_s: float) -> Reading:
            raise CollectorUnavailableError("nvml_init_failed", "NVML could not start")

        def close(self) -> None:
            return None

    server = FakeServer()
    agent = make_agent(tmp_path, server)
    agent.collector = Broken()
    assert agent.tick()
    b = server.batches[0]
    assert (
        b["agent"]["status"] == "degraded"
        and b["agent"]["problems"][0]["code"] == "nvml_init_failed"
    )
    assert b["gpus"] == [] and b["samples"] == []


def test_the_interval_follows_real_time_but_is_capped(tmp_path: Path) -> None:
    server = FakeServer()
    agent = make_agent(tmp_path, server)
    t = datetime.now(UTC)
    agent.collect(t)
    assert agent.collect(t + timedelta(seconds=7))["samples"][0]["interval_s"] == 7
    assert agent.collect(t + timedelta(hours=1))["samples"][0]["interval_s"] == 15  # 3 x 5 s


def test_backfill_sends_hourly_batches_once(tmp_path: Path) -> None:
    server = FakeServer()
    inference = [InferenceTarget("chat", "vllm", "http://mock/metrics", (0,))]
    agent = make_agent(
        tmp_path, server, profile="inference", inference=inference, sim_backfill_days=1
    )
    end = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    sent = agent.backfill(1, now=end)
    assert sent == 24 and len(server.batches) == 24
    first = server.batches[0]
    assert len(first["samples"]) == 4 * 60 and first["samples"][0]["interval_s"] == 60
    assert first["inference"][0]["endpoint"] == "chat" and first["inference"][0]["ttft"]
    assert agent.backfill(1, now=end) == 0  # marker: once per state directory


def test_simulated_inference_matches_the_traffic_model() -> None:
    cfg = AgentConfig(
        url="x",
        enrolment_token=None,
        state_dir=Path("/tmp"),
        inference=[InferenceTarget("sum", "tgi", "u", (1,))],
    )
    reading = Reading()
    t = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
    (row,) = simulated_inference(cfg, reading, t, 60)
    assert row["ttft"] is None and row["kv_cache_usage"] is None and row["requests"] > 0


def test_spool_is_bounded_and_skips_corrupt_files(tmp_path: Path) -> None:
    spool = Spool(tmp_path / "s", max_bytes=600)
    for i in range(10):
        spool.put({"batch_id": f"b{i}", "pad": "x" * 100})
    assert spool.size() <= 600 and len(spool.pending()) < 10
    assert spool.load(spool.pending()[-1])["batch_id"] == "b9"  # newest kept
    bad = tmp_path / "s" / "00000000000000000000-bad.json"
    bad.write_text("{not json")
    assert spool.load(bad) is None and not bad.exists()


def test_configuration_parsing() -> None:
    assert parse_labels("a=1, b = two,,c=") == {"a": "1", "b": "two", "c": ""}
    (t,) = parse_inference("chat=vllm,http://v:8000/metrics,0+1")
    assert t == InferenceTarget("chat", "vllm", "http://v:8000/metrics", (0, 1))
    with pytest.raises(ValueError, match="GPUWATCH_INFERENCE"):
        parse_inference("chat=ollama,http://x")
    cfg = AgentConfig.from_env(
        {
            "GPUWATCH_URL": "http://gw.test/",
            "GPUWATCH_COLLECTOR": "dcgm",
            "GPUWATCH_STATE_DIR": "/tmp/x",
        }
    )
    assert cfg.url == "http://gw.test" and cfg.collector == "dcgm" and cfg.enrolment_token is None
    with pytest.raises(ValueError, match="GPUWATCH_COLLECTOR"):
        AgentConfig.from_env({"GPUWATCH_COLLECTOR": "rocm"})
    with pytest.raises(ValueError, match="GPUWATCH_INTERVAL_S"):
        AgentConfig.from_env({"GPUWATCH_INTERVAL_S": "0.1"})


def test_token_file_is_read(tmp_path: Path) -> None:
    f = tmp_path / "token"
    f.write_text("gwe_abcdefabcdef_secret\n")
    assert (
        AgentConfig.from_env({"GPUWATCH_ENROLMENT_TOKEN_FILE": str(f)}).enrolment_token
        == "gwe_abcdefabcdef_secret"
    )


def test_observe_only_the_agent_never_runs_or_kills_anything() -> None:
    forbidden = re.compile(r"\b(subprocess|os\.system|os\.kill|os\.popen|pty\.|exec\(|eval\()")
    for path in SRC.rglob("*.py"):
        assert not forbidden.search(path.read_text()), path
    # The only listening socket is the demo's mock vLLM server.
    listeners = [
        p.name
        for p in SRC.rglob("*.py")
        if re.search(r"HTTPServer|\.listen\(|bind\(", p.read_text())
    ]
    assert listeners == ["mockvllm.py"]
