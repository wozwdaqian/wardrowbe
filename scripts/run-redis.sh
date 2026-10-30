#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
exec ./runtime/redis/bin/redis-server ./config/redis.conf
