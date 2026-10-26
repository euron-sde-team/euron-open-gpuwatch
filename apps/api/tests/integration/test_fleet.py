"""Enrolment, hosts, GPUs and the ingest contract."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.integration.conftest import Api, batch, gpu, now, process, sample

pytestmark = pytest.mark.integration


async def _enrol(api: Api, token: str, machine: str = "m-000000001") -> int:
    async with api.anonymous() as c:
        r = await c.post(
            "/ingest/v1/enroll", json={"token": token, "machine_id": machine, "hostname": "h"}
        )
    return r.status_code


async def test_enrolment_tokens_are_shown_once_and_enforce_limits(api: Api) -> None:
    created = await api.ok(
        "POST",
        "/api/v1/enrolment-tokens",
        {"name": "fleet", "max_uses": 2, "labels": {"env": "prod"}},
    )
    assert created["token"].startswith("gwe_") and created["usable"]
    listed = await api.ok("GET", "/api/v1/enrolment-tokens")
    assert "token" not in listed[0] and listed[0]["display"].endswith("_****")
    assert await _enrol(api, created["token"], "machine-aaaa1") == 201
    assert await _enrol(api, created["token"], "machine-aaaa2") == 201
    assert await _enrol(api, created["token"], "machine-aaaa3") == 401  # max uses reached
    hosts = await api.ok("GET", "/api/v1/hosts")
    assert all(h["labels"]["env"] == "prod" for h in hosts) and all(
        h["status"] == "pending" for h in hosts
    )
    other = await api.ok("POST", "/api/v1/enrolment-tokens", {"name": "revoked"})
    await api.ok("POST", f"/api/v1/enrolment-tokens/{other['id']}/revoke")
    assert await _enrol(api, other["token"]) == 401
    assert await _enrol(api, "gwe_nothex000000_x") == 401
    assert await _enrol(api, "not-a-token-at-all") == 401


async def test_expired_tokens_are_refused(api: Api) -> None:
    created = await api.ok("POST", "/api/v1/enrolment-tokens", {"name": "old"})
    await api.sql("UPDATE enrolment_tokens SET expires_at = now() - interval '1 minute'")
    assert await _enrol(api, created["token"]) == 401


async def test_re_enrolling_a_machine_keeps_its_host_and_rotates_the_token(api: Api) -> None:
    first = await api.host(machine="stable-machine-1")
    u = first.uuids[0]
    await first.ok(batch([gpu(u)], [sample(u, now())]))
    second = await api.host(machine="stable-machine-1")
    assert second.host_id == first.host_id
    r = await first.send(batch([gpu(u)], [sample(u, now() + timedelta(seconds=1))]))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_host_token"
    await second.ok(batch([gpu(u)], [sample(u, now() + timedelta(seconds=2))]))
    assert len(await api.ok("GET", "/api/v1/hosts")) == 1


async def test_a_batch_updates_the_host_and_inventory(api: Api) -> None:
    host = await api.host(hostname="node-a", labels={"rack": "r1"})
    u0, u1 = f"GPU-{host.host_id[:8]}-0", f"GPU-{host.host_id[:8]}-1"
    reply = await host.ok(
        batch(
            [gpu(u0, 0), gpu(u1, 1, name="NVIDIA L4", mem=23034.0)],
            [sample(u0, now()), sample(u1, now())],
            [process(u0, now(), 11, "python3", mem_used_mib=1000.0)],
            hostname="node-a",
        )
    )
    assert reply == {
        "accepted": True,
        "duplicate": False,
        "samples": 2,
        "processes": 1,
        "inference": 0,
        "dropped": 0,
        "next_in_s": 5.0,
    }
    h = await api.ok("GET", f"/api/v1/hosts/{host.host_id}")
    assert h["status"] == "online" and h["gpu_count"] == 2 and h["driver_version"] == "550.127.05"
    assert h["labels"] == {"rack": "r1"}
    gpus = await api.ok("GET", f"/api/v1/gpus?host_id={host.host_id}")
    assert [g["name"] for g in gpus] == ["NVIDIA A100-SXM4-80GB", "NVIDIA L4"]
    assert gpus[1]["memory_total_mib"] == 23034.0


async def test_samples_outside_the_time_window_are_dropped(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    reply = await host.ok(
        batch(
            [gpu(u)],
            [
                sample(u, now() - timedelta(days=8)),
                sample(u, now() + timedelta(hours=1)),
                sample(u, now()),
            ],
        )
    )
    assert reply["samples"] == 1 and reply["dropped"] == 2


async def test_simulated_hosts_may_backfill_history(api: Api) -> None:
    host = await api.host(simulated=True)
    u = host.uuids[0]
    reply = await host.ok(batch([gpu(u)], [sample(u, now() - timedelta(days=20), interval=60)]))
    assert reply["samples"] == 1
    assert (await api.ok("GET", "/api/v1/hosts"))[0]["simulated"] is True


async def test_a_gpu_that_moves_hosts_follows_its_uuid(api: Api) -> None:
    a = await api.host(hostname="a")
    b = await api.host(hostname="b")
    u = "GPU-moved-0001"
    await a.ok(batch([gpu(u)], [sample(u, now())], hostname="a"))
    await b.ok(batch([gpu(u)], [sample(u, now() + timedelta(seconds=1))], hostname="b"))
    gpus = await api.ok("GET", "/api/v1/gpus")
    assert len(gpus) == 1 and gpus[0]["host_id"] == b.host_id


async def test_hosts_can_be_renamed_relabelled_and_revoked(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    await host.ok(batch([gpu(u)], [sample(u, now())]))
    edited = await api.ok(
        "PATCH",
        f"/api/v1/hosts/{host.host_id}",
        {"display_name": "Trainer 1", "labels": {"team": "ml"}},
    )
    assert edited["name"] == "Trainer 1" and edited["labels"] == {"team": "ml"}
    revoked = await api.ok("POST", f"/api/v1/hosts/{host.host_id}/revoke")
    assert revoked["status"] == "revoked"
    r = await host.send(batch([gpu(u)], [sample(u, now() + timedelta(seconds=1))]))
    assert r.status_code == 401 and r.json()["error"]["code"] == "host_revoked"
    # Its GPUs leave the fleet (live view, overview) but stay on the host's own page.
    gid = await api.gpu_id(u)
    assert gid not in [g["id"] for g in await api.ok("GET", "/api/v1/live")]
    assert gid not in [g["id"] for g in await api.ok("GET", "/api/v1/gpus")]
    assert (await api.ok("GET", "/api/v1/overview"))["gpus_total"] == 0
    on_host = await api.ok("GET", f"/api/v1/gpus?host_id={host.host_id}")
    assert [g["id"] for g in on_host] == [gid]


async def test_gpus_can_be_retired_and_come_back_when_they_report(api: Api) -> None:
    host = await api.host()
    u = host.uuids[0]
    await host.ok(batch([gpu(u)], [sample(u, now())]))
    gid = await api.gpu_id(u)
    retired = await api.ok("PATCH", f"/api/v1/gpus/{gid}", {"retired": True})
    assert retired["status"] == "retired"
    assert await api.ok("GET", "/api/v1/gpus") == []
    await host.ok(batch([gpu(u)], [sample(u, now() + timedelta(seconds=1))]))
    assert (await api.ok("GET", f"/api/v1/gpus/{gid}"))["status"] == "ok"


async def test_unknown_resources_are_404(api: Api) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    for path in (
        f"/api/v1/hosts/{missing}",
        f"/api/v1/gpus/{missing}",
        f"/api/v1/gpus/{missing}/metrics",
        f"/api/v1/gpus/{missing}/processes",
        f"/api/v1/gpus/{missing}/explain",
    ):
        assert (await api.client.get(path)).status_code == 404, path


async def test_missing_or_malformed_host_tokens_are_refused(api: Api) -> None:
    async with api.anonymous() as c:
        for headers in (
            {},
            {"authorization": "Bearer gwk_000000000000_x"},
            {"authorization": "Bearer gwh_000000000000_x"},
        ):
            r = await c.post("/ingest/v1/batches", json=batch([], []), headers=headers)
            assert r.status_code == 401


async def test_a_revoked_machine_stays_revoked_until_an_admin_issues_a_new_token(
    api: Api,
) -> None:
    # The agent keeps the enrolment token it started with; revoking must still stick.
    old = await api.enrolment_token()
    host = await api.host(machine="machine-revoked-1")
    await api.ok("POST", f"/api/v1/hosts/{host.host_id}/revoke")
    enrol = {"machine_id": "machine-revoked-1", "hostname": "gpu-node-1"}
    async with api.anonymous() as agent:
        r = await agent.post("/ingest/v1/enroll", json={"token": old, **enrol})
        assert r.status_code == 401 and r.json()["error"]["code"] == "host_revoked"
        assert (await api.ok("GET", f"/api/v1/hosts/{host.host_id}"))["status"] == "revoked"

        fresh = await api.enrolment_token()
        r = await agent.post("/ingest/v1/enroll", json={"token": fresh, **enrol})
        assert r.status_code == 201 and r.json()["host_id"] == host.host_id
