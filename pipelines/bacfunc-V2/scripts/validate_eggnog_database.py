"""Validate an existing eggNOG v5 database without modifying it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from bacfunc.eggnog import validate_database_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        result = validate_database_path(args.data_dir)
    except Exception as exc:
        if args.as_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"INVALID: {exc}")
        return 1
    payload = {"ok": True, **result}
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"VALID: eggNOG database version {result['detected_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
