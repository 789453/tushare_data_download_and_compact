import pyarrow.parquet as pq
import pyarrow as pa
from pathlib import Path

# This mimics the logic in ts_download_utils.py
def test_repro():
    fp_first = r'd:\Trading\data_ever_26_3_14\data\Raw_data\moneyflow.parquet' # The existing big one
    fp_fail = r'd:\Trading\data_ever_26_3_14\data\Raw_data\moneyflow_2010_parts\20150708_o00000.parquet'
    
    print(f"Reading first file schema: {fp_first}")
    table_first = pq.read_table(fp_first)
    target_schema = table_first.schema
    
    # Simulating downcast_floats=True
    new_fields = []
    for field in target_schema:
        if field.type == pa.float64():
            new_fields.append(pa.field(field.name, pa.float32(), nullable=field.nullable))
        else:
            new_fields.append(field)
    target_schema = pa.schema(new_fields)
    print("Target schema initialized (float64 -> float32)")

    print(f"\nReading problematic file: {fp_fail}")
    table_fail = pq.read_table(fp_fail)
    
    print("Aligning schema...")
    new_columns = []
    for field in target_schema:
        if field.name in table_fail.column_names:
            col = table_fail.column(field.name)
            if not col.type.equals(field.type):
                print(f"Casting column {field.name}: {col.type} -> {field.type}")
                import pyarrow.compute as pc
                # In ts_download_utils.py, this is pc.cast(col, field.type, safe=False)
                # Wait! I might have used table.cast in some older version?
                col = pc.cast(col, field.type, safe=False)
            new_columns.append(col)
        else:
            new_columns.append(pa.array([None] * table_fail.num_rows, type=field.type))
    
    table_final = pa.Table.from_arrays(new_columns, schema=target_schema)
    print("Success!")

if __name__ == "__main__":
    try:
        test_repro()
    except Exception as e:
        print(f"Repro failed: {e}")
