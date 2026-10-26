"""``make bench``: ingest and dashboard latency against the running stack.

Enrols throwaway hosts (machine ids ``bench-*``, revoked afterwards), then measures:

* ingest latency: one agent sending batches of 8 GPUs with 3 processes each, one at a time;
* ingest throughput: several agents sending at once;
* dashboard reads: the live snapshot, the overview and a 24-hour GPU history.

Numbers are wall-clock from this machine through the published API port, so they include
HTTP and JSON on both sides. Run it on a quiet machine; the README quotes one run.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

API = os.environ.get("GPUWATCH_API_URL", "http://localhost:4430")
EMAIL = os.environ.get("DEMO_EMAIL", "owner@gpuwatch.local")
PASSWORD = os.environ.get("DEMO_PASSWORD", "")
GPUS = 8
PROCS = 3


def _batch(prefix: str, ts: datetime) -> dict[str, Any]:
    gpus = [
        {
            "uuid": f"GPU-{prefix}-{i}",
            "index": i,
            "name": "NVIDIA H100 80GB HBM3",
            "memory_total_mib": 81559,
        }
        for i in range(GPUS)
    ]
    samples = [
        {
            "gpu_uuid": g["uuid"],
            "ts": ts.isoformat(),
            "interval_s": 5,
            "util_gpu": 90.0,
            "util_mem": 55.0,
            "mem_used_mib": 70000.0,
            "mem_total_mib": 81559.0,
            "temp_c": 70.0,
            "power_w": 600.0,
            "power_limit_w": 700.0,
            "sm_clock_mhz": 1980.0,
            "throttle_reasons": 0,
            "procs": PROCS,
        }
        for g in gpus
    ]
    procs = [
        {
            "gpu_uuid": g["uuid"],
            "ts": ts.isoformat(),
            "pid": 1000 + p,
            "name": "python3",
            "mem_used_mib": 20000.0,
            "sm_util": 30.0,
        }
        for g in gpus
        for p in range(PROCS)
    ]
    return {
        "batch_id": str(uuid.uuid4()),
        "agent": {
            "version": "bench",
            "collector": "nvml",
            "hostname": f"bench-{prefix}",
            "interval_s": 5,
        },
        "gpus": gpus,
        "samples": samples,
        "processes": procs,
    }


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _report(name: str, ms: list[float]) -> None:
    print(
        f"  {name:<34} p50 {statistics.median(ms):6.1f} ms   p95 {_pct(ms, 0.95):6.1f} ms   "
        f"({len(ms)} requests)"
    )


async def main() -> None:
    if not PASSWORD:
        raise SystemExit("set DEMO_PASSWORD (make bench reads it from deploy/compose/.env)")
    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        r = await c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        auth = {"authorization": f"Bearer {r.json()['session_token']}"}
        token = (
            await c.post(
                "/api/v1/enrolment-tokens",
                json={"name": "make bench", "labels": {"purpose": "bench"}, "expires_in_days": 1},
                headers=auth,
            )
        ).json()["token"]
        hosts = []
        for i in range(8):
            e = await c.post(
                "/ingest/v1/enroll",
                json={
                    "token": token,
                    "machine_id": f"bench-{uuid.uuid4().hex[:12]}",
                    "hostname": f"bench-{i}",
                },
            )
            hosts.append(e.json())
        try:
            print(f"GPUWatch bench against {API}: batches of {GPUS} GPUs x {PROCS} processes\n")
            first = hosts[0]
            h_auth = {"authorization": f"Bearer {first['host_token']}"}
            t0 = datetime.now(UTC) - timedelta(minutes=30)
            lat: list[float] = []
            for n in range(200):
                body = _batch("seq", t0 + timedelta(seconds=5 * n))
                s = time.perf_counter()
                resp = await c.post("/ingest/v1/batches", json=body, headers=h_auth)
                lat.append((time.perf_counter() - s) * 1000)
                resp.raise_for_status()
            _report("ingest, one agent", lat)

            async def agent(h: dict[str, Any], k: int, n: int) -> None:
                headers = {"authorization": f"Bearer {h['host_token']}"}
                for j in range(n):
                    body = _batch(f"par{k}", t0 + timedelta(seconds=5 * j))
                    (
                        await c.post("/ingest/v1/batches", json=body, headers=headers)
                    ).raise_for_status()

            per = 50
            s = time.perf_counter()
            await asyncio.gather(*(agent(h, k, per) for k, h in enumerate(hosts[1:])))
            elapsed = time.perf_counter() - s
            batches = per * (len(hosts) - 1)
            print(
                f"  {'ingest, 7 agents at once':<34} {batches / elapsed:6.0f} batches/s   "
                f"{batches * GPUS / elapsed:7.0f} GPU samples/s   "
                f"{batches * GPUS * (1 + PROCS) / elapsed:7.0f} rows/s"
            )
            gpus = (await c.get("/api/v1/gpus", headers=auth)).json()
            demo = next((g for g in gpus if not g["host_name"].startswith("bench-")), gpus[0])
            end = datetime.now(UTC)
            history = f"/api/v1/gpus/{demo['id']}/metrics"
            week = {"start": (end - timedelta(days=7)).isoformat(), "end": end.isoformat()}
            reads: dict[str, tuple[str, dict[str, str] | None]] = {
                "live snapshot (/api/v1/live)": ("/api/v1/live", None),
                "overview (/api/v1/overview)": ("/api/v1/overview", None),
                "GPU history, 24 h (1 min rollups)": (
                    history,
                    {"start": (end - timedelta(hours=24)).isoformat(), "end": end.isoformat()},
                ),
                "GPU history, 7 days (1 h rollups)": (history, week),
                "costs by workload, 7 days": ("/api/v1/costs", {**week, "group_by": "workload"}),
            }
            for name, (path, params) in reads.items():
                ms = []
                for _ in range(30):
                    s = time.perf_counter()
                    (await c.get(path, headers=auth, params=params)).raise_for_status()
                    ms.append((time.perf_counter() - s) * 1000)
                _report(name, ms)
        finally:
            for h in hosts:
                await c.post(f"/api/v1/hosts/{h['host_id']}/revoke", headers=auth)
            print(
                "\n  bench hosts revoked (they stay listed as revoked; make down resets the stack)"
            )


if __name__ == "__main__":
    asyncio.run(main())
