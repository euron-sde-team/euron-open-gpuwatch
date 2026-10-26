# Euron Open GPUWatch: developer entry points. `make` lists every target.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE_DIR := deploy/compose
FLOCI       := docker compose --env-file $(COMPOSE_DIR)/.env -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.floci.yaml
AWS_LOCAL   := docker compose --env-file $(COMPOSE_DIR)/.env -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.aws.yaml
API         := cd apps/api &&
AGENT       := cd apps/agent &&
WEB         := cd apps/web &&
TF_IMAGE    := hashicorp/terraform:1.16.6
TF_ENVS     := local-floci aws-dev aws-prod
# Use a local terraform when installed, otherwise the pinned container.
TF          := $(shell command -v terraform >/dev/null 2>&1 && echo terraform || echo docker run --rm -v $(CURDIR)/infra/terraform:/infra -w /infra $(TF_IMAGE))
TF_ROOT     := $(shell command -v terraform >/dev/null 2>&1 && echo infra/terraform || echo /infra)
ENV         ?= aws-dev
# The demo password make env generated; e2e, qa and bench sign in with it.
DEMO_PW      = $(shell grep -s '^GW_DEMO_PASSWORD=' $(COMPOSE_DIR)/.env | cut -d= -f2)

.PHONY: help env up up-aws down logs ps demo test test-integration migration test-matrix e2e qa screenshots bench lint \
        typecheck build openapi sanitize admin aws-deploy aws-migrate aws-admin tf-fmt tf-validate tf-lint tf-security tf-aws-on-floci \
        aws-plan clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ─── Local ───────────────────────────────────────────────────────────────────

env: ## Generate deploy/compose/.env with random local-only secrets
	@scripts/gen-local-env.sh

up: env ## Start everything on emulated AWS (Floci), provisioned by the same Terraform as production
	$(FLOCI) up -d --build --wait
	@echo ""
	@echo "  dashboard  http://localhost:$${GW_WEB_PORT:-4410}"
	@echo "  api        http://localhost:$${GW_API_PORT:-4430}   (agents send to /ingest/v1)"
	@echo "  api docs   http://localhost:$${GW_API_PORT:-4430}/docs"
	@echo "  mailpit    http://localhost:$${GW_MAILPIT_PORT:-4425}   (alert email lands here)"
	@echo ""
	@echo "  Next: make demo   (three simulated GPU hosts, 30 days of history, live data)"

up-aws: env ## Start the stack against real AWS resources (needs deploy/compose/.env.aws)
	@test -f $(COMPOSE_DIR)/.env.aws || { echo "copy $(COMPOSE_DIR)/.env.aws.example to .env.aws first"; exit 1; }
	$(AWS_LOCAL) up -d --build --wait

demo: ## Demo users, rates and rules, then three simulated GPU hosts (the real agent) and a mock vLLM
	$(FLOCI) exec -T api gpuwatch seed-demo --token-file /demo/enrolment-token
	$(FLOCI) --profile demo up -d --build --wait mock-vllm agent-train agent-infer agent-dev
	@echo ""
	@echo "  The agents are backfilling $${GW_DEMO_DAYS:-30} days of history (about 4 minutes on a laptop), then report live."
	@echo "  Follow along: make logs SERVICE=agent-train"

down: ## Stop the stack (and the demo agents) and delete its volumes
	-$(FLOCI) --profile demo down -v --remove-orphans
	-$(AWS_LOCAL) down -v --remove-orphans 2>/dev/null

admin: ## Create or reset an owner on the local stack (EMAIL=you@example.com; prompts for the password)
	@test -n "$(EMAIL)" || { echo "usage: make admin EMAIL=you@example.com"; exit 1; }
	$(FLOCI) exec api gpuwatch create-owner --email "$(EMAIL)"

logs: ## Tail logs (SERVICE=api|worker|web|floci|agent-train|...)
	$(FLOCI) --profile demo logs -f --tail 100 $(SERVICE)

ps: ## Show stack status
	$(FLOCI) --profile demo ps

# ─── Quality ─────────────────────────────────────────────────────────────────

lint: ## Lint the API and the agent (ruff) and the web app (eslint)
	$(API) uv run ruff check src tests && uv run ruff format --check src tests
	$(AGENT) uv run ruff check src tests && uv run ruff format --check src tests
	$(WEB) pnpm lint

typecheck: ## Typecheck the API and the agent (mypy --strict) and the web app (tsc)
	$(API) uv run mypy src
	$(AGENT) uv run mypy src
	$(WEB) pnpm typecheck

test: ## Unit tests: API and agent (pytest) and web (vitest). No database, no GPU
	$(API) uv run pytest tests/unit -q
	$(AGENT) uv run pytest -q
	$(WEB) pnpm test

migration: ## Autogenerate an Alembic revision from the models: make migration MSG="add x" (local Postgres)
	@test -n "$(MSG)" || (echo 'usage: make migration MSG="what changed"' && exit 1)
	@scripts/test-db.sh
	$(API) DATABASE_URL=postgresql+asyncpg://gpuwatch:gpuwatch@localhost:$${GW_PG_PORT:-4442}/gpuwatch \
	  sh -c 'uv run gpuwatch migrate && uv run gpuwatch revision -m "$(MSG)"'

test-integration: ## API integration tests against real Postgres and Redis (started if needed)
	@scripts/test-db.sh
	$(API) uv run pytest tests/integration -q --cov --cov-report=term-missing:skip-covered

test-matrix: ## Integration tests under every cache, key and storage backend (no Redis, Floci KMS and S3)
	@scripts/test-matrix.sh

e2e: ## Browser end-to-end tests (Playwright) against the running stack (make up && make demo)
	cd e2e && pnpm install --frozen-lockfile && pnpm exec playwright install chromium && E2E_PASSWORD='$(DEMO_PW)' pnpm test

qa: ## Browser QA sweep (Puppeteer): every page, light and dark, desktop and phone
	cd scripts/qa && pnpm install --frozen-lockfile && QA_PASSWORD='$(DEMO_PW)' node qa.mjs

screenshots: ## README screenshots and the tour GIF from the running demo (after make demo)
	cd scripts/qa && pnpm install --frozen-lockfile && QA_PASSWORD='$(DEMO_PW)' node screenshots.mjs
	scripts/qa/make-tour.sh

bench: ## Measure ingest and dashboard latency and throughput against the running stack
	$(API) DEMO_PASSWORD='$(DEMO_PW)' uv run python -m gpuwatch.bench

build: ## Build the container images
	$(FLOCI) build

openapi: ## Regenerate docs/api/openapi.yaml from the FastAPI app
	$(API) uv run gpuwatch openapi > ../../docs/api/openapi.yaml

sanitize: ## Scan committable files for credentials, cloud identifiers and em/en dashes
	@scripts/check-sanitization.sh

# ─── Terraform ───────────────────────────────────────────────────────────────

tf-fmt: ## Format all Terraform
	$(TF) fmt -recursive $(TF_ROOT)

tf-validate: ## terraform validate every environment (no backend, no credentials)
	@for env in $(TF_ENVS); do \
	  echo "== $$env"; \
	  $(TF) -chdir=$(TF_ROOT)/envs/$$env init -backend=false -input=false -no-color >/dev/null && \
	  $(TF) -chdir=$(TF_ROOT)/envs/$$env validate -no-color || exit 1; \
	done

tf-lint: ## tflint every module and environment (plugins cached in a docker volume)
	docker run --rm -v $(CURDIR)/infra/terraform:/data -v gpuwatch-tflint:/plugins -e TFLINT_PLUGIN_DIR=/plugins -w /data ghcr.io/terraform-linters/tflint:v0.64.0 --init
	docker run --rm -v $(CURDIR)/infra/terraform:/data -v gpuwatch-tflint:/plugins -e TFLINT_PLUGIN_DIR=/plugins -w /data ghcr.io/terraform-linters/tflint:v0.64.0 --recursive --format compact

tf-security: ## checkov policy scan of the Terraform
	docker run --rm -v $(CURDIR)/infra/terraform:/tf bridgecrew/checkov:3.3.30 -d /tf --framework terraform --quiet --compact

tf-aws-on-floci: ## Plan, apply, re-plan and destroy the full aws-dev environment against a throwaway Floci
	@scripts/tf-aws-on-floci.sh

aws-deploy: ## One shot: registries, images, infrastructure, migrations, rollout (ENV=aws-dev|aws-prod TAG=...)
	@test -n "$(TAG)" || { echo "usage: make aws-deploy ENV=aws-dev TAG=0.1.0"; exit 1; }
	@scripts/aws-deploy.sh $(ENV) $(TAG)

aws-migrate: ## Run database migrations as a one-off ECS task (ENV=...)
	@scripts/aws-run-task.sh $(ENV) migrate

aws-admin: ## Create the first owner as a one-off ECS task (ENV=... EMAIL=...; GPUWATCH_OWNER_PASSWORD in your env)
	@test -n "$(EMAIL)" || { echo "usage: GPUWATCH_OWNER_PASSWORD=... make aws-admin ENV=aws-dev EMAIL=you@example.com"; exit 1; }
	@test -n "$$GPUWATCH_OWNER_PASSWORD" || { echo "set GPUWATCH_OWNER_PASSWORD (at least 10 characters, upper and lower case and a digit)"; exit 1; }
	@scripts/aws-run-task.sh $(ENV) create-owner --email "$(EMAIL)"

aws-plan: ## terraform plan for ENV (aws-dev | aws-prod); needs terraform.tfvars and AWS credentials
	cd infra/terraform/envs/$(ENV) && terraform init -input=false && terraform plan

clean: ## Remove build output and caches
	rm -rf apps/web/.next apps/api/.pytest_cache apps/api/.mypy_cache apps/api/.ruff_cache apps/api/.coverage e2e/test-results e2e/playwright-report
