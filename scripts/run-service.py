#!/usr/bin/env python3
"""Run the upstream services with this project's private runtimes and configuration."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
os.environ['PATH'] = f"{ROOT / 'runtime/node/bin'}:{os.environ.get('PATH', '')}"
os.environ.setdefault('PYTHONUNBUFFERED', '1')
os.environ.setdefault('NEXT_TELEMETRY_DISABLED', '1')
os.environ.setdefault('REMBG_HOME', str(ROOT / 'data/rembg'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT / 'data/numba-cache'))
PYTHON = str(ROOT / '.venv/bin/python')


def replace(command, cwd):
    os.chdir(cwd)
    os.execvpe(str(command[0]), [str(arg) for arg in command], os.environ)


async def ensure_database():
    import asyncpg
    connection = await asyncpg.connect(
        host='127.0.0.1', port=int(os.environ['POSTGRES_PORT']),
        user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
        database='postgres', timeout=15,
    )
    try:
        name = os.environ['POSTGRES_DB']
        if not await connection.fetchval('SELECT 1 FROM pg_database WHERE datname = $1', name):
            await connection.execute('CREATE DATABASE "' + name.replace('"', '""') + '"')
    finally:
        await connection.close()


role = sys.argv[1]
if role == 'backend':
    asyncio.run(ensure_database())
    subprocess.run([PYTHON, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'backend', check=True)
    replace([PYTHON, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
             '--port', os.environ['BACKEND_PORT']], ROOT / 'backend')
elif role == 'worker':
    replace([PYTHON, '-m', 'arq', 'app.workers.worker.WorkerSettings'], ROOT / 'backend')
elif role == 'image-worker':
    replace([PYTHON, '-m', 'arq', 'app.workers.image_worker.ImageWorkerSettings'], ROOT / 'backend')
elif role == 'web':
    os.environ['NODE_ENV'] = 'production'
    replace([ROOT / 'runtime/node/bin/node', ROOT / 'frontend/.next/standalone/server.js'],
            ROOT / 'frontend/.next/standalone')
elif role == 'build':
    os.environ['NODE_ENV'] = 'production'
    replace([ROOT / 'runtime/node/bin/node', ROOT / 'frontend/node_modules/next/dist/bin/next', 'build'],
            ROOT / 'frontend')
elif role in ('check-worker', 'check-image-worker'):
    from redis import Redis
    queue = 'arq:tagging' if role == 'check-worker' else 'arq:images'
    key = Redis.from_url(os.environ['REDIS_URL']).get(queue + ':health-check')
    sys.exit(0 if key else 1)
else:
    raise SystemExit(f'Unknown service: {role}')
