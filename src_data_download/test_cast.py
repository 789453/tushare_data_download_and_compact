import pyarrow as pa
import pyarrow.compute as pc

val = 17409151
arr = pa.array([val], type=pa.int64())
print(f"Value: {val}")
try:
    print("Casting with safe=True...")
    res = pc.cast(arr, pa.float32(), safe=True)
    print(f"Result: {res}")
except Exception as e:
    print(f"Safe cast failed: {e}")

try:
    print("\nCasting with safe=False...")
    res = pc.cast(arr, pa.float32(), safe=False)
    print(f"Result: {res}")
except Exception as e:
    print(f"Unsafe cast failed: {e}")
