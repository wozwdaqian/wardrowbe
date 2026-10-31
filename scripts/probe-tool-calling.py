#!/usr/bin/env python3
"""Check whether the configured text model supports tool calling and streaming.

Read-only: sends one tool-enabled request and one streaming request to AI_BASE_URL from .env
and reports what came back. The assistant uses native tools when they work and falls back to
JSON instructions otherwise, so this only tells you which path it will take.
"""

import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / ".env")
base = (env.get("AI_BASE_URL") or "").rstrip("/")
model = env.get("AI_TEXT_MODEL") or ""
if not base or not model:
    sys.exit("AI_BASE_URL and AI_TEXT_MODEL must be set in .env (scripts/configure-ai.py).")
headers = {"Content-Type": "application/json"}
if env.get("AI_API_KEY"):
    headers["Authorization"] = f"Bearer {env['AI_API_KEY']}"
TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get today's weather for the user's saved location.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}
MESSAGES = [{"role": "user", "content": "What's the weather today? Use the tool."}]


def probe_tools(client: httpx.Client) -> str:
    response = client.post(
        f"{base}/chat/completions",
        headers=headers,
        json={"model": model, "messages": MESSAGES, "tools": [TOOL], "max_tokens": 200},
    )
    if response.status_code >= 400:
        return f"rejected (HTTP {response.status_code}): {response.text[:200]}"
    message = response.json()["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    if calls:
        return f"supported: called {calls[0]['function']['name']}"
    return "accepted but not used (the model answered in text): " + str(message.get("content"))[:120]


def probe_stream(client: httpx.Client) -> str:
    chunks = 0
    with client.stream(
        "POST",
        f"{base}/chat/completions",
        headers=headers,
        json={"model": model, "messages": MESSAGES, "stream": True, "max_tokens": 50},
    ) as response:
        if response.status_code >= 400:
            return f"rejected (HTTP {response.status_code})"
        for line in response.iter_lines():
            if line.startswith("data:") and line.strip() != "data: [DONE]":
                json.loads(line[5:])
                chunks += 1
    return f"supported: {chunks} chunks" if chunks > 1 else f"single chunk ({chunks})"


with httpx.Client(timeout=60) as client:
    print(f"endpoint: {base}  model: {model}")
    for name, probe in (("tool calling", probe_tools), ("streaming", probe_stream)):
        try:
            print(f"{name:13}: {probe(client)}")
        except Exception as exc:
            print(f"{name:13}: failed: {type(exc).__name__}: {exc}")
