#!/usr/bin/env bash
# Fail if the tree contains anything that must never be published: cloud
# credentials, private keys, real account ids or resource ids, committed env
# files, or an em dash / en dash (banned in every file of every Euron open-source
# repo). Generic patterns only; runs in CI on every push and before every commit.
#
#   scripts/check-sanitization.sh [dir]     (default: repo root)
#
# Portable: bash 3.2 (macOS) and bash 5 (Linux), BSD or GNU grep.
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT" || exit 2

EXCLUDES=(--exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.next
  --exclude-dir=.venv --exclude-dir=.terraform --exclude-dir=coverage --exclude-dir=htmlcov
  --exclude-dir=__pycache__ --exclude-dir=.mypy_cache --exclude-dir=.pytest_cache
  --exclude-dir=.ruff_cache --exclude-dir=playwright-report --exclude-dir=test-results
  --exclude=uv.lock --exclude=pnpm-lock.yaml --exclude=check-sanitization.sh
  --exclude=.gitleaks.toml --exclude=*.lock.hcl --exclude=*.tfstate* --exclude=.env
  --exclude=*.png --exclude=*.jpg --exclude=*.webp --exclude=*.gif --exclude=*.mp4 --exclude=*.ico)

# Inside a git checkout, scan exactly the files git would commit (tracked plus
# untracked-but-not-ignored). That honors .gitignore by construction, so local
# state (deploy/compose/.env, terraform.tfstate, scratch dirs) is never in scope
# and nothing new slips past a hand-maintained exclude list. The path filter below
# is a second line of defence for tool output that a .gitignore may not cover yet.
# Outside git, fall back to a recursive grep with EXCLUDES.
FILES=()
IN_GIT=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IN_GIT=1
  while IFS= read -r -d '' f; do
    case "$f" in
      uv.lock | */uv.lock | pnpm-lock.yaml | */pnpm-lock.yaml | scripts/check-sanitization.sh | \
        .gitleaks.toml | *.lock.hcl | *.tfstate | *.tfstate.* | \
        *.png | *.jpg | *.webp | *.gif | *.mp4 | *.ico) continue ;;
      .venv/* | */.venv/* | node_modules/* | */node_modules/* | .next/* | */.next/* | \
        */__pycache__/* | */.mypy_cache/* | */.pytest_cache/* | */.ruff_cache/* | \
        */.terraform/* | */htmlcov/* | */coverage/* | */playwright-report/* | */test-results/*) continue ;;
    esac
    [[ -f "$f" ]] && FILES+=("$f")
  done < <(git ls-files -z --cached --others --exclude-standard)
fi

# search <extended-regex>: print file:line:text for every match in scope.
search() {
  if ((IN_GIT)); then
    if ((${#FILES[@]})); then
      printf '%s\0' "${FILES[@]}" | xargs -0 grep -nIHE -- "$1" 2>/dev/null || true
    fi
  else
    grep -rnIE "${EXCLUDES[@]}" -- "$1" . 2>/dev/null || true
  fi
}

failed=0
report() { # label, hits
  if [[ -n "$2" ]]; then
    printf '\n\033[31mx %s\033[0m\n%s\n' "$1" "$(printf '%s\n' "$2" | head -20)"
    failed=1
  fi
}

check() { # label, extended-regex, [allow-regex]
  local label="$1" pattern="$2" allow="${3:-}" hits
  hits="$(search "$pattern")"
  if [[ -n "$allow" && -n "$hits" ]]; then hits="$(printf '%s\n' "$hits" | grep -vE -- "$allow" || true)"; fi
  report "$label" "$hits"
}

check "AWS access key id" '\b(AKIA|ASIA)[0-9A-Z]{16}\b'
check "Private key block" '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----' '\.example:|PRIVATE KEY-----\\n\.\.\.\\n'
check "12-digit number (possible AWS account id)" '(^|[^0-9.])[0-9]{12}([^0-9]|$)' '000000000000|123456789012|[0-9a-f]{8}-[0-9a-f]{4}|sha|integrity'
check "AWS resource id" '\b(ami|subnet|sg|vpc|pcx|rtb|igw|eni|vol|snap)-[0-9a-f]{8,17}\b' '-(0{8,17}|x+)\b'
check "RDS endpoint" '\.[a-z0-9]{12}\.[a-z0-9-]+\.rds\.amazonaws\.com'
check "ElastiCache endpoint" '\.[a-z0-9]{6}\.(ng|clustercfg)\.[a-z0-9-]+\.cache\.amazonaws\.com'
check "Slack/GitHub/Stripe/OpenAI/Anthropic style token" '\b(xox[baprs]-[0-9A-Za-z-]{10,}|gh[pousr]_[0-9A-Za-z]{36}|sk_live_[0-9A-Za-z]{24,}|sk-proj-[0-9A-Za-z_-]{20,}|sk-ant-[0-9A-Za-z_-]{20,})\b'

# Em dash (U+2014) and en dash (U+2013), matched as their UTF-8 bytes in the C locale
# so the check behaves the same with BSD and GNU grep and needs no grep -P. Written as
# escapes, so this script never contains the characters it bans.
EM_DASH=$'\xe2\x80\x94'
EN_DASH=$'\xe2\x80\x93'
dash_hits="$(LC_ALL=C search "${EM_DASH}|${EN_DASH}")"
report "Em dash or en dash (use a colon, comma, parentheses or \"to\")" "$dash_hits"

# Env files: only *.example may be tracked.
if ((IN_GIT)); then
  tracked="$(git ls-files -- '*.env' '.env' '.env.*' '**/.env' '**/.env.*' | grep -v '\.example$' || true)"
  report "Committed env file(s)" "$tracked"
fi

if [[ $failed -eq 0 ]]; then
  echo "sanitization: clean"
else
  echo
  echo "sanitization: FAILED (see above). Replace real values with placeholders."
fi
exit $failed
