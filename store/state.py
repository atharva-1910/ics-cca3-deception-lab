"""Consistency store — the single source of truth for fake host state.

HANDOVER §7.1, §10.5, §11.1. One SQLite database shared by every decoy; all rows
scoped by ``host_id``. Decoys never hold state themselves — they forward to the
engine, which reads and writes here.

Design notes:
  * Directories are represented as ``files`` rows whose ``mode`` starts with 'd'.
  * ``write_back`` rejects writes that contradict an existing non-planted row
    (HANDOVER §10.5 "reject writes that contradict existing rows"), so an LLM
    cannot overwrite an established fact and create a contradiction.
  * Snapshots are whole-file copies (HANDOVER §10.5 "restore snapshot resets
    state"); the live DB is git-ignored, snapshots under store/snapshots/ are not.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SNAPSHOT_DIR = Path(__file__).with_name("snapshots")
DEFAULT_DB = Path(__file__).with_name("state.db")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(path: str) -> str:
    """Normalise an absolute-ish path without touching the real filesystem."""
    if not path.startswith("/"):
        path = "/" + path
    # collapse // and trailing / (except root)
    parts: list[str] = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts)


class Contradiction(Exception):
    """Raised when a write would overwrite an established (non-planted) fact."""


class Store:
    def __init__(self, db_path: os.PathLike | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    # ------------------------------------------------------------------ schema
    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA_PATH.read_text())
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self):
        """All-or-nothing write block (HANDOVER §6.5 'writes all hops in one transaction')."""
        try:
            yield self
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def commit(self) -> None:
        self.conn.commit()

    # ------------------------------------------------------------------- hosts
    def add_host(self, host_id, ip, hostname, os_="Ubuntu 22.04",
                 persona="generic linux server", gen_type="llm_store") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO hosts(host_id,ip,hostname,os,persona,gen_type) "
            "VALUES (?,?,?,?,?,?)",
            (host_id, ip, hostname, os_, persona, gen_type),
        )

    def get_host(self, host_id) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM hosts WHERE host_id=?", (host_id,)).fetchone()

    def get_host_by_ip(self, ip) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM hosts WHERE ip=?", (ip,)).fetchone()

    def set_hostname(self, host_id, hostname) -> None:
        self.conn.execute(
            "UPDATE hosts SET hostname=? WHERE host_id=?", (hostname, host_id))

    # ------------------------------------------------------------------- files
    def write_file(self, host_id, path, content, owner="root", mode="0644",
                   mtime=None, planted=0, enforce=False) -> None:
        """Insert or replace a file row.

        If ``enforce`` is True, refuse to change the content of an existing
        non-planted file (used for LLM write-back; the generator writes with
        ``enforce=False`` inside its single transaction).
        """
        path = _norm(path)
        if enforce:
            row = self.read_file(host_id, path)
            if row is not None and row["planted"] == 0 and row["content"] != content:
                raise Contradiction(f"{host_id}:{path} already exists with different content")
        self.conn.execute(
            "INSERT OR REPLACE INTO files(host_id,path,content,owner,mode,mtime,planted) "
            "VALUES (?,?,?,?,?,?,?)",
            (host_id, path, content, owner, mode, mtime or _now(), planted),
        )

    def mkdir(self, host_id, path, owner="root", mode="d0755", planted=0) -> None:
        self.write_file(host_id, path, "", owner=owner, mode=mode, planted=planted)

    def read_file(self, host_id, path) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM files WHERE host_id=? AND path=?",
            (host_id, _norm(path))).fetchone()

    def remove_file(self, host_id, path) -> int:
        cur = self.conn.execute(
            "DELETE FROM files WHERE host_id=? AND path=?", (host_id, _norm(path)))
        return cur.rowcount

    def list_dir(self, host_id, dirpath) -> list[sqlite3.Row]:
        """Immediate children of ``dirpath`` (one path segment deeper)."""
        dirpath = _norm(dirpath)
        prefix = "/" if dirpath == "/" else dirpath + "/"
        rows = self.conn.execute(
            "SELECT * FROM files WHERE host_id=? AND path LIKE ? AND path != ?",
            (host_id, prefix + "%", dirpath)).fetchall()
        seen: dict[str, sqlite3.Row] = {}
        for r in rows:
            rest = r["path"][len(prefix):]
            if not rest:
                continue
            first = rest.split("/")[0]
            if first not in seen:
                seen[first] = r
        return [seen[k] for k in sorted(seen)]

    def all_files(self, host_id) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM files WHERE host_id=? ORDER BY path", (host_id,)).fetchall()

    # ------------------------------------------------------------------- users
    def add_user(self, host_id, username, password, uid=1000, shell="/bin/bash",
                 home=None, planted=0) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO users(host_id,username,uid,password,shell,home,planted) "
            "VALUES (?,?,?,?,?,?,?)",
            (host_id, username, uid, password, shell, home or f"/home/{username}", planted),
        )

    def get_user(self, host_id, username) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE host_id=? AND username=?",
            (host_id, username)).fetchone()

    def check_password(self, host_id, username, password) -> bool:
        row = self.get_user(host_id, username)
        return row is not None and row["password"] == password

    def list_users(self, host_id) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE host_id=? ORDER BY uid", (host_id,)).fetchall()

    # ------------------------------------------------------------------- procs
    def add_proc(self, host_id, pid, user, cmd) -> None:
        self.conn.execute(
            "INSERT INTO procs(host_id,pid,user,cmd) VALUES (?,?,?,?)",
            (host_id, pid, user, cmd))

    def list_procs(self, host_id) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM procs WHERE host_id=? ORDER BY pid", (host_id,)).fetchall()

    # ----------------------------------------------------------------- history
    def add_history(self, host_id, session_id, command, response, ts=None) -> None:
        self.conn.execute(
            "INSERT INTO history(host_id,session_id,ts,command,response) VALUES (?,?,?,?,?)",
            (host_id, session_id, ts or _now(), command, response))

    def get_history(self, host_id, session_id=None, limit=100) -> list[sqlite3.Row]:
        if session_id is None:
            return self.conn.execute(
                "SELECT * FROM history WHERE host_id=? ORDER BY rowid DESC LIMIT ?",
                (host_id, limit)).fetchall()[::-1]
        return self.conn.execute(
            "SELECT * FROM history WHERE host_id=? AND session_id=? ORDER BY rowid DESC LIMIT ?",
            (host_id, session_id, limit)).fetchall()[::-1]

    # ---------------------------------------------------------------- snapshots
    def snapshot(self, name="base") -> Path:
        self.conn.commit()
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        dest = SNAPSHOT_DIR / f"{name}.db"
        shutil.copyfile(self.db_path, dest)
        return dest

    def restore(self, name="base") -> None:
        src = SNAPSHOT_DIR / f"{name}.db"
        if not src.exists():
            raise FileNotFoundError(src)
        self.conn.close()
        shutil.copyfile(src, self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------------ helpers
    def snapshot_summary(self, host_id, cwd="/") -> dict:
        """Compact store slice handed to the LLM prompt (HANDOVER §7.2 step 4)."""
        host = self.get_host(host_id)
        return {
            "host": dict(host) if host else {"host_id": host_id},
            "cwd_listing": [
                {"name": r["path"].rsplit("/", 1)[-1],
                 "mode": r["mode"], "owner": r["owner"]}
                for r in self.list_dir(host_id, cwd)
            ],
            "users": [r["username"] for r in self.list_users(host_id)],
            "recent_history": [r["command"] for r in self.get_history(host_id, limit=10)],
        }


def fresh(db_path: os.PathLike | str = DEFAULT_DB) -> Store:
    """Create a brand-new empty store (dropping any existing DB file)."""
    p = Path(db_path)
    if p.exists():
        p.unlink()
    s = Store(p)
    s.init_schema()
    return s
