import pyarrow.parquet as pq
import pyarrow as pa
import pyarrow.compute as pc
from pathlib import Path

fp = r'd:\Trading\data_ever_26_3_14\data\Raw_data\moneyflow_2010_parts\20150708_o00000.parquet'
print(f"Testing {fp}")
try:
    table = pq.read_table(fp)
    print("Read table success")
    
    # Try to downcast schema
    new_fields = []
    for field in table.schema:
        if field.type == pa.float64() or field.type == pa.int64():
            new_fields.append(pa.field(field.name, pa.float32(), nullable=field.nullable))
        else:
            new_fields.append(field)
    target_schema = pa.schema(new_fields)
    
    print("Trying to cast with safe=True...")
    try:
        t2 = table.cast(target_schema, safe=True)
        print("Cast success (safe=True)")
    except Exception as e:
        print(f"Cast failed (safe=True): {e}")

    print("\nTrying to cast with safe=False...")
    try:
        t2 = table.cast(target_schema, safe=False)
        print("Cast success (safe=False)")
    except Exception as e:
        print(f"Cast failed (safe=False): {e}")

except Exception as e:
    print(f"Failed: {e}")
