"""Command-line interface for BioAgent."""

from __future__ import annotations

import argparse
import json
import sys

from harness.runtime import resume_bioagent, run_bioagent
from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MAX_TURNS, DEFAULT_MODEL_KEYS


def _log_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the BioAgent Agents SDK harness.")
    parser.add_argument("request", nargs="*", help="User request for the agent.")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", metavar="ID", help="Approve a pending tool call by approval_id.")
    decision.add_argument("--reject", metavar="ID", help="Reject a pending tool call by approval_id.")
    parser.add_argument(
        "--model-key",
        default=DEFAULT_AGENT_MODEL_KEY,
        choices=DEFAULT_MODEL_KEYS,
        help=f"Model key from models.config.DEFAULT_MODELS. Default: {DEFAULT_AGENT_MODEL_KEY}.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"Maximum Agents SDK model turns. Default: {DEFAULT_MAX_TURNS}.",
    )
    parser.add_argument("--session-id", help="Continue a persistent SDK conversation.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print the complete structured result.")
    parser.add_argument("--verbose", action="store_true", help="Print progress messages on stderr.")
    args = parser.parse_args()
    if args.approve or args.reject:
        if not args.session_id or args.request:
            parser.error("approval decisions require --session-id and no new request")
    elif not args.request:
        parser.error("a request or --approve/--reject is required")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.approve or args.reject:
            result = resume_bioagent(
                args.session_id, bool(args.approve), args.approve or args.reject,
                log_fn=_log_progress if args.verbose else None,
            )
        else:
            result = run_bioagent(
                request=" ".join(args.request), session_id=args.session_id,
                model_key=args.model_key, max_turns=args.max_turns,
                log_fn=_log_progress if args.verbose else None,
            )
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"Agent error: {exc}")
        return 1
    print(json.dumps(result, indent=2, default=str) if args.as_json else result["answer"])
    if result.get("approval_required") and not args.as_json:
        for item in result["approvals"]:
            print(f"\n{item['tool_name']}: {json.dumps(item['arguments'], indent=2)}")
            print(f"python -m interfaces.cli --session-id {result['session_id']} --approve {item['approval_id']}")
            print("Use --reject in place of --approve to decline this call.")
    return 0 if result.get("status") not in {"error", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
