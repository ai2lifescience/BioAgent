"""Standalone administrative CLI; agent invocations obtain workspace from context."""
import argparse
import json
from pathlib import Path
import shlex

from .commands import dispatch


def main():
    parser = argparse.ArgumentParser(description="Run the local pipeline protocol in a workspace.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        print(json.dumps(dispatch(args.workspace.resolve(), shlex.join(["bioagent-pipeline", *args.command])), indent=2))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
