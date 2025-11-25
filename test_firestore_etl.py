#!/usr/bin/env python3
"""
Test script to diagnose Firestore ETL issues.
This will extract data locally and show exactly what's wrong.
"""

import os
import sys
import django
import json
import pandas as pd
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'b2b_recs.settings')
sys.path.insert(0, '/Users/dkulish/Projects/b2b_recs')
sys.path.insert(0, '/Users/dkulish/Projects/b2b_recs/etl_runner')
django.setup()

from ml_platform.models import DataSource
from ml_platform.utils.connection_manager import get_credentials_from_secret_manager


def test_firestore_extraction(data_source_id):
    """Test Firestore extraction and identify the bug"""

    print("="*80)
    print("FIRESTORE ETL DIAGNOSTIC TEST")
    print("="*80)

    # Get data source
    data_source = DataSource.objects.get(id=data_source_id)
    connection = data_source.connection
    table = data_source.tables.first()

    print(f"\n✓ Data Source: {data_source.name}")
    print(f"✓ Collection: {table.source_table_name}")

    # Get credentials
    credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

    # Setup Firestore extractor
    from extractors.firestore import FirestoreExtractor

    connection_params = {
        'source_type': 'firestore',
        'project_id': connection.bigquery_project,
        'credentials': {'service_account_json': json.dumps(credentials)}
    }

    extractor = FirestoreExtractor(connection_params)

    print(f"✓ Firestore client initialized")

    # Extract just a few documents
    print(f"\n{'='*80}")
    print("EXTRACTING SAMPLE DOCUMENTS")
    print("="*80)

    collection_ref = extractor._db.collection(table.source_table_name)
    docs = list(collection_ref.limit(3).stream())

    print(f"\n✓ Retrieved {len(docs)} sample documents")

    # Analyze each document
    for i, doc in enumerate(docs, 1):
        print(f"\n--- Document {i}: {doc.id} ---")
        doc_dict = doc.to_dict()

        for field_name, field_value in doc_dict.items():
            field_type = type(field_value).__name__

            # Check for problematic types
            if isinstance(field_value, (list, dict)):
                print(f"  ❌ {field_name}: {field_type} = {field_value}")
            elif hasattr(field_value, 'seconds') and hasattr(field_value, 'nanos'):
                print(f"  ⚠️  {field_name}: Firestore Timestamp (seconds={field_value.seconds})")
            elif hasattr(field_value, 'isoformat'):
                print(f"  ✓ {field_name}: datetime = {field_value.isoformat()}")
            else:
                value_preview = str(field_value)[:50]
                print(f"  ✓ {field_name}: {field_type} = {value_preview}")

    # Test flattening
    print(f"\n{'='*80}")
    print("TESTING DOCUMENT FLATTENING")
    print("="*80)

    flat_doc = extractor._flatten_document(docs[0], [])

    print("\nFlattened document field types:")
    for field_name, field_value in flat_doc.items():
        field_type = type(field_value).__name__

        if isinstance(field_value, (list, dict)):
            print(f"  ❌ PROBLEM: {field_name} is still {field_type}!")
            print(f"     Value: {field_value}")
        else:
            value_preview = str(field_value)[:50]
            print(f"  ✓ {field_name}: {field_type} = {value_preview}")

    # Test DataFrame creation
    print(f"\n{'='*80}")
    print("TESTING DATAFRAME CREATION")
    print("="*80)

    rows = [extractor._flatten_document(doc, []) for doc in docs]
    df = pd.DataFrame(rows)

    print(f"\n✓ DataFrame created: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"\nColumn dtypes:")

    for col in df.columns:
        dtype = df[col].dtype
        sample_value = df[col].iloc[0]
        sample_type = type(sample_value).__name__

        # Check if values are actually lists/dicts
        has_complex = df[col].apply(lambda x: isinstance(x, (list, dict))).any()

        if has_complex:
            print(f"  ❌ PROBLEM: {col}: dtype={dtype}, but contains {sample_type} values!")
            print(f"     Sample: {sample_value}")
        elif dtype == 'object':
            print(f"  ⚠️  {col}: dtype={dtype}, sample_type={sample_type}")
        else:
            print(f"  ✓ {col}: dtype={dtype}")

    # Test PyArrow conversion
    print(f"\n{'='*80}")
    print("TESTING PYARROW CONVERSION")
    print("="*80)

    try:
        import pyarrow as pa
        table = pa.Table.from_pandas(df)
        print("✓ PyArrow conversion SUCCESS!")
    except Exception as e:
        print(f"❌ PyArrow conversion FAILED: {e}")

        # Try converting object columns to string
        print("\nAttempting fix: Converting object columns to string...")
        df_fixed = df.copy()
        for col in df_fixed.select_dtypes(include=['object']).columns:
            df_fixed[col] = df_fixed[col].astype(str)

        try:
            table = pa.Table.from_pandas(df_fixed)
            print("✓ PyArrow conversion SUCCESS after string conversion!")
        except Exception as e2:
            print(f"❌ Still failed: {e2}")

            # More aggressive fix
            print("\nAttempting aggressive fix: Force convert all values...")
            for col in df_fixed.columns:
                if df_fixed[col].apply(lambda x: isinstance(x, (list, dict))).any():
                    print(f"  Converting {col} (contains lists/dicts)")
                    df_fixed[col] = df_fixed[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else str(x))
                else:
                    df_fixed[col] = df_fixed[col].astype(str)

            try:
                table = pa.Table.from_pandas(df_fixed)
                print("✓ PyArrow conversion SUCCESS after aggressive conversion!")
            except Exception as e3:
                print(f"❌ Still failed: {e3}")

    print(f"\n{'='*80}")
    print("TEST COMPLETE")
    print("="*80)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_firestore_etl.py <data_source_id>")
        sys.exit(1)

    data_source_id = int(sys.argv[1])
    test_firestore_extraction(data_source_id)
