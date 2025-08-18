import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  peer_type TEXT NOT NULL,     -- 'user' hoặc 'room'
  peer_id   TEXT NOT NULL,
  direction TEXT NOT NULL,     -- 'in' hoặc 'out'
  msg_type  TEXT NOT NULL,     -- 'text' hoặc 'image'
  content   TEXT,              -- text hoặc base64 ảnh
  ts        INTEGER            -- epoch ms
);
"""

class Storage:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def save_message(self, peer_type: str, peer_id: str, direction: str, msg_type: str, content: str, ts: int):
        self.conn.execute(
            "INSERT INTO messages(peer_type, peer_id, direction, msg_type, content, ts) VALUES (?,?,?,?,?,?)",
            (peer_type, peer_id, direction, msg_type, content, ts),
        )
        self.conn.commit()

    def search(self, peer_type: Optional[str], peer_id: Optional[str], keyword: Optional[str], ts_range: Optional[Tuple[int, int]]) -> List[tuple]:
        q = "SELECT peer_type, peer_id, direction, msg_type, content, ts FROM messages WHERE 1=1"
        params: list = []
        if peer_type:
            q += " AND peer_type=?"; params.append(peer_type)
        if peer_id:
            q += " AND peer_id=?"; params.append(peer_id)
        if keyword:
            q += " AND msg_type='text' AND content LIKE ?"; params.append(f"%{keyword}%")
        if ts_range:
            q += " AND ts BETWEEN ? AND ?"; params.extend(list(ts_range))
        q += " ORDER BY ts DESC LIMIT 200"
        cur = self.conn.execute(q, params)
        return cur.fetchall()