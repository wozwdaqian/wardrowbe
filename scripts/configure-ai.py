#!/usr/bin/env python3
"""Store an OpenAI-compatible service configuration locally, without echoing its key."""
from getpass import getpass
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / '.env'
current = dotenv_values(path)


def ask(label, key):
    default = current.get(key) or ''
    return input(f'{label}' + (f' [{default}]' if default else '') + ': ').strip() or default


print('配置 Wardrowbe 的 AI 服务（密钥只保存在本机 .env 中）')
url = ask('API 地址，例如 http://127.0.0.1:18082/v1', 'AI_BASE_URL').rstrip('/')
if urlsplit(url).scheme not in ('http', 'https') or not urlsplit(url).netloc:
    raise SystemExit('地址无效，配置未修改。')
text = ask('文字模型名称（身材穿搭必填）', 'AI_TEXT_MODEL')
vision = ask('图片模型名称（衣物识别选填，可直接回车跳过）', 'AI_VISION_MODEL')
if not text:
    raise SystemExit('请提供模型名称，配置未修改。')
key = getpass('API 密钥（留空保留现有值；本地免密服务可留空）: ').strip()
key = key or current.get('AI_API_KEY') or ''
for name, value in {
    'AI_BASE_URL': url, 'AI_API_KEY': key,
    'AI_VISION_MODEL': vision, 'AI_TEXT_MODEL': text,
    'AI_INTERNAL_ENABLED': 'true', 'AI_TEXT_ENABLED': 'true',
    'AI_VISION_ENABLED': 'true' if vision else 'false',
}.items():
    set_key(path, name, value, quote_mode='always')
path.chmod(0o600)
print('配置已保存，正在重启 API 和后台任务。')
subprocess.run([str(ROOT.parent / 'manager/pf'), 'restart',
                'wardrowbe/backend', 'wardrowbe/worker', 'wardrowbe/image-worker'],
               cwd=ROOT, check=True)
print('完成。可在浏览器打开 http://127.0.0.1:18083 继续使用。')
