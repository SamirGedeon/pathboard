"""SQLite persistence. Each mutation owns a short, explicit transaction."""

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from .planning import ProjectInput, plan


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                    salt TEXT NOT NULL, password TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(
                    token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS projects(
                    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    document TEXT NOT NULL, version INTEGER NOT NULL,
                    updated INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS projects_owner ON projects(user_id);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def password_hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    def auth(self, email, password, signup):
        email = email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise HTTPException(400, "Enter a valid email.")
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if signup:
                if user:
                    raise HTTPException(409, "Email already registered.")
                salt = secrets.token_hex(16)
                try:
                    result = db.execute(
                        "INSERT INTO users(email,salt,password) VALUES(?,?,?)",
                        (email, salt, self.password_hash(password, salt)),
                    )
                except sqlite3.IntegrityError as error:
                    raise HTTPException(409, "Email already registered.") from error
                uid = result.lastrowid
            else:
                # Keep missing-account and incorrect-password work comparable.
                salt = user["salt"] if user else "00" * 16
                candidate = self.password_hash(password, salt)
                if not user or not hmac.compare_digest(candidate, user["password"]):
                    raise HTTPException(401, "Invalid email or password.")
                uid = user["id"]
            token = secrets.token_hex(32)
            db.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (self.digest(token), uid, int(time.time()) + 86400),
            )
            return {"id": uid, "email": email}, token

    def user(self, token):
        with self.connect() as db:
            row = db.execute(
                "SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token=? AND s.expires>?",
                (self.digest(token), int(time.time())),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Please sign in.")
        return dict(row)

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (self.digest(token),))

    def get(self, uid, project_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, uid)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Project not found.")
        return self.serialize(row)

    @staticmethod
    def serialize(row):
        document = json.loads(row["document"])
        return {
            **document,
            "id": row["id"],
            "version": row["version"],
            "updated": row["updated"],
            "plan": plan(ProjectInput.model_validate(document).tasks),
        }

    def list(self, uid):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM projects WHERE user_id=? ORDER BY updated DESC,id", (uid,)
            ).fetchall()
        return [self.serialize(row) for row in rows]

    def save(self, uid, document: ProjectInput, project_id=None):
        payload = document.model_dump(exclude={"version"})
        creating = project_id is None
        project_id = project_id or secrets.token_hex(12)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if creating:
                db.execute(
                    "INSERT INTO projects VALUES(?,?,?,?,?)",
                    (project_id, uid, json.dumps(payload), 1, time.time_ns() // 1_000_000),
                )
            else:
                result = db.execute(
                    "UPDATE projects SET document=?,version=version+1,updated=? WHERE id=? AND user_id=? AND version=?",
                    (
                        json.dumps(payload),
                        time.time_ns() // 1_000_000,
                        project_id,
                        uid,
                        document.version,
                    ),
                )
                if result.rowcount == 0:
                    exists = db.execute(
                        "SELECT 1 FROM projects WHERE id=? AND user_id=?", (project_id, uid)
                    ).fetchone()
                    raise HTTPException(
                        409 if exists else 404,
                        "Project changed. Reload before saving."
                        if exists
                        else "Project not found.",
                    )
            row = db.execute(
                "SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, uid)
            ).fetchone()
        return self.serialize(row)
