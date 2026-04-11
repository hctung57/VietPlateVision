from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DetectionRecord:
    """Represent one license plate detection record; example: DetectionRecord(id=1, timestamp='2026-04-11T10:00:00Z', source_type='image', source_name='1.jpg', plate_text='51A-12345', confidence=0.92, edge=0.42, crop_path='data:image/jpeg;base64,...', frame_index=0)."""

    id: int
    timestamp: str
    source_type: str
    source_name: str
    plate_text: str
    confidence: float
    edge: float
    crop_path: str
    frame_index: int


class HistoryStore:
    """Manage detection history in SQLite; example: store = HistoryStore(Path('storage/history.db'))."""

    def __init__(self, database_path: Path) -> None:
        self.database_path: Path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """Create a SQLite connection; example: connection = self._connect()."""

        connection: sqlite3.Connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        """Initialize history table when missing; example: self._initialize_schema()."""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS detection_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    plate_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    edge REAL NOT NULL,
                    crop_path TEXT NOT NULL,
                    frame_index INTEGER NOT NULL
                )
                """
            )
            connection.commit()

    def insert_detection(
        self,
        timestamp: str,
        source_type: str,
        source_name: str,
        plate_text: str,
        confidence: float,
        edge: float,
        crop_path: str,
        frame_index: int,
    ) -> int:
        """Store one detection record and return id; example: detection_id = store.insert_detection(...)."""

        with self._connect() as connection:
            cursor: sqlite3.Cursor = connection.execute(
                """
                INSERT INTO detection_history (
                    timestamp,
                    source_type,
                    source_name,
                    plate_text,
                    confidence,
                    edge,
                    crop_path,
                    frame_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    source_type,
                    source_name,
                    plate_text,
                    confidence,
                    edge,
                    crop_path,
                    frame_index,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_detections(self, limit: int = 200) -> list[DetectionRecord]:
        """Get latest detections; example: rows = store.list_detections(limit=100)."""

        with self._connect() as connection:
            rows: list[sqlite3.Row] = connection.execute(
                """
                SELECT
                    id,
                    timestamp,
                    source_type,
                    source_name,
                    plate_text,
                    confidence,
                    edge,
                    crop_path,
                    frame_index
                FROM detection_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_record(row) for row in rows]

    def get_detection(self, detection_id: int) -> DetectionRecord | None:
        """Get one detection by id; example: item = store.get_detection(10)."""

        with self._connect() as connection:
            row: sqlite3.Row | None = connection.execute(
                """
                SELECT
                    id,
                    timestamp,
                    source_type,
                    source_name,
                    plate_text,
                    confidence,
                    edge,
                    crop_path,
                    frame_index
                FROM detection_history
                WHERE id = ?
                """,
                (detection_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DetectionRecord:
        """Map a sqlite row to dataclass; example: record = self._row_to_record(row)."""

        return DetectionRecord(
            id=int(row["id"]),
            timestamp=str(row["timestamp"]),
            source_type=str(row["source_type"]),
            source_name=str(row["source_name"]),
            plate_text=str(row["plate_text"]),
            confidence=float(row["confidence"]),
            edge=float(row["edge"]),
            crop_path=str(row["crop_path"]),
            frame_index=int(row["frame_index"]),
        )

    @staticmethod
    def serialize(record: DetectionRecord) -> dict[str, Any]:
        """Convert dataclass to JSON-ready dict; example: payload = HistoryStore.serialize(record)."""

        return {
            "id": record.id,
            "timestamp": record.timestamp,
            "source_type": record.source_type,
            "source_name": record.source_name,
            "plate_text": record.plate_text,
            "confidence": record.confidence,
            "edge": record.edge,
            "crop_path": record.crop_path,
            "frame_index": record.frame_index,
        }
