"""Print the top idle GPU spend from GPUWatch, using a read-only API key.

    GPUWATCH_API_KEY=gwk_... python idle_report.py [--url http://localhost:4430] [--days 7]

Reads GET /api/v1/costs (the exact cost split) and GET /api/v1/insights?status=open (idle
findings with their evidence). Standard library only. Money is integer nano-dollars.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

IDLE_KINDS = {"idle_loaded": "model loaded, idle", "idle_empty": "nothing running"}


def get(base: str, key: str, path: str, params: dict[str, str]) -> Any:
    if not base.startswith(("http://", "https://")):
        sys.exit("--url must start with http:// or https://")
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 scheme checked above
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        error = json.loads(exc.read() or b"{}").get("error", {})
        sys.exit(f"{exc.code} {error.get('code', '')}: {error.get('message', exc.reason)}")


def usd(nusd: int | None) -> str:
    return "n/a (no rate)" if nusd is None else f"${nusd / 1e9:,.2f}"


def main() -> None:
    p = argparse.ArgumentParser(description="Top idle GPU spend from GPUWatch")
    p.add_argument("--url", default=os.environ.get("GPUWATCH_API_URL", "http://localhost:4430"))
    p.add_argument("--key", default=os.environ.get("GPUWATCH_API_KEY"), help="gwk_ API key")
    p.add_argument("--days", type=int, default=7, help="cost window in days (default 7)")
    p.add_argument("--top", type=int, default=5, help="findings to list (default 5)")
    args = p.parse_args()
    if not args.key:
        sys.exit("set GPUWATCH_API_KEY or pass --key (create one in GPUWatch, API keys)")

    end = datetime.now(UTC)
    window = {"start": (end - timedelta(days=args.days)).isoformat(), "end": end.isoformat()}
    costs = get(args.url, args.key, "/api/v1/costs", {"group_by": "gpu", **window})
    idle, held = costs["idle_nusd"], costs["held_idle_nusd"]
    print(f"Last {args.days} days: {usd(costs['total_nusd'])} total, {usd(idle + held)} idle")
    print(f"  {usd(idle)} with nothing running, {usd(held)} with a workload holding the GPU")
    if costs["unpriced_gpu_hours"]:
        print(f"  ({costs['unpriced_gpu_hours']:.1f} GPU hours have no rate and are not counted)")

    found = get(args.url, args.key, "/api/v1/insights", {"status": "open"})
    idle_found = [i for i in found if i["kind"] in IDLE_KINDS]
    idle_found.sort(key=lambda i: -(i["est_monthly_nusd"] or i["evidence"].get("cost_nusd") or 0))
    print(f"\nTop idle findings ({len(idle_found)} open):")
    for i in idle_found[: args.top]:
        ev, where = i["evidence"], i["gpu_label"] or i["host_name"]
        line = f"- {where}: {IDLE_KINDS[i['kind']]}, {ev['idle_hours']:.1f} h"
        line += f" ({ev['share']:.0%} of monitored time), {usd(ev.get('cost_nusd'))} in the window"
        print(f"{line}, about {usd(i['est_monthly_nusd'])} a month")
    if not idle_found:
        print("- none: no GPU was idle long enough to report")


if __name__ == "__main__":
    main()
