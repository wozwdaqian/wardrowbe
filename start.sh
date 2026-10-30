#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PORT="${PORT:-18083}"
export HOSTNAME=127.0.0.1
exec "$project_dir/.venv/bin/python" "$project_dir/scripts/run-service.py" web
