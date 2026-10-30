#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$project_dir/runtime/postgres/bin/pg_isready" -h 127.0.0.1 -p 15433 -U wardrowbe
