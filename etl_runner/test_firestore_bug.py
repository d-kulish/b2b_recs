#!/usr/bin/env python3
"""
Simplified test to identify the Firestore PyArrow bug.
"""

import pandas as pd
from datetime import datetime
import json

print("="*80)
print("FIRESTORE PYARROW BUG DIAGNOSIS")
print("="*80)

# Simulate what Firestore returns
class FirestoreTimestamp:
    """Mock Firestore timestamp object"""
    def __init__(self):
        self.seconds = 1732540800
        self.nanos = 123456789

    def __repr__(self):
        return f"Timestamp(seconds={self.seconds}, nanos={self.nanos})"


# Test data simulating Firestore document
firestore_doc = {
    'id': '123',
    'name': 'Test Document',
    'last_modified': FirestoreTimestamp(),  # This is the problem
    'tags': ['tag1', 'tag2'],  # Array
    'metadata': {'key': 'value'}  # Object
}

print("\n1. RAW FIRESTORE DOCUMENT:")
for k, v in firestore_doc.items():
    print(f"  {k}: {type(v).__name__} = {v}")

# Current flattening logic (simplified from firestore.py)
def flatten_document_current(doc):
    """Current flattening logic"""
    flat_doc = {}

    for field_name, field_value in doc.items():
        if field_value is None:
            flat_doc[field_name] = None
        elif isinstance(field_value, (str, int, float, bool)):
            flat_doc[field_name] = field_value
        elif isinstance(field_value, datetime):
            flat_doc[field_name] = field_value.isoformat()
        elif isinstance(field_value, (list, dict)):
            flat_doc[field_name] = json.dumps(field_value)
        else:
            # Fallback for unknown types (Firestore timestamps)
            if hasattr(field_value, 'seconds') and hasattr(field_value, 'nanos'):
                ts = datetime.utcfromtimestamp(field_value.seconds + field_value.nanos / 1e9)
                flat_doc[field_name] = ts.isoformat()
            else:
                flat_doc[field_name] = str(field_value)

    return flat_doc

print("\n2. FLATTENED DOCUMENT:")
flat = flatten_document_current(firestore_doc)
for k, v in flat.items():
    print(f"  {k}: {type(v).__name__} = {v}")

# Create DataFrame
print("\n3. DATAFRAME CREATION:")
df = pd.DataFrame([flat])
print(f"  Shape: {df.shape}")
print(f"\n  Dtypes:")
for col in df.columns:
    print(f"    {col}: {df[col].dtype}")

# Test PyArrow conversion
print("\n4. PYARROW CONVERSION TEST:")
try:
    import pyarrow as pa
    table = pa.Table.from_pandas(df)
    print("  ✓ SUCCESS - PyArrow conversion worked!")
except Exception as e:
    print(f"  ❌ FAILED: {e}")

    # Try fix: convert object columns to string
    print("\n5. ATTEMPTING FIX: Convert object dtypes to string")
    df_fixed = df.copy()
    for col in df_fixed.select_dtypes(include=['object']).columns:
        print(f"  Converting column: {col}")
        df_fixed[col] = df_fixed[col].astype(str)

    try:
        table = pa.Table.from_pandas(df_fixed)
        print("  ✓ SUCCESS after dtype conversion!")
    except Exception as e2:
        print(f"  ❌ Still failed: {e2}")

print("\n" + "="*80)
print("DIAGNOSIS COMPLETE")
print("="*80)
