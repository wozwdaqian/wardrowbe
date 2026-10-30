import os,subprocess,sys
from pathlib import Path
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1];cfg=dotenv_values(root/'.env')
env={**os.environ,**{k:v for k,v in cfg.items() if v is not None}}
dsn=cfg['DATABASE_URL'].rsplit('/',1)[0]+'/wardrowbe_body_styling_test_20261029'
env.update(DATABASE_URL=dsn,TEST_DATABASE_URL=dsn,REDIS_URL='redis://127.0.0.1:16380/14',AI_INTERNAL_ENABLED='true',AI_VISION_ENABLED='true',AI_TEXT_ENABLED='true',AI_BASE_URL='',AI_API_KEY='',AI_REASONING_EFFORT='none',AI_MAX_RETRIES='3',PATH=str(root/'.venv/bin')+':'+env['PATH'])
result=subprocess.run([str(root/'.venv/bin/python'),'-m','pytest','tests/test_body_styling.py','tests/test_users.py','tests/test_ai_service.py','-q','--tb=short'],cwd=root/'backend',env=env)
sys.exit(result.returncode)
