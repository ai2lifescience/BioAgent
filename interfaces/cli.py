"""Command-line interface for BioAgent."""

from __future__ import annotations

import argparse
import json
import sys

from harness.runtime import run_bioagent
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_SKILL_STEPS, DEFAULT_MODEL_KEYS


def _log_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the BioAgent Agents SDK harness.")
    parser.add_argument("request", nargs="+", help="User request for the agent.")
    parser.add_argument(
        "--model-key",
        default=DEFAULT_AGENT_MODEL_KEY,
        choices=DEFAULT_MODEL_KEYS,
        help=f"Model key from models.config.DEFAULT_MODELS. Default: {DEFAULT_AGENT_MODEL_KEY}.",
    )
    parser.add_argument(
        "--max-skill-steps",
        type=int,
        default=DEFAULT_MAX_SKILL_STEPS,
        help=f"Maximum Agents SDK model turns. Default: {DEFAULT_MAX_SKILL_STEPS}.",
    )
    parser.add_argument("--session-id", help="Continue a persistent SDK conversation.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print the complete structured result.")
    parser.add_argument("--verbose", action="store_true", help="Print progress messages on stderr.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_bioagent(
            request=" ".join(args.request),
            session_id=args.session_id,
            model_key=args.model_key,
            max_skill_steps=args.max_skill_steps,
            log_fn=_log_progress if args.verbose else None,
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"Agent error: {exc}")
        return 1
    print(json.dumps(result, indent=2, default=str) if args.as_json else result["answer"])
    return 0 if result.get("verification", {}).get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
