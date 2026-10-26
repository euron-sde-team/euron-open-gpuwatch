# Threat Model

The attacker's view of GPUWatch, organised by entry point. The controls are described in
[security.md](security.md); this document lists what could go wrong, what stops it, and
what is left.

## Scope and assumptions

- One deployment serves one organisation. Dashboard users are employees with one of three
  roles; admins and owners are trusted with configuration.
- GPU machines are operated by the same organisation, but any one of them may be
  compromised. A compromised machine holds its host token.
- The network between agents and the API may be hostile; production runs HTTPS only.
- The AWS account, the Postgres and Redis instances and the KMS key are trusted. A
  compromise of those is out of scope.

## Entry points

| Entry point | Who reaches it | Authentication |
| ----------- | -------------- | -------------- |
| `POST /ingest/v1/enroll` | Any network client | Enrolment token (`gwe_`) |
| `POST /ingest/v1/batches` | Agents | Host token (`gwh_`) |
| `/api/v1/*` | Browsers, scripts | Session (cookie plus CSRF header, or Bearer) or read-only API key (`gwk_`) |
| `POST /api/v1/auth/login` | Anyone | Email and password |
| `/metrics` | Prometheus | `METRICS_TOKEN` (when set) |
| `/healthz`, `/readyz`, `/docs`, `/openapi.json` | Anyone | None (no data beyond status and the public API description) |
| Worker outbound | Webhook receivers, SMTP or SES | GPUWatch signs; receivers verify |
| Agent outbound | The GPUWatch API, local DCGM and inference `/metrics` | Host token to the API |

## Threats and mitigations

STRIDE categories: Spoofing, Tampering, Repudiation, Information disclosure, Denial of
service, Elevation of privilege.

| # | Threat | STRIDE | Mitigation | Residual |
| - | ------ | ------ | ---------- | -------- |
| T1 | An attacker guesses or brute forces a dashboard password | S | Argon2, 20 attempts a minute per address, 15 minute lockout after 5 failures counted atomically, constant-time unknown-email path | Lockout can be triggered deliberately against a known email (denial of sign-in for 15 minutes) |
| T2 | A forged `X-Forwarded-For` dodges the per-address throttle | S | uvicorn trusts the header only from `FORWARDED_ALLOW_IPS` | Misconfiguring `FORWARDED_ALLOW_IPS=*` behind an untrusted proxy reopens it |
| T3 | A stolen session token keeps working after sign-out or a password change | S | `revoked_sessions` in Postgres; `session_version` bump on password, role and access changes; 12 hour expiry | A token stolen and used before sign-out works until then |
| T4 | Cross-site request forgery with the session cookie | T, E | Mutations via cookie need `X-GPUWatch-CSRF: 1`; CORS allowlist; `SameSite=Lax` | None known |
| T5 | A viewer or an API key changes configuration | E | One role dependency per route; API keys only on safe methods; tests over the role matrix | None known |
| T6 | A leaked database dump yields usable keys or tokens | I, S | Only peppered HMACs of secrets are stored; the pepper is in the environment or Secrets Manager | A dump plus the pepper allows offline checking of guessed secrets (secrets are 32 random bytes) |
| T7 | A compromised GPU machine writes false telemetry | T | Host token scoped to its own host; GPUs it did not declare are dropped; time window; rate limit; revocation | It can report false values for its own GPUs, or claim another GPU's UUID by declaring it (attribution caps every GPU-hour at 3600 s, so overlap never bills more than an hour per hour). Revoke the host |
| T8 | A compromised agent floods the API | D | Per-host rate limit (`INGEST_RPM_PER_HOST`), body limit with chunked counting, row limit per batch, WAF flood rule on AWS | A large fleet of compromised hosts can still load Postgres |
| T9 | A crafted body crashes the API or poisons the database (huge body, lone surrogate, out-of-range numbers) | D, T | Body limit before parsing; orjson validation (422 `invalid_json`); bounded Pydantic schemas; readings outside what any GPU can report (or not finite) are stored as NULL, so one bad value neither refuses the batch nor reaches the rollup arithmetic; timestamps must carry a zone | None known |
| T10 | A replayed batch double-counts cost | T | `batch_id` deduplication in `ingest_batches`; row primary keys ignore duplicates | None known |
| T11 | Backdated rows rewrite history | T | Rows older than `RAW_RETENTION_DAYS` or more than 120 s in the future are dropped; only simulated hosts may backfill further | A host may still insert rows in the last `RAW_RETENTION_DAYS` for its own GPUs where no row exists yet |
| T12 | A simulated enrolment token is minted through the API to backfill arbitrary history | E | No API route creates simulated tokens; only the `seed-demo` CLI (shell access, refused in production) does | An operator who runs `seed-demo` on a real deployment creates one |
| T13 | An enrolment token leaks and an attacker enrols rogue hosts | S | Tokens expire (30 days by default), have optional use limits, are revocable; every enrolment is audited and shows in Hosts | Until revoked, a leaked token enrols hosts; revoke it and the rogue hosts. A revoked host cannot re-enrol with a token older than its revocation |
| T14 | An admin points a webhook at cloud metadata or an internal service (SSRF) | I, E | Link-local, metadata, multicast, reserved and unspecified addresses always refused; private ranges refusable with `WEBHOOK_ALLOW_PRIVATE=false`; checked on save and before every delivery; redirects not followed | Private targets allowed by default; DNS rebinding between the check and the connection is not prevented (the address is not pinned) |
| T15 | Forged alerts sent to a receiver | S | HMAC-SHA256 over timestamp and body with a per-channel secret; receivers reject old timestamps | Receivers that do not verify accept anything |
| T16 | A webhook secret is read from the database and used elsewhere | I | Sealed with KMS (encryption context bound to the channel) or AES-GCM with associated data; IAM limits decryption to the `channel:*` context | Anyone with the KMS key and decrypt permission can open it |
| T17 | GPUWatch is used to run commands on GPU machines | E | No inbound port on the agent; no command channel; the reply carries only counts and `next_in_s`; tests over the route table and the agent's source | None by design |
| T18 | `/metrics` discloses the fleet | I | `METRICS_TOKEN`; optional CIDR restriction at the ALB | Unset token means public metrics on a public endpoint |
| T19 | An admin deletes evidence of a change | R | Audit rows written in the same transaction; database trigger refuses `UPDATE` and `DELETE` | A database superuser can still drop the trigger |
| T20 | Secrets leak through logs or error messages | I | `hide_parameters=True`; log field redaction; one error envelope without stack traces | A secret placed in free text by a user (for example a rule name) is logged like any text |
| T21 | A pathological workload rule regex stalls attribution | D | Admin only, compiled on write, 200 character limit; a failing job never stops the other jobs | Catastrophic backtracking is not detected |
| T22 | Redis is lost or evicted to bypass a revocation | S | Revocations and token hashes live in Postgres; the config cache holds rows for at most 5 s | Up to 5 s of grace on another replica when the version stamp is unreachable |
| T23 | A production deployment runs with demo secrets | S, E | Boot guards refuse weak or equal secrets, local keys, an emulator endpoint and insecure cookies | Guards check shape and length, not entropy |
| T24 | A report download link is shared outside the organisation | I | Downloads go through the API with the caller's session or key; there is no public link | Anyone with a viewer session can download every report |
| T25 | A holder of any enrolment token enrols with another host's `machine_id` (visible to viewers) and takes over its host row; cloned images sharing `/etc/machine-id` merge into one host | S, T | Enrolment tokens are admin-issued, expire and are audited; every enrolment shows in the audit log; `GPUWATCH_MACHINE_ID` gives each agent a stable unique id | Not prevented in 0.1.0: the token rotates and the two agents alternate. Give cloned machines their own `GPUWATCH_MACHINE_ID` |
| T26 | A viewer or read-only key reads a chat webhook URL, which is itself a credential | I | Viewers and keys see the scheme and host only; the full URL is shown to admins | None known |
| T27 | A process or host named like a spreadsheet formula runs when a cost report is opened | T | Labels starting with `=`, `+`, `-`, `@`, tab or carriage return are written with a leading apostrophe | None known |
| T28 | Worker memory grows with fleet size: attribution loads an hour of raw samples, insights a week of minute rollups | D | Advisory locks (one worker does the work), retention, rollups instead of raw scans for every dashboard read | Sized for fleets of hundreds of GPUs on one worker; batching per host is on the roadmap |

## Out of scope

- Physical access to GPU machines, a compromised AWS account, or leaked deployment
  secrets.
- Denial of service against a deployment you operate yourself through legitimate load.
- The demo seed (`make demo`) and the mock vLLM server, which use well-known values on
  purpose and never run in production.
