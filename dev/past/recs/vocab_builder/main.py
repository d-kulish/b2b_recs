#!/usr/bin/env python3
"""VocabBuilder Component with Product Metadata - Builds vocabularies from TFRecord files with product features"""

import argparse
import logging
import os
import json
from typing import Dict, List, Set, Any
from collections import Counter

import numpy as np
import tensorflow as tf

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_tfrecord_example(example_proto: bytes) -> Dict[str, Any]:
    """Parse TFRecord example with product metadata features."""
    
    feature_description = {
        # Original features
        'cust_person_id': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'product_id': tf.io.FixedLenFeature([], tf.int64, default_value=0),
        'revenue': tf.io.FixedLenFeature([], tf.float32, default_value=0.0),
        'city': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'timestamp': tf.io.FixedLenFeature([], tf.int64, default_value=0),
        # New product metadata features
        'art_name': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'stratbuy_domain_desc': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'mge_main_cat_desc': tf.io.FixedLenFeature([], tf.string, default_value=''),
    }
    
    return tf.io.parse_single_example(example_proto, feature_description)


def extract_vocabularies_from_tfrecords(tfrecord_pattern: str) -> Dict[str, Any]:
    """Extract vocabularies from TFRecord files with product metadata."""
    
    logger.info(f"Reading TFRecord files from pattern: {tfrecord_pattern}")
    logger.info("NOTE: Processing COMPLETE DATASET with PRODUCT METADATA for vocabulary building")
    
    # Handle both single patterns and comma-separated patterns
    if ',' in tfrecord_pattern:
        # Handle comma-separated patterns (e.g., multiple splits or explicit files)
        patterns = tfrecord_pattern.split(',')
        tfrecord_files = []
        for pattern in patterns:
            pattern = pattern.strip()
            # Check if it's an explicit file path (no wildcards) or a glob pattern
            if '*' in pattern or '?' in pattern:
                # It's a glob pattern
                files = tf.io.gfile.glob(pattern)
                if files:
                    tfrecord_files.extend(files)
                    logger.info(f"Found {len(files)} files for glob pattern: {pattern}")
            else:
                # It's an explicit file path
                if tf.io.gfile.exists(pattern):
                    tfrecord_files.append(pattern)
                    logger.info(f"Added explicit file: {pattern}")
                else:
                    logger.warning(f"Explicit file not found: {pattern}")
    else:
        # Handle single pattern (all_data folder approach)
        if '*' in tfrecord_pattern or '?' in tfrecord_pattern:
            # It's a glob pattern
            tfrecord_files = tf.io.gfile.glob(tfrecord_pattern)
            logger.info(f"Processing glob pattern: {tfrecord_pattern}")
        else:
            # It's an explicit file path
            if tf.io.gfile.exists(tfrecord_pattern):
                tfrecord_files = [tfrecord_pattern]
                logger.info(f"Processing explicit file: {tfrecord_pattern}")
            else:
                tfrecord_files = []
                logger.error(f"Explicit file not found: {tfrecord_pattern}")
    
    if not tfrecord_files:
        raise ValueError(f"No TFRecord files found matching pattern: {tfrecord_pattern}")
    
    logger.info(f"Total TFRecord files found: {len(tfrecord_files)}")
    
    # Create dataset with compression handling
    dataset = tf.data.TFRecordDataset(
        tfrecord_files,
        compression_type='GZIP'  # Handle .gz files
    )
    parsed_dataset = dataset.map(parse_tfrecord_example)
    
    # Initialize collectors for all features
    product_ids = set()
    customer_ids = set()
    cities = set()
    revenues = []
    timestamps = []
    # New product metadata collectors
    product_names = set()
    product_categories = set()
    product_subcategories = set()
    
    # Process dataset in batches for efficiency
    batch_size = 1000
    batched_dataset = parsed_dataset.batch(batch_size)
    
    total_examples = 0
    
    logger.info("Processing TFRecord files to extract vocabularies with product metadata...")
    
    for batch in batched_dataset:
        # Convert tensor batch to numpy for processing
        batch_product_ids = batch['product_id'].numpy()
        batch_customer_ids = batch['cust_person_id'].numpy()
        batch_cities = batch['city'].numpy()
        batch_revenues = batch['revenue'].numpy()
        batch_timestamps = batch['timestamp'].numpy()
        # New product metadata
        batch_product_names = batch['art_name'].numpy()
        batch_categories = batch['stratbuy_domain_desc'].numpy()
        batch_subcategories = batch['mge_main_cat_desc'].numpy()
        
        # Update collectors - convert product_id to string for trainer compatibility
        product_ids.update([str(pid) for pid in batch_product_ids])
        customer_ids.update([cid.decode('utf-8') if isinstance(cid, bytes) else str(cid) 
                           for cid in batch_customer_ids])
        cities.update([city.decode('utf-8') if isinstance(city, bytes) else str(city) 
                      for city in batch_cities])
        revenues.extend(batch_revenues)
        timestamps.extend(batch_timestamps)
        
        # Update product metadata collectors
        product_names.update([name.decode('utf-8') if isinstance(name, bytes) else str(name) 
                             for name in batch_product_names])
        product_categories.update([cat.decode('utf-8') if isinstance(cat, bytes) else str(cat) 
                                  for cat in batch_categories])
        product_subcategories.update([subcat.decode('utf-8') if isinstance(subcat, bytes) else str(subcat) 
                                     for subcat in batch_subcategories])
        
        total_examples += len(batch_product_ids)
        
        if total_examples % 100000 == 0:
            logger.info(f"Processed {total_examples} examples...")
    
    logger.info(f"Processed {total_examples} total examples")
    
    # Convert to sorted lists for consistency
    unique_product_ids = sorted(list(product_ids))
    unique_customer_ids = sorted(list(customer_ids))
    unique_cities = sorted(list(cities))
    unique_revenues = np.array(revenues)
    unique_timestamps = np.array(timestamps)
    # New product metadata vocabularies
    unique_product_names = sorted(list(product_names))
    unique_product_categories = sorted(list(product_categories))
    unique_product_subcategories = sorted(list(product_subcategories))
    
    # Convert timestamps to dates for logging
    from datetime import datetime
    min_date = datetime.fromtimestamp(unique_timestamps.min()).strftime('%Y-%m-%d')
    max_date = datetime.fromtimestamp(unique_timestamps.max()).strftime('%Y-%m-%d')
    
    logger.info(f"\n📊 COMPLETE DATASET VOCABULARY ANALYSIS WITH PRODUCT METADATA:")
    logger.info(f"  - Products: {len(unique_product_ids):,}")
    logger.info(f"  - Customers: {len(unique_customer_ids):,}")
    logger.info(f"  - Cities: {len(unique_cities):,}")
    logger.info(f"  - Revenue stats: min={unique_revenues.min():.2f}, max={unique_revenues.max():.2f}")
    logger.info(f"  - Timestamp range: {min_date} to {max_date} ({unique_timestamps.min()} to {unique_timestamps.max()})")
    logger.info(f"  ✨ Product names: {len(unique_product_names):,}")
    logger.info(f"  ✨ Product categories: {len(unique_product_categories):,}")
    logger.info(f"  ✨ Product subcategories: {len(unique_product_subcategories):,}")
    logger.info(f"  - Total examples: {total_examples:,}")
    logger.info(f"✅ Vocabularies built on COMPLETE dataset with PRODUCT METADATA")
    
    return {
        'unique_product_ids': unique_product_ids,
        'unique_customer_ids': unique_customer_ids,
        'unique_cities': unique_cities,
        'unique_revenues': unique_revenues,
        'unique_timestamps': unique_timestamps,
        # New product metadata
        'unique_product_names': unique_product_names,
        'unique_product_categories': unique_product_categories,
        'unique_product_subcategories': unique_product_subcategories,
        'total_examples': total_examples
    }


def create_revenue_buckets(unique_revenues: np.ndarray, num_buckets: int = 1000) -> np.ndarray:
    """Create revenue buckets for discretization (like in no_tfx_example.py)."""
    
    min_revenue = unique_revenues.min()
    max_revenue = unique_revenues.max()
    
    revenue_buckets = np.linspace(min_revenue, max_revenue, num=num_buckets)
    
    logger.info(f"Created {num_buckets} revenue buckets: {min_revenue:.2f} to {max_revenue:.2f}")
    
    return revenue_buckets


def create_timestamp_buckets(unique_timestamps: np.ndarray, num_buckets: int = 120) -> np.ndarray:
    """Create timestamp buckets for temporal discretization (TensorFlow approach)."""
    
    min_timestamp = unique_timestamps.min()
    max_timestamp = unique_timestamps.max()
    
    # Create linear buckets across time range (like TensorFlow example)
    timestamp_buckets = np.linspace(min_timestamp, max_timestamp, num=num_buckets)
    
    # Convert to dates for logging
    from datetime import datetime
    min_date = datetime.fromtimestamp(min_timestamp).strftime('%Y-%m-%d')
    max_date = datetime.fromtimestamp(max_timestamp).strftime('%Y-%m-%d')
    
    logger.info(f"Created {num_buckets} timestamp buckets: {min_date} to {max_date}")
    logger.info(f"Timestamp range: {min_timestamp} to {max_timestamp} (Unix seconds)")
    
    return timestamp_buckets


def save_vocabularies(vocabularies: Dict[str, Any], output_path: str, num_buckets: int = 1000, num_timestamp_buckets: int = 120):
    """Save vocabularies with product metadata to JSON file for trainer compatibility."""
    
    logger.info(f"Saving vocabularies with product metadata to: {output_path}")
    
    # Create output directory if needed
    if output_path.startswith('gs://'):
        # For GCS, we'll write to a file directly
        vocab_file = os.path.join(output_path, 'vocabularies.json')
    else:
        os.makedirs(output_path, exist_ok=True)
        vocab_file = os.path.join(output_path, 'vocabularies.json')
    
    # Create revenue buckets
    revenue_buckets = create_revenue_buckets(vocabularies['unique_revenues'], num_buckets)
    
    # Create timestamp buckets (TensorFlow approach)
    timestamp_buckets = create_timestamp_buckets(vocabularies['unique_timestamps'], num_timestamp_buckets)
    
    # Prepare vocabularies in format expected by trainer
    vocab_data = {
        # Original vocabularies
        'product_id': vocabularies['unique_product_ids'],  # Already strings
        'customer_id': vocabularies['unique_customer_ids'],
        'city': vocabularies['unique_cities'],
        'revenue_buckets': revenue_buckets.tolist(),  # Convert numpy array to list
        'timestamp_buckets': timestamp_buckets.tolist(),  # Convert numpy array to list
        # New product metadata vocabularies
        'art_name': vocabularies['unique_product_names'],
        'stratbuy_domain_desc': vocabularies['unique_product_categories'],
        'mge_main_cat_desc': vocabularies['unique_product_subcategories'],
        'metadata': {
            'total_examples': vocabularies['total_examples'],
            'vocab_sizes': {
                'products': len(vocabularies['unique_product_ids']),
                'customers': len(vocabularies['unique_customer_ids']),
                'cities': len(vocabularies['unique_cities']),
                'revenue_buckets': len(revenue_buckets),
                'timestamp_buckets': len(timestamp_buckets),
                # New product metadata sizes
                'product_names': len(vocabularies['unique_product_names']),
                'product_categories': len(vocabularies['unique_product_categories']),
                'product_subcategories': len(vocabularies['unique_product_subcategories'])
            },
            'revenue_stats': {
                'min': float(vocabularies['unique_revenues'].min()),
                'max': float(vocabularies['unique_revenues'].max()),
                'mean': float(vocabularies['unique_revenues'].mean()),
                'std': float(vocabularies['unique_revenues'].std())
            },
            'timestamp_stats': {
                'min': int(vocabularies['unique_timestamps'].min()),
                'max': int(vocabularies['unique_timestamps'].max()),
                'range_days': int((vocabularies['unique_timestamps'].max() - vocabularies['unique_timestamps'].min()) / 86400),
                'approach': 'tensorflow_linear_buckets'
            },
            'features_version': 'with_product_metadata',
            'features_count': 8  # 5 original + 3 product metadata
        }
    }
    
    # Save to JSON
    import json
    if vocab_file.startswith('gs://'):
        # For GCS, use TensorFlow's file API
        json_str = json.dumps(vocab_data, indent=2)
        with tf.io.gfile.GFile(vocab_file, 'w') as f:
            f.write(json_str)
    else:
        with open(vocab_file, 'w') as f:
            json.dump(vocab_data, f, indent=2)
    
    logger.info("\n✅ VOCABULARIES WITH PRODUCT METADATA SAVED SUCCESSFULLY")
    logger.info(f"📁 Saved to: {vocab_file}")
    logger.info(f"\n📊 Final Vocabulary Summary:")
    logger.info(f"  Original Features:")
    logger.info(f"    - Products: {len(vocabularies['unique_product_ids']):,}")
    logger.info(f"    - Customers: {len(vocabularies['unique_customer_ids']):,}")
    logger.info(f"    - Cities: {len(vocabularies['unique_cities']):,}")
    logger.info(f"    - Revenue buckets: {len(revenue_buckets):,}")
    logger.info(f"    - Timestamp buckets: {len(timestamp_buckets):,}")
    logger.info(f"  Product Metadata Features:")
    logger.info(f"    ✨ Product names: {len(vocabularies['unique_product_names']):,}")
    logger.info(f"    ✨ Product categories: {len(vocabularies['unique_product_categories']):,}")
    logger.info(f"    ✨ Product subcategories: {len(vocabularies['unique_product_subcategories']):,}")
    logger.info(f"  - Total examples processed: {vocabularies['total_examples']:,}")
    logger.info(f"\n🎯 METHODOLOGY: Complete dataset vocabularies with product metadata")
    logger.info(f"📋 READY FOR: Enhanced trainer with product features for better recommendations")


def main():
    """Main entry point for VocabBuilder component with product metadata."""
    
    try:
        parser = argparse.ArgumentParser(description='Metro Recommender VocabBuilder Component with Product Metadata')
        parser.add_argument('--input_path', required=True, help='Path to TFRecord files (supports glob patterns)')
        parser.add_argument('--output_path', required=True, help='Path to save vocabulary files')
        parser.add_argument('--num_revenue_buckets', type=int, default=1000,
                           help='Number of revenue buckets for discretization (default: 1000)')
        parser.add_argument('--num_timestamp_buckets', type=int, default=90,
                           help='Number of timestamp buckets for temporal discretization (default: 90 for 90 days)')
        
        args = parser.parse_args()
        
        logger.info("Starting VocabBuilder component with Product Metadata")
        logger.info(f"Input path: {args.input_path}")
        logger.info(f"Output path: {args.output_path}")
        logger.info(f"Revenue buckets: {args.num_revenue_buckets}")
        logger.info(f"Timestamp buckets: {args.num_timestamp_buckets}")
        logger.info(f"\n🎯 OBJECTIVE: Build vocabularies with product metadata (8 features)")
        
        # Validate input path
        if not args.input_path:
            raise ValueError("Input path cannot be empty")
        
        # Extract vocabularies from TFRecord files
        try:
            vocabularies = extract_vocabularies_from_tfrecords(args.input_path)
        except Exception as e:
            logger.error(f"Failed to extract vocabularies: {str(e)}")
            raise
        
        # Save vocabularies
        try:
            save_vocabularies(vocabularies, args.output_path, args.num_revenue_buckets, args.num_timestamp_buckets)
        except Exception as e:
            logger.error(f"Failed to save vocabularies: {str(e)}")
            raise
        
        logger.info("\n🎉 VocabBuilder with Product Metadata completed successfully!")
        logger.info("✅ Complete dataset vocabularies with 8 features ready for enhanced trainer")
        
    except Exception as e:
        logger.error(f"VocabBuilder component failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import sys
    main()