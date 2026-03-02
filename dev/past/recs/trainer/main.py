#!/usr/bin/env python3
"""
Single VM Multi-GPU Metadata Trainer v7 with Early Stopping
Key features:
1. Single machine multi-GPU training with MirroredStrategy
2. ProductModel with product IDs + categories (16D) + subcategories (24D)
3. FIXED: Proper metadata lookup during evaluation (no more dummy values)
4. Week number, day of week, day of month, month of year cyclical encodings
5. ORIGINAL architecture with 128→64→32 dense layers
6. Maintains customer×city and revenue×time cross features
7. Optimized for scaling from 500K to 50M examples on single powerful VM
8. Simplified distributed training without multi-machine complexity
9. NEW: Early stopping, learning rate reduction, and model checkpointing
10. NEW: Training monitoring for convergence detection
11. NEW: Gradient clipping for stability
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Tuple
from datetime import datetime

import tensorflow as tf
import tensorflow_recommenders as tfrs
from google.cloud import storage
import numpy as np
import math
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_distributed_training():
    """Setup distributed training strategy for single VM multi-GPU training."""
    
    # Get available GPUs on this machine
    gpus = tf.config.list_physical_devices('GPU')
    logger.info(f"🎮 Available GPUs: {len(gpus)}")
    
    if len(gpus) > 1:
        # Single machine, multi-GPU training
        logger.info("🔥 SINGLE VM MULTI-GPU TRAINING")
        strategy = tf.distribute.MirroredStrategy()
        logger.info(f"🎯 Using {strategy.num_replicas_in_sync} GPUs with MirroredStrategy")
        logger.info("✅ NVLink communication for fast GPU-to-GPU transfer")
    elif len(gpus) == 1:
        # Single GPU training
        logger.info("🔥 SINGLE GPU TRAINING")
        strategy = tf.distribute.get_strategy()  # Default strategy
        logger.info("🎯 Using default strategy (single GPU)")
    else:
        # CPU training (fallback)
        logger.warning("⚠️ No GPUs found, using CPU strategy")
        strategy = tf.distribute.get_strategy()
    
    # Set memory growth for all GPUs to avoid OOM errors
    for gpu in gpus:
        try:
            tf.config.experimental.set_memory_growth(gpu, True)
            logger.info(f"✅ Set memory growth for GPU: {gpu}")
        except RuntimeError:
            # Memory growth can only be set at program startup
            pass
    
    return strategy


class TrainingMonitor(tf.keras.callbacks.Callback):
    """Monitor training progress and detect convergence patterns."""

    def __init__(self):
        super().__init__()
        self.epoch_times = []
        self.losses = []
        self.val_losses = []

    def on_epoch_begin(self, epoch, logs=None):
        self.epoch_start = time.time()

    def on_epoch_end(self, epoch, logs=None):
        epoch_time = time.time() - self.epoch_start
        self.epoch_times.append(epoch_time)

        if logs:
            self.losses.append(logs.get('loss'))
            self.val_losses.append(logs.get('val_loss'))

        # Check for convergence
        if len(self.losses) > 20:
            recent_losses = self.losses[-10:]
            loss_std = np.std(recent_losses)
            if loss_std < 0.001:
                logger.warning(f"⚠️ Loss plateau detected at epoch {epoch+1}, std={loss_std:.6f}")

        # Log progress every 10 epochs
        if (epoch + 1) % 10 == 0:
            avg_time = np.mean(self.epoch_times[-10:] if len(self.epoch_times) >= 10 else self.epoch_times)
            remaining_epochs = self.params['epochs'] - epoch - 1
            eta = remaining_epochs * avg_time / 3600
            logger.info(f"📊 Epoch {epoch+1}/{self.params['epochs']}: "
                       f"avg_epoch_time={avg_time:.1f}s, ETA={eta:.1f}h")

            # Log loss trends
            if len(self.losses) >= 10:
                recent_loss_trend = self.losses[-1] - self.losses[-10]
                logger.info(f"   Loss trend (last 10 epochs): {recent_loss_trend:+.6f}")

    def on_train_end(self, logs=None):
        total_time = sum(self.epoch_times)
        logger.info(f"✅ Training completed in {total_time/3600:.2f} hours")
        if len(self.losses) > 0:
            logger.info(f"   Final loss: {self.losses[-1]:.6f}")
            logger.info(f"   Best loss: {min(self.losses):.6f} at epoch {self.losses.index(min(self.losses)) + 1}")


def get_optimal_batch_size(total_examples, num_gpus):
    """Calculate optimal batch size based on dataset size."""
    if total_examples > 10_000_000:
        # Very large dataset - use larger batches
        per_gpu_batch = 4096
    elif total_examples > 1_000_000:
        # Large dataset
        per_gpu_batch = 2048
    else:
        # Smaller dataset
        per_gpu_batch = 1024

    # Ensure we don't exceed GPU memory
    max_per_gpu = 4096
    per_gpu_batch = min(per_gpu_batch, max_per_gpu)

    logger.info(f"🔧 Auto-selected batch size: {per_gpu_batch} per GPU based on {total_examples:,} examples")
    return per_gpu_batch


class FeatureCrossingLayer(tf.keras.layers.Layer):
    """Create explicit feature crosses using hashing."""

    def __init__(self, num_bins=10000, embedding_dim=16, name=None):
        super().__init__(name=name)
        self.num_bins = num_bins
        self.embedding_dim = embedding_dim

        # Use StringLookup with hash bucket for feature crossing
        self.hash_layer = tf.keras.layers.Hashing(
            num_bins=num_bins,
            output_mode='int'
        )

        # Embedding for crossed features
        self.cross_embedding = tf.keras.layers.Embedding(
            num_bins + 1, embedding_dim, name=f"{name}_embedding" if name else None
        )

    def call(self, feature1, feature2):
        # Concatenate features as strings and hash
        concatenated = tf.strings.join([feature1, '_x_', feature2])
        hashed = self.hash_layer(concatenated)
        return self.cross_embedding(hashed)


class EnhancedBuyerModel(tf.keras.Model):
    """Enhanced buyer model with optimized embeddings, feature crossing, and cyclical features."""
    
    def __init__(self, user_vocab, city_vocab, revenue_buckets, unique_revenues, timestamp_buckets=None, unique_timestamps=None):
        super().__init__()
        
        logger.info("🎯 ENHANCED EMBEDDINGS WITH CYCLICAL FEATURES:")
        logger.info(f"   Customer: {len(user_vocab):,} vocab → 64D (high cardinality)")
        logger.info(f"   City: {len(city_vocab)} vocab → 16D (low cardinality)")
        
        # Customer embedding - ENHANCED to 64D
        self.customers_embedding = tf.keras.Sequential([
            tf.keras.layers.StringLookup(vocabulary=user_vocab, mask_token=None),
            tf.keras.layers.Embedding(len(user_vocab) + 1, 64),
        ])
        
        # City embedding - REDUCED to 16D
        self.city_embedding = tf.keras.Sequential([
            tf.keras.layers.StringLookup(vocabulary=city_vocab, mask_token=None),
            tf.keras.layers.Embedding(len(city_vocab) + 1, 16),
        ])
        
        # Revenue - same as baseline
        self.revenues_embedding = tf.keras.Sequential([
            tf.keras.layers.Discretization(revenue_buckets.tolist()),
            tf.keras.layers.Embedding(len(revenue_buckets) + 1, 32),
        ])
        
        self.revenues_discretizer = tf.keras.layers.Discretization(revenue_buckets.tolist())
        
        self.normalized_revenues = tf.keras.layers.Normalization(axis=None)
        self.normalized_revenues.adapt(unique_revenues)
        
        # Feature crossing
        logger.info("🔄 FEATURE CROSSING:")
        logger.info("   Customer×City: 5,000 bins → 16D")
        logger.info("   Revenue×Time: 3,000 bins → 12D")
        
        self.customer_city_cross = FeatureCrossingLayer(
            num_bins=5000, embedding_dim=16, name="customer_city_cross"
        )
        
        self.revenue_time_cross = FeatureCrossingLayer(
            num_bins=3000, embedding_dim=12, name="revenue_time_cross"
        )
        
        # Timestamps - cyclical features only
        self.has_timestamps = timestamp_buckets is not None and unique_timestamps is not None
        if self.has_timestamps:
            logger.info("🔄 TIMESTAMPS: Combined linear + cyclical features")
            logger.info("📅 CYCLICAL: Week number, day of week, day of month, month of year")
            
            self.normalized_timestamps = tf.keras.layers.Normalization(axis=None)
            self.normalized_timestamps.adapt(unique_timestamps.astype(np.float32))
            
            self.timestamps_embedding = tf.keras.Sequential([
                tf.keras.layers.Discretization(timestamp_buckets.tolist()),
                tf.keras.layers.Embedding(len(timestamp_buckets) + 1, 32),
            ])
    
    def _create_cyclical_features(self, timestamps):
        """Create cyclical features: week number, day of week, day of month, month of year."""
        SECONDS_PER_DAY = tf.constant(86400.0, dtype=tf.float32)
        DAYS_PER_WEEK = tf.constant(7.0, dtype=tf.float32)
        AVG_DAYS_PER_MONTH = tf.constant(30.44, dtype=tf.float32)
        MONTHS_PER_YEAR = tf.constant(12.0, dtype=tf.float32)
        DAYS_PER_YEAR = tf.constant(365.25, dtype=tf.float32)
        PI = tf.constant(np.pi, dtype=tf.float32)
        
        timestamps_float = tf.cast(timestamps, tf.float32)
        days_since_epoch = timestamps_float / SECONDS_PER_DAY
        
        # Day of week (Monday = 0, Sunday = 6)
        day_of_week = tf.math.mod(days_since_epoch + 3, DAYS_PER_WEEK)
        dow_normalized = day_of_week / DAYS_PER_WEEK
        dow_sin = tf.sin(2 * PI * dow_normalized)
        dow_cos = tf.cos(2 * PI * dow_normalized)
        
        # Week number (0-51)
        week_of_year = tf.math.mod(days_since_epoch / DAYS_PER_WEEK, 52.0)
        week_normalized = week_of_year / 52.0
        week_sin = tf.sin(2 * PI * week_normalized)
        week_cos = tf.cos(2 * PI * week_normalized)
        
        # Day of month (approximation)
        day_of_month = tf.math.mod(days_since_epoch, AVG_DAYS_PER_MONTH)
        dom_normalized = day_of_month / AVG_DAYS_PER_MONTH
        dom_sin = tf.sin(2 * PI * dom_normalized)
        dom_cos = tf.cos(2 * PI * dom_normalized)
        
        # Month of year
        month_approx = tf.math.mod(days_since_epoch / AVG_DAYS_PER_MONTH, MONTHS_PER_YEAR)
        month_normalized = month_approx / MONTHS_PER_YEAR
        month_sin = tf.sin(2 * PI * month_normalized)
        month_cos = tf.cos(2 * PI * month_normalized)
        
        cyclical_features = tf.stack([
            dow_sin, dow_cos,    # Day of week
            week_sin, week_cos,  # Week number
            dom_sin, dom_cos,    # Day of month
            month_sin, month_cos # Month of year
        ], axis=1)
        
        return cyclical_features  # 8D features
    
    def call(self, inputs):
        # Base features with OPTIMIZED dimensions
        features = [
            self.customers_embedding(inputs['customer_id']),  # 64D
            self.city_embedding(inputs['city']),              # 16D  
            self.revenues_embedding(inputs["revenue"]),       # 32D
            tf.reshape(self.normalized_revenues(inputs["revenue"]), (-1, 1)),  # 1D
        ]
        
        # Customer×City crossing
        customer_city_cross = self.customer_city_cross(
            inputs['customer_id'], inputs['city']
        )  # 16D
        features.append(customer_city_cross)
        
        # Timestamps if available
        if self.has_timestamps and 'timestamp' in inputs:
            # Linear features
            timestamps_float = tf.cast(inputs["timestamp"], tf.float32)
            normalized_timestamps = self.normalized_timestamps(timestamps_float)
            linear_features = self.timestamps_embedding(normalized_timestamps)  # 32D
            features.append(linear_features)
            
            # Cyclical features
            cyclical_features = self._create_cyclical_features(inputs["timestamp"])  # 8D
            features.append(cyclical_features)
            
            # Revenue×Time crossing
            revenue_bucket = tf.strings.as_string(
                tf.cast(self.revenues_discretizer(inputs["revenue"]), tf.int64)
            )
            timestamp_bucket = tf.strings.as_string(
                tf.cast(inputs["timestamp"] // 3600, tf.int64)
            )
            
            revenue_time_cross = self.revenue_time_cross(
                revenue_bucket, timestamp_bucket
            )  # 12D
            features.append(revenue_time_cross)
        
        return tf.concat(features, axis=1)


class EnhancedProductModel(tf.keras.Model):
    """Product model with product_id, category, and subcategory embeddings."""
    
    def __init__(self, product_vocab, art_name_vocab, category_vocab, subcategory_vocab):
        super().__init__()
        
        logger.info("✨ PRODUCT MODEL WITH CATEGORY METADATA:")
        logger.info(f"   Product IDs: {len(product_vocab):,} → 32D")
        logger.info(f"   Categories: {len(category_vocab)} → 16D")
        logger.info(f"   Subcategories: {len(subcategory_vocab)} → 24D")
        logger.info("   Total embedding: 72D (32+16+24)")
        
        # Product embedding
        self.product_embedding = tf.keras.Sequential([
            tf.keras.layers.StringLookup(vocabulary=product_vocab, mask_token=None),
            tf.keras.layers.Embedding(len(product_vocab) + 1, 32),
        ])
        
        # Category embedding (16D for 24 categories)
        self.category_embedding = tf.keras.Sequential([
            tf.keras.layers.StringLookup(vocabulary=category_vocab, mask_token=None),
            tf.keras.layers.Embedding(len(category_vocab) + 1, 16),
        ])
        
        # Subcategory embedding (24D for 125 subcategories)
        self.subcategory_embedding = tf.keras.Sequential([
            tf.keras.layers.StringLookup(vocabulary=subcategory_vocab, mask_token=None),
            tf.keras.layers.Embedding(len(subcategory_vocab) + 1, 24),
        ])
    
    def call(self, inputs):
        # Concatenate all embeddings
        features = [
            self.product_embedding(inputs['product_id']),             # 32D
            self.category_embedding(inputs['stratbuy_domain_desc']),  # 16D
            self.subcategory_embedding(inputs['mge_main_cat_desc']),  # 24D
        ]
        return tf.concat(features, axis=1)  # Total: 72D (32+16+24)


def build_product_metadata_lookup(dataset_path, product_ids, category_vocab, subcategory_vocab):
    """Build a lookup table for product metadata from the dataset."""
    logger.info("📚 Building product metadata lookup table...")
    
    product_metadata = {}
    
    # Read a sample of data to build the lookup
    feature_description = {
        'product_id': tf.io.FixedLenFeature([], tf.int64),
        'stratbuy_domain_desc': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'mge_main_cat_desc': tf.io.FixedLenFeature([], tf.string, default_value=''),
    }
    
    # Get all TFRecord files
    files = tf.io.gfile.glob(dataset_path)
    logger.info(f"Found {len(files)} TFRecord files to scan for metadata")
    
    # Read through files to collect unique product metadata
    for file_path in files[:5]:  # Sample first 5 files for efficiency
        dataset = tf.data.TFRecordDataset(file_path, compression_type="GZIP")
        
        for raw_record in dataset.take(10000):  # Sample records
            example = tf.io.parse_single_example(raw_record, feature_description)
            
            product_id = str(example['product_id'].numpy())
            category = example['stratbuy_domain_desc'].numpy().decode('utf-8')
            subcategory = example['mge_main_cat_desc'].numpy().decode('utf-8')
            
            if product_id not in product_metadata:
                product_metadata[product_id] = {
                    'category': category,
                    'subcategory': subcategory
                }
    
    logger.info(f"✅ Built metadata lookup for {len(product_metadata)} products")
    
    # For any missing products, use defaults
    default_category = category_vocab[0] if category_vocab else 'Other'
    default_subcategory = subcategory_vocab[0] if subcategory_vocab else 'Other'
    
    for pid in product_ids:
        if pid not in product_metadata:
            product_metadata[pid] = {
                'category': default_category,
                'subcategory': default_subcategory
            }
    
    return product_metadata


def _get_simple_serve_fn(model, product_ids, art_name_vocab, category_vocab, subcategory_vocab, dataset_path=None):
    """Create serving function that returns actual product recommendations with product metadata support."""
    
    # Pre-compute all product embeddings with metadata
    logger.info("Pre-computing product embeddings with metadata for serving...")
    
    # Build product metadata lookup if dataset path provided
    if dataset_path:
        product_metadata = build_product_metadata_lookup(dataset_path, product_ids, category_vocab, subcategory_vocab)
    else:
        logger.warning("⚠️ No dataset path provided, using default metadata values")
        product_metadata = {pid: {'category': category_vocab[0], 'subcategory': subcategory_vocab[0]} 
                          for pid in product_ids}
    
    all_product_embeddings = []
    
    # Process products in batches with CORRECT metadata
    for i in range(0, len(product_ids), 100):
        batch_products = product_ids[i:i+100]
        
        # Get correct metadata for each product
        batch_categories = [product_metadata[pid]['category'] for pid in batch_products]
        batch_subcategories = [product_metadata[pid]['subcategory'] for pid in batch_products]
        
        batch_embeddings = model.candidate_model({
            'product_id': tf.constant(batch_products),
            'stratbuy_domain_desc': tf.constant(batch_categories),
            'mge_main_cat_desc': tf.constant(batch_subcategories),
        })
        all_product_embeddings.append(batch_embeddings)
    
    # Concatenate all embeddings
    all_candidate_embeddings = tf.concat(all_product_embeddings, axis=0)
    logger.info(f"Pre-computed embeddings for {len(product_ids)} products with metadata")
    
    # Convert product_ids to tensor
    product_ids_tensor = tf.constant(product_ids)
    
    @tf.function
    def serve_fn(customer_id, city, revenue, timestamp):
        """Serving function that returns top-100 product recommendations."""
        
        # Create query input with batch dimension
        query_input = {
            'customer_id': tf.expand_dims(customer_id, 0),
            'city': tf.expand_dims(city, 0),
            'revenue': tf.expand_dims(revenue, 0),
            'timestamp': tf.expand_dims(timestamp, 0)
        }
        
        # Get query embeddings
        query_embeddings = model.query_model(query_input)
        
        # Compute similarities with all candidates
        similarities = tf.linalg.matmul(query_embeddings, all_candidate_embeddings, transpose_b=True)
        similarities = tf.squeeze(similarities, 0)  # Remove batch dimension
        
        # Get top-100 recommendations
        top_scores, top_indices = tf.nn.top_k(similarities, k=100)
        
        # Get product IDs for top indices
        recommended_products = tf.gather(product_ids_tensor, top_indices)
        
        # Return both product IDs and scores
        return {
            'product_ids': recommended_products,
            'scores': top_scores
        }
    
    return serve_fn


class EnhancedMetroRetrievalModel(tfrs.models.Model):
    """Enhanced retrieval model with product metadata."""
    
    def __init__(self, user_vocab, product_vocab, city_vocab, revenue_buckets, unique_revenues, 
                 art_name_vocab, category_vocab, subcategory_vocab, timestamp_buckets=None, unique_timestamps=None):
        super().__init__()
        
        logger.info("🏗️ ORIGINAL BASELINE ARCHITECTURE WITH MULTI-GPU OPTIMIZATION:")
        logger.info("   Base: Proven main_combined.py query tower architecture")
        logger.info("   Product tower: Product ID + metadata")
        logger.info("   Dense layers: ORIGINAL 128→64→32 (no 256 layer)")
        
        # Initialize models
        self.buyer_model = EnhancedBuyerModel(user_vocab, city_vocab, revenue_buckets, unique_revenues, timestamp_buckets, unique_timestamps)
        self.product_model = EnhancedProductModel(product_vocab, art_name_vocab, category_vocab, subcategory_vocab)
        
        # Query model - ORIGINAL architecture
        self.query_model = tf.keras.Sequential([
            self.buyer_model,
            tf.keras.layers.Dense(128, kernel_regularizer=tf.keras.regularizers.l1(0.02)),
            tf.keras.layers.Dense(64),
            tf.keras.layers.Dense(32),
        ])
        
        # Candidate model - ORIGINAL architecture
        self.candidate_model = tf.keras.Sequential([
            self.product_model,
            tf.keras.layers.Dense(128, kernel_regularizer=tf.keras.regularizers.l1(0.02)),
            tf.keras.layers.Dense(64),
            tf.keras.layers.Dense(32),
        ])
        
        # Retrieval task
        self.retrieval_task = tfrs.tasks.Retrieval()
        
    def call(self, features):
        buyer_embeddings = self.query_model({
            'customer_id': features['customer_id'],
            'city': features['city'],
            'revenue': features['revenue'],
            'timestamp': features.get('timestamp', tf.zeros_like(features['customer_id'], dtype=tf.int64))
        })
        
        product_embeddings = self.candidate_model({
            'product_id': features['product_id'],
            'stratbuy_domain_desc': features['stratbuy_domain_desc'],
            'mge_main_cat_desc': features['mge_main_cat_desc'],
        })
        
        return buyer_embeddings, product_embeddings
    
    def compute_loss(self, features, training=False):
        buyer_embeddings, product_embeddings = self(features)
        loss = self.retrieval_task(
            query_embeddings=buyer_embeddings,
            candidate_embeddings=product_embeddings
        )
        
        # Simple loss reduction for MirroredStrategy
        return tf.reduce_mean(loss)


def load_vocabularies(vocab_path: str) -> Dict[str, List[str]]:
    """Load vocabularies with product metadata support."""
    logger.info(f"Loading vocabularies from: {vocab_path}")
    
    if vocab_path.endswith('.json'):
        vocab_file_path = vocab_path
    else:
        vocab_file_path = os.path.join(vocab_path, 'vocabularies.json')
    
    if vocab_file_path.startswith('gs://'):
        with tf.io.gfile.GFile(vocab_file_path, 'r') as f:
            vocab_data = json.load(f)
    else:
        with open(vocab_file_path, 'r') as f:
            vocab_data = json.load(f)
    
    logger.info(f"Loaded vocabularies - Customers: {len(vocab_data['customer_id'])}, "
               f"Products: {len(vocab_data['product_id'])}, "
               f"Cities: {len(vocab_data['city'])}, "
               f"Product names: {len(vocab_data['art_name'])}, "
               f"Categories: {len(vocab_data['stratbuy_domain_desc'])}, "
               f"Subcategories: {len(vocab_data['mge_main_cat_desc'])}")
    
    return vocab_data


def create_single_dataset(file_pattern: str) -> tf.data.Dataset:
    """Create single dataset from TFRecord files with product metadata."""
    
    # Feature description with product metadata
    feature_description = {
        'cust_person_id': tf.io.FixedLenFeature([], tf.string),
        'product_id': tf.io.FixedLenFeature([], tf.int64),
        'revenue': tf.io.FixedLenFeature([], tf.float32),
        'city': tf.io.FixedLenFeature([], tf.string),
        'timestamp': tf.io.FixedLenFeature([], tf.int64, default_value=0),
        # NEW product metadata features
        'art_name': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'stratbuy_domain_desc': tf.io.FixedLenFeature([], tf.string, default_value=''),
        'mge_main_cat_desc': tf.io.FixedLenFeature([], tf.string, default_value=''),
    }
    
    def parse_example(serialized_example):
        parsed = tf.io.parse_single_example(serialized_example, feature_description)
        return {
            'customer_id': parsed['cust_person_id'],
            'product_id': tf.strings.as_string(parsed['product_id']),
            'revenue': parsed['revenue'],
            'city': parsed['city'],
            'timestamp': parsed['timestamp'],
            # NEW product metadata
            'art_name': parsed['art_name'],
            'stratbuy_domain_desc': parsed['stratbuy_domain_desc'],
            'mge_main_cat_desc': parsed['mge_main_cat_desc'],
        }
    
    files = tf.data.Dataset.list_files(file_pattern, shuffle=True)
    dataset = files.interleave(
        lambda x: tf.data.TFRecordDataset(x, compression_type="GZIP"),
        cycle_length=4,
        block_length=16,
        num_parallel_calls=tf.data.AUTOTUNE
    )
    
    dataset = dataset.map(parse_example, num_parallel_calls=tf.data.AUTOTUNE)
    
    return dataset


def create_train_val_datasets(file_pattern: str, total_examples: int, per_replica_batch_size: int, strategy) -> tuple:
    """Create train and validation datasets with distributed training support."""
    
    # Calculate global batch size for distributed training
    global_batch_size = per_replica_batch_size * strategy.num_replicas_in_sync
    
    logger.info("\n🔧 DISTRIBUTED DATA SPLITTING:")
    logger.info(f"  - Complete dataset: {total_examples:,} examples")
    logger.info(f"  - Splitting: 80% train, 15% validation, 5% test")
    logger.info(f"  - Per-replica batch size: {per_replica_batch_size}")
    logger.info(f"  - Global batch size: {global_batch_size} ({strategy.num_replicas_in_sync} replicas)")
    logger.info(f"  - Shuffling: seed=42 for reproducibility")
    
    # Load complete dataset
    full_dataset = create_single_dataset(file_pattern)
    
    # CRITICAL: Shuffle before splitting to avoid temporal bias
    tf.random.set_seed(158)
    shuffled = full_dataset.shuffle(buffer_size=10000, seed=42)
    
    # Calculate split sizes
    train_size = int(total_examples * 0.8)  # 80%
    val_size = int(total_examples * 0.15)   # 15%
    test_size = total_examples - train_size - val_size  # 5%
    
    logger.info(f"  - Train examples: {train_size:,} (80%)")
    logger.info(f"  - Validation examples: {val_size:,} (15%)")
    logger.info(f"  - Test examples: {test_size:,} (5%)")
    
    # Create train and validation datasets
    train_ds = shuffled.take(train_size)
    remaining_ds = shuffled.skip(train_size)
    val_ds = remaining_ds.take(val_size)
    
    # Apply training-specific processing with distributed batching
    train_ds = train_ds.shuffle(buffer_size=10000)  # Additional shuffle for training
    train_ds = train_ds.repeat()  # Repeat for multiple epochs
    train_ds = train_ds.batch(global_batch_size)  # Use global batch size
    train_ds = train_ds.prefetch(tf.data.AUTOTUNE)
    
    # Apply validation-specific processing with distributed batching
    val_ds = val_ds.repeat()  # Repeat to prevent exhaustion
    val_ds = val_ds.batch(global_batch_size)  # Use global batch size
    val_ds = val_ds.prefetch(tf.data.AUTOTUNE)
    
    logger.info("✅ Distributed train and validation datasets created")
    
    return train_ds, val_ds


def create_test_dataset_after_training(file_pattern: str, total_examples: int, per_replica_batch_size: int, strategy) -> tf.data.Dataset:
    """Create test dataset AFTER training is complete (same split as training)."""
    
    global_batch_size = per_replica_batch_size * strategy.num_replicas_in_sync
    
    logger.info("\n🎯 CREATING DISTRIBUTED TEST DATASET - Post-Training Evaluation:")
    logger.info(f"  - Using same shuffle parameters for consistency")
    logger.info(f"  - Loading final 5% of data for evaluation")
    logger.info(f"  - Global batch size: {global_batch_size}")
    
    # Load complete dataset with SAME shuffle parameters
    full_dataset = create_single_dataset(file_pattern)
    
    # SAME shuffle parameters for consistency
    tf.random.set_seed(158)
    shuffled = full_dataset.shuffle(buffer_size=10000, seed=42)
    
    # Skip to test portion (same split as training)
    train_size = int(total_examples * 0.8)
    val_size = int(total_examples * 0.15)
    
    test_ds = shuffled.skip(train_size + val_size)
    test_ds = test_ds.batch(global_batch_size)
    test_ds = test_ds.prefetch(tf.data.AUTOTUNE)
    
    logger.info("✅ Distributed test dataset created with consistent split methodology")
    
    return test_ds


def evaluate_model_on_test_set(model, test_dataset, product_ids, art_name_vocab, category_vocab, subcategory_vocab, dataset_path=None, steps=50):
    """Evaluate the trained model on the test set with product metadata support."""
    logger.info("=" * 60)
    logger.info("🎯 FINAL EVALUATION: Computing accuracy metrics on TEST DATA ONLY")
    logger.info("=" * 60)
    logger.info("📊 Metrics: Recall@5, Recall@10, Recall@50, Recall@100")
    logger.info("📋 Note: During training, only loss metrics were shown")
    
    # Initialize metrics
    total_recall_5 = 0.0
    total_recall_10 = 0.0
    total_recall_50 = 0.0
    total_recall_100 = 0.0
    total_batches = 0
    
    try:
        # Create candidate embeddings for all products with metadata
        logger.info("Building candidate embeddings with product metadata...")
        
        # Build product metadata lookup if dataset path provided
        if dataset_path:
            product_metadata = build_product_metadata_lookup(dataset_path, product_ids, category_vocab, subcategory_vocab)
        else:
            logger.warning("⚠️ No dataset path provided for evaluation, using default metadata values")
            product_metadata = {pid: {'category': category_vocab[0], 'subcategory': subcategory_vocab[0]} 
                              for pid in product_ids}
        
        all_product_embeddings = []
        
        # Process products in batches with CORRECT metadata
        for i in range(0, len(product_ids), 100):
            batch_products = product_ids[i:i+100]
            
            # Get correct metadata for each product
            batch_categories = [product_metadata[pid]['category'] for pid in batch_products]
            batch_subcategories = [product_metadata[pid]['subcategory'] for pid in batch_products]
            
            batch_embeddings = model.candidate_model({
                'product_id': tf.constant(batch_products),
                'stratbuy_domain_desc': tf.constant(batch_categories),
                'mge_main_cat_desc': tf.constant(batch_subcategories),
            })
            all_product_embeddings.append(batch_embeddings)
        
        # Concatenate all embeddings
        all_candidate_embeddings = tf.concat(all_product_embeddings, axis=0)
        logger.info(f"Built embeddings for {len(product_ids)} products with metadata")
        
        # Create product ID to index mapping
        product_to_idx = {pid: i for i, pid in enumerate(product_ids)}
        
        # Evaluate on test batches
        logger.info("Evaluating on test batches...")
        for batch in test_dataset.take(steps):
            # Get query embeddings
            query_embeddings = model.query_model({
                'customer_id': batch['customer_id'],
                'city': batch['city'],
                'revenue': batch['revenue'],
                'timestamp': batch.get('timestamp', tf.zeros_like(batch['customer_id'], dtype=tf.int64))
            })
            
            # Compute similarities with all candidates
            similarities = tf.linalg.matmul(query_embeddings, all_candidate_embeddings, transpose_b=True)
            
            # Get top-k indices
            _, top_indices = tf.nn.top_k(similarities, k=100)
            
            # Calculate recall for each K
            current_batch_size = tf.shape(batch['product_id'])[0].numpy()
            
            for k in [5, 10, 50, 100]:
                # Get top-k predictions
                top_k_indices = top_indices[:, :k]
                
                # Calculate hits for this batch
                hits = 0
                for i in range(current_batch_size):
                    # Get actual product ID
                    actual_product = batch['product_id'][i].numpy().decode('utf-8')
                    
                    # Check if it's in our product vocabulary
                    if actual_product in product_to_idx:
                        actual_idx = product_to_idx[actual_product]
                        
                        # Check if actual product is in top-k predictions
                        if actual_idx in top_k_indices[i].numpy():
                            hits += 1
                
                # Calculate recall for this batch
                batch_recall = hits / current_batch_size
                
                # Add to totals
                if k == 5:
                    total_recall_5 += batch_recall
                elif k == 10:
                    total_recall_10 += batch_recall
                elif k == 50:
                    total_recall_50 += batch_recall
                elif k == 100:
                    total_recall_100 += batch_recall
            
            total_batches += 1
            
            if total_batches % 10 == 0:
                logger.info(f"  Processed {total_batches} batches...")
        
        # Calculate final averages
        final_recall_5 = total_recall_5 / total_batches
        final_recall_10 = total_recall_10 / total_batches
        final_recall_50 = total_recall_50 / total_batches
        final_recall_100 = total_recall_100 / total_batches
        
        logger.info("\n" + "=" * 60)
        logger.info("🎆 FINAL MULTI-GPU TEST RESULTS WITH PRODUCT METADATA:")
        logger.info(f"  Recall@5:   {final_recall_5:.4f} ({final_recall_5*100:.2f}%)")
        logger.info(f"  Recall@10:  {final_recall_10:.4f} ({final_recall_10*100:.2f}%)")
        logger.info(f"  Recall@50:  {final_recall_50:.4f} ({final_recall_50*100:.2f}%)")
        logger.info(f"  Recall@100: {final_recall_100:.4f} ({final_recall_100*100:.2f}%)")
        logger.info(f"  Test batches: {total_batches}")
        logger.info("=" * 60)
        
        return {
            'test_recall_5': final_recall_5,
            'test_recall_10': final_recall_10,
            'test_recall_50': final_recall_50,
            'test_recall_100': final_recall_100,
            'test_batches_evaluated': total_batches
        }
        
    except Exception as e:
        logger.error(f"❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'test_recall_5': 0.0,
            'test_recall_10': 0.0,
            'test_recall_50': 0.0,
            'test_recall_100': 0.0,
            'test_batches_evaluated': 0
        }


def train_model(args):
    """Train model with multi-GPU distributed training and product metadata support."""
    
    logger.info("🚀 SINGLE VM MULTI-GPU TRAINER WITH PRODUCT METADATA")
    logger.info("=" * 60)
    
    # STEP 1: Setup distributed training strategy for single VM
    strategy = setup_distributed_training()
    
    # STEP 2: Scale learning rate with number of GPUs for optimal training
    base_learning_rate = args.learning_rate
    if strategy.num_replicas_in_sync > 1:
        # Choose scaling strategy based on argument
        if args.lr_scaling == 'linear':
            # Linear scaling: LR scales linearly with batch size increase
            # Good for large batches but may cause instability
            scaled_learning_rate = base_learning_rate * strategy.num_replicas_in_sync
            logger.info(f"📈 LINEAR LEARNING RATE SCALING:")
        elif args.lr_scaling == 'sqrt':
            # Square root scaling: More conservative, often better accuracy
            # Recommended for accuracy-sensitive training
            scaled_learning_rate = base_learning_rate * (strategy.num_replicas_in_sync ** 0.5)
            logger.info(f"📈 SQUARE ROOT LEARNING RATE SCALING:")
        else:  # 'none'
            # No scaling: Keep base learning rate
            # May converge slower but can be more stable
            scaled_learning_rate = base_learning_rate
            logger.info(f"📈 NO LEARNING RATE SCALING:")
        
        logger.info(f"   Base LR: {base_learning_rate}")
        logger.info(f"   Scaled LR: {scaled_learning_rate:.6f}")
        logger.info(f"   Scaling factor: {scaled_learning_rate/base_learning_rate:.2f}x")
        logger.info(f"   Global batch size: {args.batch_size * strategy.num_replicas_in_sync}")
        
        # Log recommendation based on use case
        if args.lr_scaling == 'sqrt':
            logger.info("   💡 Using sqrt scaling for better accuracy preservation")
        elif args.lr_scaling == 'linear':
            logger.info("   💡 Using linear scaling for faster convergence")
        else:
            logger.info("   💡 No scaling - most conservative approach")
    else:
        scaled_learning_rate = base_learning_rate
        logger.info(f"📈 Single GPU - Using base learning rate: {base_learning_rate}")
    
    # Load vocabularies with product metadata
    vocabularies = load_vocabularies(args.vocabularies_path)
    
    # Extract vocabularies - original features
    user_vocab = vocabularies['customer_id']
    product_ids = [str(pid) for pid in vocabularies['product_id']]
    city_vocab = vocabularies['city']
    
    # Extract NEW product metadata vocabularies
    art_name_vocab = vocabularies['art_name']
    category_vocab = vocabularies['stratbuy_domain_desc']
    subcategory_vocab = vocabularies['mge_main_cat_desc']
    
    # Revenue buckets - SAME as baseline
    if 'revenue_buckets' in vocabularies:
        revenue_buckets = np.array(vocabularies['revenue_buckets'])
        logger.info(f"📊 Loaded {len(revenue_buckets)} revenue buckets")
    else:
        logger.error("❌ Revenue buckets not found")
        raise ValueError("Revenue buckets missing")
    
    # Get unique revenues for normalization - SAME approach as baseline
    logger.info("📊 Using revenue statistics from vocab_builder (complete dataset)...")
    metadata_section = vocabularies.get('metadata', {})
    revenue_stats = metadata_section.get('revenue_stats', {})
    if revenue_stats:
        # Create revenue array from vocab statistics for normalization layer
        revenue_mean = revenue_stats['mean']
        revenue_std = revenue_stats['std']
        revenue_min = revenue_stats['min'] 
        revenue_max = revenue_stats['max']
        
        # Create representative revenue array for normalization adaptation
        unique_revenues = np.linspace(revenue_min, revenue_max, 1000).astype(np.float32)
        logger.info(f"   Using complete dataset stats: mean={revenue_mean:.2f}, std={revenue_std:.2f}")
        logger.info(f"   Range: {revenue_min:.2f} - {revenue_max:.2f}")
    else:
        logger.error("❌ No revenue stats in vocabularies metadata")
        raise ValueError("Revenue stats missing from vocabularies metadata")
    
    # Timestamps - SAME as baseline
    timestamp_buckets = None
    unique_timestamps = None
    if 'timestamp_buckets' in vocabularies:
        logger.info("🕒 Loading timestamp buckets from vocab_builder...")
        timestamp_buckets = np.array(vocabularies['timestamp_buckets'])
        logger.info(f"📊 Loaded {len(timestamp_buckets)} timestamp buckets from vocab_builder")
        
        # Get timestamp statistics from vocabulary metadata (complete dataset)
        timestamp_stats = metadata_section.get('timestamp_stats', {})
        if timestamp_stats:
            timestamp_min = timestamp_stats['min']
            timestamp_max = timestamp_stats['max']
            
            # Create representative timestamp array for normalization adaptation
            unique_timestamps = np.linspace(timestamp_min, timestamp_max, 1000).astype(np.float32)
            logger.info(f"   Range: {timestamp_min} to {timestamp_max}")
            logger.info(f"   Built from complete dataset (not just training split)")
        else:
            logger.warning("⚠️ No timestamp stats in vocabularies, using bucket range")
            unique_timestamps = timestamp_buckets.astype(np.float32)
    
    # Get total examples from metadata
    if args.metadata_path.startswith('gs://'):
        with tf.io.gfile.GFile(args.metadata_path, 'r') as f:
            metadata = json.load(f)
    else:
        with open(args.metadata_path, 'r') as f:
            metadata = json.load(f)
    
    total_examples = metadata['total_examples']
    logger.info(f"\n📊 DATASET INFO: {total_examples:,} total examples from complete dataset")
    
    # BEST PRACTICE: Keep per-replica batch size reasonable (1024-2048)
    # Global batch size will be per_replica_batch_size * num_replicas
    # Use adaptive batch size if not specified
    if args.batch_size == -1:
        per_replica_batch_size = get_optimal_batch_size(total_examples, strategy.num_replicas_in_sync)
    else:
        per_replica_batch_size = args.batch_size
    global_batch_size = per_replica_batch_size * strategy.num_replicas_in_sync
    
    logger.info(f"\n⚡ BATCH SIZE OPTIMIZATION:")
    logger.info(f"  - Per-replica batch size: {per_replica_batch_size} (maintains GPU memory efficiency)")
    logger.info(f"  - Global batch size: {global_batch_size} (total across all replicas)")
    logger.info(f"  - Effective speedup: ~{strategy.num_replicas_in_sync}x training acceleration")
    
    # Create datasets with distributed training support
    file_pattern = args.tfrecords_path
    train_dataset, val_dataset = create_train_val_datasets(file_pattern, total_examples, per_replica_batch_size, strategy)
    
    # Calculate steps per epoch based on splits and global batch size
    train_steps = max(1, int(total_examples * 0.8) // global_batch_size)
    val_steps = max(1, int(total_examples * 0.15) // global_batch_size)
    
    logger.info(f"Training steps per epoch: {train_steps} (adjusted for global batch size)")
    logger.info(f"Validation steps: {val_steps} (adjusted for global batch size)")
    
    # STEP 2: Initialize model within strategy scope for distributed training
    with strategy.scope():
        logger.info("🎯 Creating model within distributed strategy scope...")
        
        model = EnhancedMetroRetrievalModel(
            user_vocab=user_vocab,
            product_vocab=product_ids,
            city_vocab=city_vocab,
            revenue_buckets=revenue_buckets,
            unique_revenues=unique_revenues,
            art_name_vocab=art_name_vocab,
            category_vocab=category_vocab,
            subcategory_vocab=subcategory_vocab,
            timestamp_buckets=timestamp_buckets,
            unique_timestamps=unique_timestamps
        )
        
        # Setup optimizer with optional learning rate schedule
        if args.warmup_steps > 0:
            # Create learning rate schedule with warmup
            logger.info(f"🔥 Using learning rate warmup for {args.warmup_steps} steps")
            
            # Calculate total training steps
            total_training_steps = train_steps * args.epochs
            
            # Create custom learning rate schedule with warmup
            class WarmupSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):
                def __init__(self, base_lr, warmup_steps):
                    super().__init__()
                    self.base_lr = base_lr
                    self.warmup_steps = tf.cast(warmup_steps, tf.float32)
                
                def __call__(self, step):
                    step = tf.cast(step, tf.float32)
                    # Linear warmup
                    warmup_lr = self.base_lr * (step / self.warmup_steps)
                    # After warmup, use constant learning rate
                    return tf.cond(
                        step < self.warmup_steps,
                        lambda: warmup_lr,
                        lambda: self.base_lr
                    )
                
                def get_config(self):
                    return {
                        'base_lr': self.base_lr,
                        'warmup_steps': self.warmup_steps
                    }
            
            lr_schedule = WarmupSchedule(scaled_learning_rate, args.warmup_steps)
            optimizer = tf.keras.optimizers.Adam(
                learning_rate=lr_schedule,
                clipnorm=1.0  # Gradient clipping for stability
            )
            logger.info(f"   Warmup from 0 to {scaled_learning_rate:.6f} over {args.warmup_steps} steps")
            logger.info(f"   Then constant at {scaled_learning_rate:.6f}")
            logger.info(f"   Gradient clipping enabled (clipnorm=1.0)")
        else:
            # Use constant learning rate
            optimizer = tf.keras.optimizers.Adam(
                learning_rate=scaled_learning_rate,
                clipnorm=1.0  # Gradient clipping for stability
            )
            logger.info(f"   Using constant learning rate: {scaled_learning_rate:.6f}")
            logger.info(f"   Gradient clipping enabled (clipnorm=1.0)")
        
        # Compile within strategy scope
        model.compile(optimizer=optimizer)
        
        logger.info("✅ Model compiled within distributed strategy scope")
    
    # STEP 3: Setup callbacks for better training control
    logger.info("📋 Setting up training callbacks...")

    # Create temporary directory for checkpoints
    checkpoint_dir = '/tmp/metro_trainer_v2_checkpoints'
    os.makedirs(checkpoint_dir, exist_ok=True)

    callbacks = []

    # Early stopping callback - using regularization_loss for better stability
    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor='regularization_loss',
        patience=args.early_stopping_patience,
        restore_best_weights=True,
        verbose=1,
        min_delta=0.001,  # Increased from 0.0001 since regularization_loss changes are larger
        mode='min',
        start_from_epoch=args.min_epochs  # Don't stop before minimum epochs
    )
    callbacks.append(early_stopping)
    logger.info(f"✅ Early stopping configured on regularization_loss (patience={args.early_stopping_patience}, min_epochs={args.min_epochs})")

    # Model checkpoint callback - using regularization_loss for consistency
    checkpoint_path = os.path.join(checkpoint_dir, 'best_model.keras')
    checkpoint = tf.keras.callbacks.ModelCheckpoint(
        filepath=checkpoint_path,
        monitor='regularization_loss',
        save_best_only=True,
        save_weights_only=False,
        verbose=1,
        mode='min'
    )
    callbacks.append(checkpoint)
    logger.info(f"✅ Model checkpoint configured at {checkpoint_path}")

    # Learning rate reduction callback (only if not using warmup schedule)
    if args.warmup_steps == 0:
        reduce_lr = tf.keras.callbacks.ReduceLROnPlateau(
            monitor='regularization_loss',
            factor=0.5,
            patience=args.reduce_lr_patience,
            min_lr=1e-6,
            verbose=1,
            mode='min',
            cooldown=2,
            min_delta=0.001  # Adjusted for regularization_loss scale
        )
        callbacks.append(reduce_lr)
        logger.info(f"✅ LR reduction configured (patience={args.reduce_lr_patience}, factor=0.5)")
    else:
        logger.info("ℹ️ LR reduction disabled (using warmup schedule instead)")

    # Training monitor callback
    training_monitor = TrainingMonitor()
    callbacks.append(training_monitor)
    logger.info("✅ Training monitor configured")

    # TensorBoard callback (optional)
    if args.enable_tensorboard:
        tensorboard_dir = os.path.join(checkpoint_dir, 'logs')
        tensorboard = tf.keras.callbacks.TensorBoard(
            log_dir=tensorboard_dir,
            histogram_freq=0,
            update_freq='epoch',
            profile_batch=0
        )
        callbacks.append(tensorboard)
        logger.info(f"✅ TensorBoard logging configured at {tensorboard_dir}")

    # STEP 4: Train with distributed datasets
    logger.info("🎯 Starting distributed training with product metadata features and smart callbacks...")

    # Distributed dataset preparation
    train_dataset = strategy.experimental_distribute_dataset(train_dataset)
    val_dataset = strategy.experimental_distribute_dataset(val_dataset)

    # Train the model
    history = model.fit(
        train_dataset,
        validation_data=val_dataset,
        epochs=args.epochs,
        steps_per_epoch=train_steps,
        validation_steps=val_steps,
        callbacks=callbacks,
        verbose=1
    )

    # Log actual epochs trained
    actual_epochs = len(history.history['loss'])
    logger.info(f"✅ Training completed after {actual_epochs} epochs (requested: {args.epochs})")
    if actual_epochs < args.epochs:
        logger.info(f"💡 Early stopping triggered - saved {args.epochs - actual_epochs} unnecessary epochs!")
        saved_hours = (args.epochs - actual_epochs) * np.mean(training_monitor.epoch_times) / 3600 if training_monitor.epoch_times else 0
        logger.info(f"⏱️ Estimated time saved: {saved_hours:.1f} hours")

    # Check if best model was restored
    if os.path.exists(checkpoint_path):
        logger.info(f"📁 Best model checkpoint available at: {checkpoint_path}")
        # Load best model if early stopping didn't restore it
        if not early_stopping.restore_best_weights:
            logger.info("Loading best model from checkpoint...")
            model = tf.keras.models.load_model(checkpoint_path)
    
    # STEP 5: Evaluate on test set with distributed test dataset
    logger.info("\n📊 POST-TRAINING EVALUATION:")
    test_dataset = create_test_dataset_after_training(file_pattern, total_examples, per_replica_batch_size, strategy)
    
    test_steps = max(1, int(total_examples * 0.05) // global_batch_size)  # 5% of data
    test_metrics = evaluate_model_on_test_set(model, test_dataset, product_ids, art_name_vocab, category_vocab, subcategory_vocab, args.tfrecords_path, test_steps)
    
    # STEP 6: Save model
    logger.info("💾 Saving model...")
    
    # Create serving signature
    logger.info("Creating serving signature with product metadata support...")
    simple_serve_fn = _get_simple_serve_fn(model, product_ids, art_name_vocab, category_vocab, subcategory_vocab, args.tfrecords_path)
    signatures = {
        'serving_default': simple_serve_fn.get_concrete_function(
            customer_id=tf.TensorSpec(shape=[], dtype=tf.string, name='customer_id'),
            city=tf.TensorSpec(shape=[], dtype=tf.string, name='city'), 
            revenue=tf.TensorSpec(shape=[], dtype=tf.float32, name='revenue'),
            timestamp=tf.TensorSpec(shape=[], dtype=tf.int64, name='timestamp')
        )
    }
    
    if args.output_path.startswith('gs://'):
        # Save locally first using tf.saved_model.save - SAME as baseline
        local_path = '/tmp/enhanced_model_multigpu'
        os.makedirs(local_path, exist_ok=True)
        
        # Save the complete model with serving signature
        saved_model_path = os.path.join(local_path, 'saved_model')
        tf.saved_model.save(model, saved_model_path, signatures=signatures)
        logger.info("✅ Saved complete single VM model with serving signature")
        
        # Also save individual components for debugging
        query_model_path = os.path.join(local_path, 'query_model')
        candidate_model_path = os.path.join(local_path, 'candidate_model')
        
        tf.saved_model.save(model.query_model, query_model_path)
        tf.saved_model.save(model.candidate_model, candidate_model_path)
        
        # Upload to GCS
        storage_client = storage.Client()
        bucket_name = args.output_path.split('/')[2]
        bucket = storage_client.bucket(bucket_name)
        
        def upload_directory(local_dir, gcs_prefix):
            for root, dirs, files in os.walk(local_dir):
                for file in files:
                    local_file = os.path.join(root, file)
                    relative_path = os.path.relpath(local_file, local_dir)
                    gcs_path = f"{'/'.join(args.output_path.split('/')[3:])}/{gcs_prefix}/{relative_path}"
                    blob = bucket.blob(gcs_path)
                    blob.upload_from_filename(local_file)
        
        upload_directory(f"{local_path}/saved_model", "saved_model")
        upload_directory(f"{local_path}/query_model", "query_model")
        upload_directory(f"{local_path}/candidate_model", "candidate_model")
        
        # Save metadata with single VM multi-GPU training info
        metadata = {
            "model_version": "v7-single-vm-multigpu-early-stopping",
            "architecture": "original_128_64_32_with_early_stopping_and_lr_reduction",
            "distributed_training": {
                "strategy": str(strategy.__class__.__name__),
                "num_replicas": strategy.num_replicas_in_sync,
                "per_replica_batch_size": per_replica_batch_size,
                "global_batch_size": global_batch_size
            },
            "paths": {
                "saved_model": f"{args.output_path}/saved_model",
                "query_model": f"{args.output_path}/query_model",
                "candidate_model": f"{args.output_path}/candidate_model"
            },
            "vocabularies": {
                "num_users": len(user_vocab),
                "num_products": len(product_ids),
                "num_cities": len(city_vocab),
                "num_categories": len(category_vocab),
                "num_subcategories": len(subcategory_vocab)
            },
            "hyperparameters": {
                "embedding_dims": {
                    "customer": "64D (high cardinality)",
                    "product": "32D (medium cardinality)",
                    "city": "16D (low cardinality)",
                    "category": "16D (low cardinality)",
                    "subcategory": "24D (medium cardinality)"
                },
                "feature_crossing": {
                    "customer_city": "5,000 bins → 16D",
                    "revenue_time": "3,000 bins → 12D"
                },
                "cyclical_features": {
                    "day_of_week": "sin/cos encoding",
                    "week_number": "sin/cos encoding (0-51)",
                    "day_of_month": "sin/cos encoding",
                    "month_of_year": "sin/cos encoding"
                },
                "architecture": "128→64→32 Dense (ORIGINAL baseline architecture)",
                "batch_size": per_replica_batch_size,
                "global_batch_size": global_batch_size,
                "base_learning_rate": base_learning_rate,
                "scaled_learning_rate": scaled_learning_rate,
                "lr_scaling_factor": strategy.num_replicas_in_sync,
                "epochs_requested": args.epochs,
                "epochs_trained": actual_epochs,
                "early_stopping_patience": args.early_stopping_patience,
                "reduce_lr_patience": args.reduce_lr_patience,
                "min_epochs": args.min_epochs,
                "gradient_clipping": "clipnorm=1.0"
            },
            "metrics": {
                "test_metrics": test_metrics
            }
        }
        
        metadata_json = json.dumps(metadata, indent=2)
        blob = bucket.blob(f"{'/'.join(args.output_path.split('/')[3:])}/model_metadata.json")
        blob.upload_from_string(metadata_json)
    
    # Results
    logger.info("=" * 60)
    logger.info("🎉 SINGLE VM MULTI-GPU TRAINING WITH PRODUCT METADATA COMPLETED!")
    logger.info(f"🚀 Training strategy: {strategy.__class__.__name__}")
    logger.info(f"🎯 Total GPUs used: {strategy.num_replicas_in_sync}")
    logger.info(f"📊 Global batch size: {global_batch_size}")
    logger.info(f"📊 Recall@5:   {test_metrics['test_recall_5']:.4f} ({test_metrics['test_recall_5']*100:.2f}%)")
    logger.info(f"📊 Recall@10:  {test_metrics['test_recall_10']:.4f} ({test_metrics['test_recall_10']*100:.2f}%)")
    logger.info(f"📊 Recall@50:  {test_metrics['test_recall_50']:.4f} ({test_metrics['test_recall_50']*100:.2f}%)")
    logger.info(f"📊 Recall@100: {test_metrics['test_recall_100']:.4f} ({test_metrics['test_recall_100']*100:.2f}%)")
    logger.info("🎯 Key features:")
    logger.info("   ✓ Single VM multi-GPU training (simplified)")
    logger.info("   ✓ Customer: 32D→64D (high cardinality)")
    logger.info("   ✓ City: 32D→16D (low cardinality)")
    logger.info("   ✓ Customer×City crossing (location patterns)")
    logger.info("   ✓ Revenue×Time crossing (temporal spending)")
    logger.info("   ✓ Cyclical features: week, day of week, day of month, month")
    logger.info("   ✓ Product metadata: categories (16D), subcategories (24D)")
    logger.info("   ✓ FIXED: Proper metadata lookup during evaluation")
    logger.info("   ✓ ORIGINAL: 128→64→32 architecture")
    logger.info("   ✓ NEW: Early stopping, LR reduction, model checkpointing")
    logger.info("   ✓ NEW: Gradient clipping for stable training")
    logger.info("   ✓ NEW: Training monitoring and convergence detection")
    logger.info("   ✓ Optimized for 50M examples on single powerful VM")
    logger.info("   ✓ NVLink GPU communication for best performance")
    logger.info(f"📁 Model saved to: {args.output_path}")
    logger.info("=" * 60)


def main():
    """Main function with distributed training support."""
    parser = argparse.ArgumentParser(description='Single VM Multi-GPU Metro Retrieval Trainer v2 with Early Stopping')
    parser.add_argument('--tfrecords-path', required=True)
    parser.add_argument('--vocabularies-path', required=True)
    parser.add_argument('--metadata-path', required=True)
    parser.add_argument('--output-path', required=True)
    parser.add_argument('--epochs', type=int, default=150)
    parser.add_argument('--learning-rate', type=float, default=0.001)
    parser.add_argument('--batch-size', type=int, default=2048, help='Per-replica batch size (use -1 for auto-selection)')
    parser.add_argument('--lr-scaling', type=str, default='sqrt',
                       choices=['linear', 'sqrt', 'none'],
                       help='Learning rate scaling strategy: linear (fast but may hurt accuracy), sqrt (recommended for accuracy), none (conservative)')
    parser.add_argument('--warmup-steps', type=int, default=0,
                       help='Number of warmup steps for learning rate (0 = no warmup). Recommended: 500-1000 for large batch training')

    # New arguments for early stopping and LR reduction
    parser.add_argument('--early-stopping-patience', type=int, default=10,
                       help='Epochs to wait before early stopping (default: 10)')
    parser.add_argument('--reduce-lr-patience', type=int, default=5,
                       help='Epochs to wait before reducing learning rate (default: 5)')
    parser.add_argument('--min-epochs', type=int, default=20,
                       help='Minimum epochs to train before allowing early stopping (default: 20)')
    parser.add_argument('--enable-tensorboard', action='store_true',
                       help='Enable TensorBoard logging')

    # Keep for compatibility
    parser.add_argument('--embedding-dim', type=int, default=32)  # Keep for compatibility
    parser.add_argument('--revenue-buckets', type=int, default=1000)  # Keep for compatibility
    
    args = parser.parse_args()
    
    train_model(args)
    logger.info("✅ Single VM multi-GPU training v2 with early stopping completed successfully!")


if __name__ == "__main__":
    main()