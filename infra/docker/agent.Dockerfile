# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# Agent: runs on each GPU machine and sends metrics to the GPUWatch API
# (`gpuwatch-agent run`, `gpuwatch-agent check`). The same image serves the demo's mock
# vLLM metrics endpoint (`gpuwatch-mock-vllm`).
#   docker build -f infra/docker/agent.Dockerfile -t gpuwatch-agent apps/agent
#   docker run --gpus all --pid=host -e GPUWATCH_URL=... -e GPUWATCH_ENROLMENT_TOKEN=... \
#     -v gpuwatch-agent:/var/lib/gpuwatch-agent gpuwatch-agent
#
# NVML (libnvidia-ml.so) is not in the image: the NVIDIA Container Toolkit mounts the host
# driver's library into the container when it runs with --gpus.
# ─────────────────────────────────────────────────────────────────────────────
ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.9.17 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project
COPY pyproject.toml uv.lock README.md ./
COPY src src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC \
    GPUWATCH_STATE_DIR=/var/lib/gpuwatch-agent \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=utility
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 gpuwatch \
 && useradd --system --uid 10001 --gid gpuwatch --home-dir /var/lib/gpuwatch-agent \
      --no-create-home --shell /usr/sbin/nologin gpuwatch \
 && mkdir -p /var/lib/gpuwatch-agent /state && chown gpuwatch:gpuwatch /var/lib/gpuwatch-agent /state
COPY --from=build /opt/venv /opt/venv
# Unprivileged: NVML needs no root. To read process names of other users with --pid=host,
# run with --user 0 or grant CAP_SYS_PTRACE; without it, processes show as "pid <n>".
USER 10001:10001
VOLUME ["/var/lib/gpuwatch-agent"]
ENTRYPOINT ["/usr/bin/tini", "--", "gpuwatch-agent"]
CMD ["run"]
