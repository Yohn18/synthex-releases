# -*- coding: utf-8 -*-
"""
modules/agents/memory.py
Shared SQLite memory untuk semua agent dalam satu session.
"""
import os
import json
import sqlite3
import time
import threading

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "agents_memory.db")


class AgentMemory:
    def __init__(self, db_path: str = None):
        self._path = db_path or _DB_PATH
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._path, check_same_thread=False)

    def _init_db(self):
        with self._lock:
            c = self._conn()
            c.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    session   TEXT    NOT NULL,
                    agent     TEXT    NOT NULL,
                    role      TEXT    NOT NULL,
                    content   TEXT    NOT NULL,
                    msg_type  TEXT    DEFAULT 'response',
                    model     TEXT    DEFAULT '',
                    ts        REAL    NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id       TEXT PRIMARY KEY,
                    task     TEXT,
                    result   TEXT,
                    created  REAL,
                    finished REAL
                )
            """)
            c.commit()
            c.close()

    def new_session(self, task: str) -> str:
        session_id = "s_{:.0f}".format(time.time())
        with self._lock:
            c = self._conn()
            c.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                      (session_id, task, "", time.time(), None))
            c.commit()
            c.close()
        return session_id

    def store(self, session_id: str, agent: str, role: str,
              content: str, msg_type: str = "response", model: str = ""):
        with self._lock:
            c = self._conn()
            c.execute(
                "INSERT INTO messages (session,agent,role,content,msg_type,model,ts) "
                "VALUES (?,?,?,?,?,?,?)",
                (session_id, agent, role, content, msg_type, model, time.time())
            )
            c.commit()
            c.close()

    def get_context(self, session_id: str, limit: int = 20) -> list:
        with self._lock:
            c = self._conn()
            rows = c.execute(
                "SELECT agent,role,content,msg_type,model FROM messages "
                "WHERE session=? ORDER BY ts DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
            c.close()
        return [{"agent": r[0], "role": r[1], "content": r[2],
                 "msg_type": r[3], "model": r[4]} for r in reversed(rows)]

    def finish_session(self, session_id: str, result: str):
        with self._lock:
            c = self._conn()
            c.execute("UPDATE sessions SET result=?, finished=? WHERE id=?",
                      (result, time.time(), session_id))
            c.commit()
            c.close()

    def get_sessions(self, limit: int = 10) -> list:
        with self._lock:
            c = self._conn()
            rows = c.execute(
                "SELECT id,task,result,created,finished FROM sessions "
                "ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()
            c.close()
        return [{"id": r[0], "task": r[1], "result": r[2],
                 "created": r[3], "finished": r[4]} for r in rows]
