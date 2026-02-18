"""One-off migration: add pinned column to chat_sessions if missing. Run from backend: python -m scripts.add_pinned_to_sessions"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.config import DATABASE_URL


def main():
    with engine.connect() as conn:
        if "sqlite" in DATABASE_URL:
            # SQLite: check if column exists
            r = conn.execute(text("PRAGMA table_info(chat_sessions)"))
            cols = [row[1] for row in r.fetchall()]
            if "pinned" in cols:
                print("Column 'pinned' already exists. Nothing to do.")
                return
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN pinned BOOLEAN DEFAULT 0"))
            conn.commit()
            print("Added column 'pinned' to chat_sessions (SQLite).")
        else:
            # PostgreSQL etc.
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false"))
            conn.commit()
            print("Added column 'pinned' to chat_sessions (PostgreSQL).")


if __name__ == "__main__":
    main()
