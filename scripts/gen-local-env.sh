#!/usr/bin/env bash
# Write deploy/compose/.env with random, local-only secrets (once; never overwrites).
set -euo pipefail
f="$(cd "$(dirname "$0")/.." && pwd)/deploy/compose/.env"
if [[ -f "$f" ]]; then
  echo "deploy/compose/.env exists (delete it to regenerate)"
  exit 0
fi
rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-"$1"; }
umask 077
# SESSION_SECRET and API_KEY_PEPPER must differ (the API refuses to boot otherwise);
# two independent draws of 64 characters always do. The demo password always has upper
# and lower case letters and a digit, as the API's password policy requires.
cat > "$f" <<ENV
SESSION_SECRET=$(rand 64)
API_KEY_PEPPER=$(rand 64)
LOCAL_MASTER_KEY=$(rand 64)
GW_DEMO_PASSWORD=Watch-$(rand 10)-7
ENV
echo "wrote deploy/compose/.env"
