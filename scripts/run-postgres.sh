#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
set -a
. ./.env
set +a
mkdir -p data/postgres data/postgres-socket
chmod 700 data/postgres data/postgres-socket
if [ ! -f data/postgres/PG_VERSION ]; then
  ./runtime/postgres/bin/initdb -D "$project_dir/data/postgres" --username="$POSTGRES_USER" \
    --encoding=UTF8 --locale=C --auth-local=trust --auth-host=scram-sha-256 \
    --pwfile="$project_dir/config/postgres-password" --no-instructions
fi
exec ./runtime/postgres/bin/postgres -D "$project_dir/data/postgres" -h 127.0.0.1 \
  -p "$POSTGRES_PORT" -k "$project_dir/data/postgres-socket" \
  -c max_connections=50 -c shared_buffers=64MB -c unix_socket_permissions=0700
