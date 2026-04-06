import json
import mimetypes
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parent
DB_DIR = Path(os.getenv("SPNS_DB_DIR", APP_DIR / "data"))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB = DB_DIR / "spns_rapports.db"

HOST = os.getenv("SPNS_HOST", "127.0.0.1")
PORT = int(os.getenv("SPNS_PORT", "8022"))
ALLOWED_ORIGIN = os.getenv("SPNS_ALLOWED_ORIGIN", "*")
TABLES = {"activities", "requests"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    for table_name in TABLES:
        cur.execute(
            f"""
            create table if not exists {table_name}(
                id text primary key,
                payload text not null,
                created_at text not null,
                updated_at text not null
            )
            """
        )
    conn.commit()
    conn.close()


def read_table(table_name):
    conn = get_db()
    rows = conn.execute(
        f"select payload from {table_name} order by coalesce(updated_at, created_at) desc, id desc"
    ).fetchall()
    conn.close()
    return [json.loads(row["payload"]) for row in rows]


def upsert_item(table_name, item):
    if not item or not item.get("id"):
        raise ValueError("Missing item id")
    timestamp = now_iso()
    payload = dict(item)
    payload.setdefault("createdAt", timestamp)
    payload["updatedAt"] = timestamp
    conn = get_db()
    conn.execute(
        f"""
        insert into {table_name}(id, payload, created_at, updated_at)
        values(?, ?, ?, ?)
        on conflict(id) do update set
            payload=excluded.payload,
            created_at=coalesce({table_name}.created_at, excluded.created_at),
            updated_at=excluded.updated_at
        """,
        (
            payload["id"],
            json.dumps(payload, ensure_ascii=False),
            payload["createdAt"],
            payload["updatedAt"],
        ),
    )
    conn.commit()
    conn.close()
    return payload


def delete_item(table_name, item_id):
    conn = get_db()
    cur = conn.execute(f"delete from {table_name} where id = ?", (item_id,))
    conn.commit()
    deleted = cur.rowcount > 0
