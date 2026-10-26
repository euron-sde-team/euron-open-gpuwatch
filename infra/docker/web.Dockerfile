# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# Dashboard: Next.js standalone server.
#   docker build -f infra/docker/web.Dockerfile -t gpuwatch-web apps/web
#
# The browser only ever talks to this origin. /api/* and /v1/* reach the API through
# Next rewrites to API_INTERNAL_URL (locally http://api:8080 on the Compose network);
# on AWS the load balancer routes those paths to the API before they get here.
# ─────────────────────────────────────────────────────────────────────────────
ARG NODE_IMAGE=node:22.23.4-bookworm-slim

FROM ${NODE_IMAGE} AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH CI=true NEXT_TELEMETRY_DISABLED=1
# pnpm comes from corepack, pinned by the packageManager field in package.json.
RUN corepack enable
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

FROM base AS build
# Next resolves rewrites when it builds the standalone server, so the default target
# is set here too; the runtime ENV below wins wherever the app reads it per request.
ARG API_INTERNAL_URL=http://api:8080
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production TZ=UTC PORT=8080 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1 \
    API_INTERNAL_URL=http://api:8080
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
# The only path Next writes at runtime (image and fetch cache); the root filesystem is
# read-only on ECS, which mounts a volume here.
RUN mkdir -p /app/.next/cache && chown node:node /app/.next/cache
USER node
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||8080)+'/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "server.js"]
