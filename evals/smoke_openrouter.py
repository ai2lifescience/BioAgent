"""Optional live smoke test for the OpenRouter-backed Agents SDK runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness import run_bioagent


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        print("SKIP: set OPENROUTER_API_KEY to run the live smoke test")
        return 0
    model_key = os.getenv("BIOAGENT_SMOKE_MODEL_KEY", "gpt-oss")
    session_id = f"smoke-openrouter-{uuid4().hex[:8]}"
    result = run_bioagent(
        "Analyze this DNA sequence and report its GC content: ACGTACGT.",
        model_key=model_key,
        session_id=session_id,
        max_skill_steps=6,
    )
    if result.get("runtime") != "agents_sdk":
        print(f"FAIL: unexpected runtime {result.get('runtime')!r}")
        return 1
    if not result.get("answer"):
        print("FAIL: OpenRouter returned an empty answer")
        return 1
    if "sequence_analyze" not in (result.get("evidence") or {}).get("tools", []):
        print("FAIL: live run did not dispatch the sequence analysis function tool")
        return 1
    if result.get("status") == "error":
        print(f"FAIL: run error: {result.get('answer')}")
        return 1
    print("PASS: OpenRouter Agents SDK request completed")
    print(f"model_key={model_key} session_id={result.get('session_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
