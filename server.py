import json
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

HOST = os.getenv("SPNS_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("SPNS_PORT", "10000")))
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
    conn.close()
    return deleted


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.json({"ok": True, "service": "spns-rapports-api"})
        if path == "/api/bootstrap":
            return self.json(
                {
                    "activities": read_table("activities"),
                    "requests": read_table("requests"),
                }
            )
        return self.json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_json()
        if path == "/api/activities/upsert":
            return self.handle_upsert("activities", body)
        if path == "/api/requests/upsert":
            return self.handle_upsert("requests", body)
        return self.json({"error": "Not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/activities/"):
            return self.handle_delete("activities", path.removeprefix("/api/activities/"))
        if path.startswith("/api/requests/"):
            return self.handle_delete("requests", path.removeprefix("/api/requests/"))
        return self.json({"error": "Not found"}, 404)

    def handle_upsert(self, table_name, body):
        try:
            item = upsert_item(table_name, body.get("item") or {})
        except ValueError as error:
            return self.json({"error": str(error)}, 400)
        return self.json({"ok": True, "item": item})

    def handle_delete(self, table_name, item_id):
        if not item_id:
            return self.json({"error": "Missing id"}, 400)
        deleted = delete_item(table_name, item_id)
        return self.json({"ok": deleted})

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def json(self, data, status=200):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SPNS Rapports server on http://{HOST}:{PORT}")
    server.serve_forever()
