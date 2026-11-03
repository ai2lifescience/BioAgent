"""Immutable session ownership, including tombstones for deleted sessions."""
from pathlib import Path

from .context import AccessDenied, current_principal
from .store import database

class OwnershipStore:
    """Ownership survives session deletion, preventing ID reuse or adoption."""
    def __init__(self, metadata_root: Path):
        self.root = metadata_root
        self.path = metadata_root / ".ownership.sqlite3"
        with database(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS owners (session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)")

    def require(self, session_id: str) -> None:
        principal = current_principal()
        with database(self.path) as db:
            row = db.execute("SELECT * FROM owners WHERE session_id=?", (session_id,)).fetchone()
        if not row or row["deleted"] or row["user_id"] != principal.user_id:
            raise AccessDenied("Session not found.")

    def claim(self, session_id: str, *, legacy_exists: bool = False) -> None:
        principal = current_principal()
        with database(self.path) as db:
            row = db.execute("SELECT * FROM owners WHERE session_id=?", (session_id,)).fetchone()
            if row:
                if row["deleted"] or row["user_id"] != principal.user_id:
                    raise AccessDenied("Session not found.")
            elif legacy_exists:
                raise AccessDenied("This session requires an explicit owner migration.")
            else:
                db.execute("INSERT INTO owners VALUES (?,?,0)", (session_id, principal.user_id))

    def delete(self, session_id: str) -> None:
        self.require(session_id)
        with database(self.path) as db:
            db.execute("UPDATE owners SET deleted=1 WHERE session_id=?", (session_id,))

    def owned_ids(self, *, include_deleted: bool = False) -> set[str]:
        principal = current_principal()
        with database(self.path) as db:
            query = "SELECT session_id FROM owners WHERE user_id=?" + ("" if include_deleted else " AND deleted=0")
            return {row[0] for row in db.execute(query, (principal.user_id,))}
