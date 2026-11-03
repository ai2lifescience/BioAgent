"""Account administration: python -m auth."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re

from .context import LOCAL_USER_ID, Principal
from .store import AuthStore, database
from .ownership import OwnershipStore

def main() -> int:
    parser = argparse.ArgumentParser(description="Administer BioAgent accounts and explicitly assign legacy sessions.")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add-user")
    add.add_argument("username")
    reset = commands.add_parser("set-password")
    reset.add_argument("username")
    adopt = commands.add_parser("adopt-legacy")
    adopt.add_argument("--user", required=True, help="Existing username, or local for single-user mode")
    adopt.add_argument("--apply", action="store_true", help="Without this flag, only list unowned sessions")
    args = parser.parse_args()
    if args.command in {"add-user", "set-password"}:
        password = getpass.getpass("Password (12+ characters): ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("Passwords did not match.")
        store = AuthStore()
        if args.command == "add-user":
            print("Created user:", store.add_user(args.username, password))
        else:
            store.set_password(args.username, password)
            print("Password changed; existing logins revoked.")
        return 0
    user = Principal(LOCAL_USER_ID) if args.user == "local" else AuthStore().user(args.user)
    root = Path(os.getenv("AGENT_METADATA_DIR", "runtime/session_metadata")).expanduser().resolve()
    ownership = OwnershipStore(root)
    with database(ownership.path) as db:
        existing = {row[0] for row in db.execute("SELECT session_id FROM owners")}
        ids = sorted(p.stem for p in root.glob("*.json") if p.stem not in existing)
        for identifier in ids:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
                raise ValueError("Invalid legacy session ID")
            data = json.loads((root / f"{identifier}.json").read_text())
            if data.get("session_id") != identifier:
                raise ValueError("Legacy session ID does not match its filename")
            print(identifier)
            if args.apply:
                db.execute("INSERT INTO owners VALUES (?,?,0)", (identifier, user.user_id))
    print(f"{'Assigned' if args.apply else 'Unassigned'} sessions: {len(ids)}")
    # Apply a matching owner to historical queue rows without replaying work.
    # Stop the server/workers before running this administrative migration.
    run_path = Path(os.getenv("AGENT_RUN_DB", "runtime/agent_runs.sqlite3"))
    if args.apply and run_path.exists():
        with database(ownership.path) as db:
            owned = [row[0] for row in db.execute("SELECT session_id FROM owners WHERE user_id=? AND deleted=0", (user.user_id,))]
        with database(run_path) as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(runs)")}
            if columns:
                if "owner_user_id" not in columns:
                    db.execute("ALTER TABLE runs ADD COLUMN owner_user_id TEXT")
                for identifier in owned:
                    db.execute("UPDATE runs SET status='interrupted', error='Legacy job migrated; review before starting new work.' WHERE session_id=? AND owner_user_id IS NULL AND status IN ('queued','running')", (identifier,))
                    db.execute("UPDATE runs SET owner_user_id=? WHERE session_id=? AND owner_user_id IS NULL", (user.user_id, identifier))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
