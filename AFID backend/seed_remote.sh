#!/usr/bin/env bash
# seed_remote.sh -- apply the schema fix and demo analytics data to a remote
# database (Neon) without the connection string ever appearing on the command
# line, in shell history, or in a terminal transcript.
#
# Setup (once):
#   printf 'DATABASE_URL=postgresql://...neon.tech/...?sslmode=require\n' \
#     > "AFID backend/.env.neon"       # gitignored via .env.*
#
# Usage:
#   ./seed_remote.sh            # schema sync + presets + demo data
#   ./seed_remote.sh --wipe     # regenerate demo rows from scratch
#
# What it does, in order:
#   1. migrations.py         -- adds the start_time/end_time/duration_minutes
#                               columns the analytics endpoints need
#   2. seed_presets.py       -- ensures the procedure dropdown has entries
#   3. seed_analytics_demo.py -- 12 demo patients + ~180 completed procedures
#
# Only step 3 writes demo data, and only it is undone by --wipe. Steps 1 and 2
# are idempotent and safe to repeat.

set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE=".env.neon"
PY="./venv/bin/python"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found." >&2
  echo "Create it with a single line:" >&2
  echo "  DATABASE_URL=postgresql://user:password@host.neon.tech/db?sslmode=require" >&2
  exit 1
fi

# Pull DATABASE_URL out of the file without echoing it.
DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [[ -z "$DATABASE_URL" ]]; then
  echo "error: no DATABASE_URL= line in $ENV_FILE" >&2
  exit 1
fi
export DATABASE_URL

if [[ "$DATABASE_URL" != postgres* ]]; then
  echo "error: DATABASE_URL is not a postgres:// or postgresql:// URL" >&2
  exit 1
fi

# Show the host only -- never the credentials.
echo "Target host: $(sed -E 's#.*@([^/?]+).*#\1#' <<< "$DATABASE_URL")"
echo

echo "[1/3] schema sync"
$PY migrations.py

echo "[2/3] procedure presets"
$PY seed_presets.py

echo "[3/3] demo analytics data"
$PY seed_analytics_demo.py "$@"

echo
echo "Done. Open the Vercel HOD portal -> Procedure Analytics."
