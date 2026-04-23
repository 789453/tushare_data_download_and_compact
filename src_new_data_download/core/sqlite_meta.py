from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from .utils import now_iso_utc


class SQLiteMetaStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS dataset_watermark (
                    dataset_name      TEXT PRIMARY KEY,
                    watermark_value   TEXT,
                    watermark_col     TEXT,
                    updated_at        TEXT NOT NULL,
                    note              TEXT
                );

                CREATE TABLE IF NOT EXISTS job_run (
                    job_id            TEXT PRIMARY KEY,
                    job_type          TEXT NOT NULL,
                    dataset_name      TEXT,
                    started_at        TEXT NOT NULL,
                    finished_at       TEXT,
                    status            TEXT NOT NULL,
                    total_tasks       INTEGER DEFAULT 0,
                    done_tasks        INTEGER DEFAULT 0,
                    failed_tasks      INTEGER DEFAULT 0,
                    extra_json        TEXT
                );

                CREATE TABLE IF NOT EXISTS task_run (
                    task_key          TEXT PRIMARY KEY,
                    job_id            TEXT NOT NULL,
                    dataset_name      TEXT NOT NULL,
                    params_json       TEXT NOT NULL,
                    params_hash       TEXT NOT NULL,
                    started_at        TEXT,
                    finished_at       TEXT,
                    status            TEXT NOT NULL,
                    rows_written      INTEGER DEFAULT 0,
                    parquet_path      TEXT,
                    retry_count       INTEGER DEFAULT 0,
                    error_message     TEXT,
                    FOREIGN KEY(job_id) REFERENCES job_run(job_id)
                );

                CREATE TABLE IF NOT EXISTS file_manifest (
                    file_path         TEXT PRIMARY KEY,
                    dataset_name      TEXT NOT NULL,
                    task_key          TEXT,
                    file_kind         TEXT NOT NULL,   -- raw_part/raw_snapshot/silver_export/verify_report
                    row_count         INTEGER,
                    file_size         INTEGER,
                    file_hash         TEXT,
                    created_at        TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verify_run (
                    verify_id         TEXT PRIMARY KEY,
                    dataset_name      TEXT NOT NULL,
                    started_at        TEXT NOT NULL,
                    finished_at       TEXT,
                    status            TEXT NOT NULL,
                    duplicates_cnt    INTEGER DEFAULT 0,
                    missing_cnt       INTEGER DEFAULT 0,
                    invalid_cnt       INTEGER DEFAULT 0,
                    report_json_path  TEXT,
                    report_md_path    TEXT
                );

                CREATE TABLE IF NOT EXISTS dead_letter (
                    dlq_id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_name      TEXT NOT NULL,
                    task_key          TEXT NOT NULL,
                    params_json       TEXT NOT NULL,
                    error_message     TEXT NOT NULL,
                    created_at        TEXT NOT NULL,
                    replay_status     TEXT DEFAULT 'pending'
                );
            """)

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_watermark(self, dataset_name: str) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT watermark_value FROM dataset_watermark WHERE dataset_name = ?",
                (dataset_name,)
            ).fetchone()
            return row["watermark_value"] if row else None

    def update_watermark(self, dataset_name: str, value: str, col: str = "trade_date"):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO dataset_watermark(dataset_name, watermark_value, watermark_col, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(dataset_name) DO UPDATE SET
                    watermark_value = excluded.watermark_value,
                    watermark_col   = excluded.watermark_col,
                    updated_at      = excluded.updated_at
            """, (dataset_name, value, col, now_iso_utc()))

    def is_task_done(self, task_key: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM task_run WHERE task_key = ?",
                (task_key,)
            ).fetchone()
            return row["status"] == "done" if row else False

    def upsert_task_run(self, task_key: str, job_id: str, dataset_name: str, params: dict, params_hash: str, status: str, **kwargs):
        params_json = json.dumps(params, sort_keys=True)
        with self._get_conn() as conn:
            # Check if exists to preserve started_at if it's already set
            existing = conn.execute("SELECT started_at FROM task_run WHERE task_key = ?", (task_key,)).fetchone()
            started_at = existing["started_at"] if existing and existing["started_at"] else (now_iso_utc() if status == "running" else None)
            
            finished_at = now_iso_utc() if status in ("done", "failed") else None
            
            rows_written = kwargs.get("rows_written", 0)
            parquet_path = kwargs.get("parquet_path")
            error_message = kwargs.get("error_message")
            retry_count = kwargs.get("retry_count", 0)

            conn.execute("""
                INSERT INTO task_run(task_key, job_id, dataset_name, params_json, params_hash, started_at, finished_at, status, rows_written, parquet_path, retry_count, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_key) DO UPDATE SET
                    status = excluded.status,
                    finished_at = excluded.finished_at,
                    rows_written = excluded.rows_written,
                    parquet_path = excluded.parquet_path,
                    retry_count = task_run.retry_count + excluded.retry_count,
                    error_message = excluded.error_message
            """, (task_key, job_id, dataset_name, params_json, params_hash, started_at, finished_at, status, rows_written, parquet_path, retry_count, error_message))

    def create_job_run(self, job_id: str, job_type: str, dataset_name: str | None = None, total_tasks: int = 0):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO job_run(job_id, job_type, dataset_name, started_at, status, total_tasks)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (job_id, job_type, dataset_name, now_iso_utc(), "running", total_tasks))

    def update_job_status(self, job_id: str, status: str, **kwargs):
        finished_at = now_iso_utc() if status in ("done", "failed") else None
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE job_run SET 
                    status = ?, 
                    finished_at = ?,
                    done_tasks = COALESCE(?, done_tasks),
                    failed_tasks = COALESCE(?, failed_tasks)
                WHERE job_id = ?
            """, (status, finished_at, kwargs.get("done_tasks"), kwargs.get("failed_tasks"), job_id))

    def record_file(self, file_path: str, dataset_name: str, task_key: str | None, file_kind: str, row_count: int | None = None, file_size: int | None = None, file_hash: str | None = None):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO file_manifest(file_path, dataset_name, task_key, file_kind, row_count, file_size, file_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    row_count = COALESCE(excluded.row_count, row_count),
                    file_size = COALESCE(excluded.file_size, file_size),
                    file_hash = COALESCE(excluded.file_hash, file_hash),
                    created_at = excluded.created_at
            """, (file_path, dataset_name, task_key, file_kind, row_count, file_size, file_hash, now_iso_utc()))
