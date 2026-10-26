# Security Policy

GPUWatch runs an agent on your GPU machines, holds the tokens those agents use, and knows
your fleet, workloads and costs, so we take reports seriously and respond quickly.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x | Yes |
| Earlier | No |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include:

- the affected component (`apps/api`, `apps/agent`, `apps/web`, `infra/terraform/...`) and
  version or commit,
- a description of the issue and its impact,
- steps to reproduce, or a proof of concept,
- any suggested mitigation.

What to expect:

| Stage | Target |
| ----- | ------ |
| Acknowledgement | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation for critical and high issues | within 30 days |
| Coordinated public disclosure | after a fix is released, credited to you unless you prefer otherwise |

## Scope

In scope: the code in this repository and the infrastructure it provisions with its
default settings. We are especially interested in:

- any way to make an agent run a command, open a port, or change anything on a GPU
  machine, or to send it instructions through the API;
- any way to write telemetry as another host, into another host's GPUs, or outside the
  accepted time window, or to create a simulated enrolment token through the API;
- any way to recover an API key, host token, enrolment token or webhook signing secret
  from the API, logs or database;
- SSRF through webhook channels (reaching link-local or metadata addresses, or private
  addresses when `WEBHOOK_ALLOW_PRIVATE=false`);
- authentication or authorization bypasses in the dashboard API, including an API key
  that can write;
- tampering with the audit log, or making costs or insights disagree with the stored data.

Out of scope:

- **The demo seed.** `make demo` creates well-known demo logins on purpose and refuses to
  run with `ENVIRONMENT=production`.
- **The mock vLLM server** (`gpuwatch-mock-vllm`), a demo and test fixture.
- **Simulated hosts** backfilling history, which is their documented purpose.
- Findings that require a compromised host with root access to the agent's state
  directory, a compromised AWS account, or leaked deployment secrets.
- Denial of service through resource exhaustion of a deployment you operate yourself.

## Hardening checklist for operators

See [docs/architecture/security.md](docs/architecture/security.md#operator-checklist).
