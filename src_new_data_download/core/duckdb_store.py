from __future__ import annotations

from pathlib import Path

import duckdb
import threading

from .dataset_spec import DatasetSpec


class DuckDBStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with duckdb.connect(str(self.db_path)) as conn:
                conn.execute("CREATE SCHEMA IF NOT EXISTS raw_ext;")
                conn.execute("CREATE SCHEMA IF NOT EXISTS silver;")
                conn.execute("CREATE SCHEMA IF NOT EXISTS audit;")

    def merge_incremental(self, spec: DatasetSpec, parquet_paths: list[str]):
        if not parquet_paths:
            return

        table_name = f"silver.fact_{spec.name}"
        pk_cols = spec.pk_cols
        pk_join_clause = " AND ".join([f"t.{c} = s.{c}" for c in pk_cols])
        
        # Paths string for read_parquet
        paths_str = ", ".join([f"'{p}'" for p in parquet_paths])

        with self._lock:
            with duckdb.connect(str(self.db_path)) as conn:
                # 1. Ensure target table exists (schema only if not exists)
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM read_parquet([{paths_str}], union_by_name=True) LIMIT 0")
                
                # 2. Use a temp table for staging
                conn.execute(f"CREATE OR REPLACE TEMP TABLE stage AS SELECT * FROM read_parquet([{paths_str}], union_by_name=True)")
                
                # 3. Construct MERGE clauses
                cols_info = conn.execute("DESCRIBE stage").fetchall()
                all_cols = [c[0] for c in cols_info]
                update_cols = [c for c in all_cols if c not in pk_cols]
                
                if not update_cols:
                    # All columns are PKs, just insert missing
                    conn.execute(f"""
                        INSERT INTO {table_name}
                        SELECT s.* FROM stage s
                        LEFT JOIN {table_name} t ON {pk_join_clause}
                        WHERE t.{pk_cols[0]} IS NULL
                    """)
                else:
                    update_set_clause = ", ".join([f"{c} = s.{c}" for c in update_cols])
                    insert_cols_str = ", ".join(all_cols)
                    insert_vals_str = ", ".join([f"s.{c}" for c in all_cols])
                    
                    # 4. DuckDB MERGE INTO
                    conn.execute(f"""
                        MERGE INTO {table_name} t
                        USING stage s ON {pk_join_clause}
                        WHEN MATCHED THEN UPDATE SET {update_set_clause}
                        WHEN NOT MATCHED THEN INSERT ({insert_cols_str}) VALUES ({insert_vals_str})
                    """)

    def export_silver_parquet(self, spec: DatasetSpec, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        table_name = f"silver.fact_{spec.name}"
        with self._lock:
            with duckdb.connect(str(self.db_path)) as conn:
                conn.execute(f"COPY (SELECT * FROM {table_name}) TO '{output_path}' (FORMAT parquet)")

    def query(self, sql: str):
        with self._lock:
            with duckdb.connect(str(self.db_path)) as conn:
                return conn.execute(sql).df()
