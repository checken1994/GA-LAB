import uuid
import json
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from scp.contracts.time import now_utc_iso
from scp.knowledge.learning_db import LearningDB

@dataclass
class LessonRecord:
    experiment_refs: List[str]
    insights: List[str]
    lesson_id: str = ""
    knowledge_updates: List[Dict[str, Any]] = field(default_factory=list)
    capability_updates: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.lesson_id:
            self.lesson_id = f"lsn_{uuid.uuid4().hex}"
        if not self.created_at:
            self.created_at = now_utc_iso()

class LessonAuthority:
    """
    P1-10 Lesson Learned Authority.
    Converts experiment results into durable insights and updates for knowledge/capabilities.
    """
    def __init__(self, db: LearningDB):
        self.db = db
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS lessons (
                    lesson_id TEXT PRIMARY KEY,
                    experiment_refs_json TEXT NOT NULL,
                    insights_json TEXT,
                    knowledge_updates_json TEXT,
                    capability_updates_json TEXT,
                    created_at TEXT
                );
            """)

    def record_lesson(self, record: LessonRecord) -> str:
        data = {
            "lesson_id": record.lesson_id,
            "experiment_refs_json": json.dumps(record.experiment_refs),
            "insights_json": json.dumps(record.insights),
            "knowledge_updates_json": json.dumps(record.knowledge_updates),
            "capability_updates_json": json.dumps(record.capability_updates),
            "created_at": record.created_at
        }
        self.db.execute_insert("lessons", data)
        return record.lesson_id
