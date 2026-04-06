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
