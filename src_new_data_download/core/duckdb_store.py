from __future__ import annotations

from pathlib import Path

import duckdb

from .dataset_spec import DatasetSpec


class DuckDBStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS raw_ext;")
            conn.execute("CREATE SCHEMA IF NOT EXISTS silver;")
            conn.execute("CREATE SCHEMA IF NOT EXISTS audit;")

    def merge_incremental(self, spec: DatasetSpec, parquet_paths: list[str]):
        if not parquet_paths:
            return

        table_name = f"silver.fact_{spec.name}"
        pk_str = ", ".join(spec.pk_cols)
        
        # Create table if not exists
        with duckdb.connect(str(self.db_path)) as conn:
            # Check if table exists
            res = conn.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_schema = 'silver' AND table_name = 'fact_{spec.name}'").fetchone()
            if res[0] == 0:
                # Initial load
                paths_str = ", ".join([f"'{p}'" for p in parquet_paths])
                conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet([{paths_str}], union_by_name=True)")
            else:
                # Incremental merge
                paths_str = ", ".join([f"'{p}'" for p in parquet_paths])
                # Use a temp table for staging
                conn.execute("CREATE OR REPLACE TEMP TABLE stage AS SELECT * FROM read_parquet([{}], union_by_name=True)".format(paths_str))
                
                # DuckDB MERGE INTO
                # We need to construct the update clause dynamically based on columns
                cols = conn.execute("DESCRIBE stage").fetchall()
                col_names = [c[0] for c in cols if c[0] not in spec.pk_cols]
                update_clause = ", ".join([f"{c} = excluded.{c}" for c in col_names])
                
                conn.execute(f"""
                    INSERT INTO {table_name} 
                    SELECT * FROM stage
                    ON CONFLICT ({pk_str}) DO UPDATE SET {update_clause}
                """)

    def export_silver_parquet(self, spec: DatasetSpec, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        table_name = f"silver.fact_{spec.name}"
        with duckdb.connect(str(self.db_path)) as conn:
            conn.execute(f"COPY (SELECT * FROM {table_name}) TO '{output_path}' (FORMAT parquet)")

    def query(self, sql: str):
        with duckdb.connect(str(self.db_path)) as conn:
            return conn.execute(sql).df()
