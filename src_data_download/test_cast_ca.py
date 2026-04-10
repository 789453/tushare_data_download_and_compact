import pyarrow as pa
import pyarrow.compute as pc

val = 17409151
arr = pa.array([val], type=pa.int64())
ca = pa.chunked_array([arr])
print(f"Value: {val}")
try:
    print("Casting ChunkedArray with safe=True...")
    res = pc.cast(ca, pa.float32(), safe=True)
    print(f"Result: {res}")
except Exception as e:
    print(f"Safe cast failed: {e}")

try:
    print("\nCasting ChunkedArray with safe=False...")
    res = pc.cast(ca, pa.float32(), safe=False)
    print(f"Result: {res}")
except Exception as e:
    print(f"Unsafe cast failed: {e}")
