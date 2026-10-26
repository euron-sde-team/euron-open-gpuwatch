"""The agent's only connection: outbound HTTPS to the GPUWatch ingest API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from gpuwatch_agent import __version__


class SendError(Exception):
    """A batch was not accepted. ``retry`` says whether to keep it for later."""

    def __init__(self, message: str, *, retry: bool, reenrol: bool = False) -> None:
        super().__init__(message)
        self.retry = retry
        self.reenrol = reenrol


@dataclass
class Enrolment:
    host_id: str
    host_token: str
    simulated: bool


class Client:
    def __init__(self, base_url: str, timeout_s: float, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={"user-agent": f"gpuwatch-agent/{__version__}"},
        )
        self.token: str | None = None

    def enrol(
        self, enrolment_token: str, machine_id: str, hostname: str, labels: dict[str, str]
    ) -> Enrolment:
        try:
            r = self._http.post(
                "/ingest/v1/enroll",
                json={
                    "token": enrolment_token,
                    "machine_id": machine_id,
                    "hostname": hostname,
                    "labels": labels,
                },
            )
        except httpx.HTTPError as exc:
            raise SendError(f"cannot reach GPUWatch: {exc}", retry=True) from exc
        if r.status_code != 201:
            raise SendError(_message(r), retry=r.status_code >= 500)
        body = r.json()
        self.token = body["host_token"]
        return Enrolment(body["host_id"], body["host_token"], body["simulated"])

    def send(self, batch: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise SendError("not enrolled", retry=True, reenrol=True)
        r = self._post_batch(batch)
        if r.status_code == 200:
            data: dict[str, Any] = r.json()
            return data
        code = _code(r)
        if r.status_code == 401:
            # A rotated or revoked token: enrol again (and keep the batch).
            raise SendError(
                _message(r), retry=True, reenrol=code in ("invalid_host_token", "host_revoked")
            )
        # 422 and other 4xx mean this batch will never be accepted; 429 and 5xx may pass later.
        raise SendError(_message(r), retry=r.status_code == 429 or r.status_code >= 500)

    def _post_batch(self, batch: dict[str, Any]) -> httpx.Response:
        headers = {"authorization": f"Bearer {self.token}"}
        for attempt in (1, 2):
            try:
                return self._http.post("/ingest/v1/batches", json=batch, headers=headers)
            except (httpx.RemoteProtocolError, httpx.ReadError) as exc:
                # A kept-alive connection the server (or a proxy) closed just as we reused
                # it. Resending is safe: the batch id makes a duplicate a no-op.
                if attempt == 2:
                    raise SendError(f"cannot reach GPUWatch: {exc}", retry=True) from exc
            except httpx.HTTPError as exc:
                raise SendError(f"cannot reach GPUWatch: {exc}", retry=True) from exc
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._http.close()


def _code(r: httpx.Response) -> str | None:
    try:
        code = r.json()["error"]["code"]
        return str(code)
    except (ValueError, KeyError, TypeError):
        return None


def _message(r: httpx.Response) -> str:
    try:
        return f"{r.status_code} {r.json()['error']['message']}"
    except (ValueError, KeyError, TypeError):
        return f"{r.status_code} {r.text[:200]}"
