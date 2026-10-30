#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
exec "$project_dir/../manager/pf" stop wardrowbe/web wardrowbe/worker wardrowbe/image-worker wardrowbe/backend wardrowbe/redis wardrowbe/postgres
