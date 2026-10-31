#!/usr/bin/env python3
"""Run the 24 evaluation personas against the configured text model and summarise quality.

Usage: scripts/eval-body-styling.py [--locale zh-CN|en] [--only persona_id ...] [--min-pass 0.9]
Reads the AI settings from .env. Run it before changing the prompt or switching models;
the exit status is non-zero when the pass rate is below --min-pass.
"""

import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
os.environ.update({k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None})
sys.path.insert(0, str(ROOT / "backend"))

from app.services.body_styling_service import (  # noqa: E402
    ai_status,
    body_facts,
    generate_ai_content,
    prepare_style,
)
from tests.body_style_eval.checks import PERSONAS, persona_inputs, quality_failures  # noqa: E402


class EvalUser:
    def __init__(self, persona: dict, locale: str):
        self.styling_profile = persona["styling_profile"]
        self.locale = locale


async def run(persona: dict, locale: str) -> tuple[list[str], float]:
    measurements, profile, request, rules = persona_inputs(persona)
    _, facts, _, snapshot = prepare_style(
        EvalUser(persona, locale), measurements, request, None, "ai"
    )
    assert facts == body_facts(measurements, profile)
    started = time.monotonic()
    try:
        content, _ = await generate_ai_content(None, facts, profile, rules, snapshot, locale)
    except Exception as exc:  # report and continue with the next persona
        reason = type(exc.__cause__ or exc).__name__
        return [f"generation failed: {reason}: {str(exc.__cause__ or exc)[:200]}"], 0.0
    return quality_failures(content, rules, locale.startswith("zh")), time.monotonic() - started


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--min-pass", type=float, default=0.9)
    args = parser.parse_args()
    if not ai_status([])["available"]:
        print("No text AI is configured in .env; run scripts/configure-ai.py first.")
        return 2
    personas = [p for p in PERSONAS if not args.only or p["id"] in args.only]
    reasons: Counter[str] = Counter()
    passed = 0
    print(f"{'persona':32} {'result':8} {'secs':>6}  failures")
    for persona in personas:
        failures, seconds = await run(persona, args.locale)
        passed += not failures
        for failure in failures:
            reasons[failure.split(": ", 1)[-1]] += 1
        print(
            f"{persona['id']:32} {'pass' if not failures else 'FAIL':8} {seconds:6.1f}  "
            + "; ".join(failures)
        )
    rate = passed / len(personas)
    print(f"\npass rate: {passed}/{len(personas)} = {rate:.0%} (required {args.min_pass:.0%})")
    if reasons:
        print("most common failures:")
        for reason, count in reasons.most_common(10):
            print(f"  {count:3}  {reason}")
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
