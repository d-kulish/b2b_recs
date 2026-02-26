#!/usr/bin/env python3
"""
Taste Vector Validation Experiment

Standalone Custom Job that bypasses the TFX pipeline to test the purchase_history
"taste vector" feature. Reads directly from BigQuery v4 views, builds a TFRS
retrieval model with shared product embedding + masked averaging, and trains
on GPU.

Baseline: Experiment QT#28 (ID 162) — Recall@100 = 0.3308

Usage:
    # Quick test (5 epochs)
    python scripts/test_taste_vector.py --epochs 5

    # Full experiment matching baseline (100 epochs, wait for results)
    python scripts/test_taste_vector.py --epochs 100 --wait --timeout 60

    # Dry run (upload script to GCS, don't submit job)
    python scripts/test_taste_vector.py --epochs 100 --dry-run
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ID = 'b2b-recs'
REGION = 'europe-west4'  # GPU training region
JOB_STAGING_BUCKET = 'b2b-recs-gpu-staging'  # Must be in REGION
ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
TRAINER_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu:latest'

# BigQuery tables (v4 views with purchase_history)
BQ_TRAIN_TABLE = 'b2b-recs.raw_data.ternopil_train_v4'
BQ_TEST_TABLE = 'b2b-recs.raw_data.ternopil_test_v4'

# Column name mapping (BQ column -> model feature name)
# Must match experiment #162's FeatureConfig aliases
COLUMN_ALIASES = {
    'days_since_last_purchase': 'cust_last_purchase',
    'cust_order_days_60d': 'cust_visits',
    'cust_unique_products_60d': 'cust_bought_SKU',
    'stratbuy_domain_desc': 'category',
    'mge_main_cat_desc': 'sub_category_v1',
    'mge_cat_desc': 'sub_category_v2',
    'brand_name': 'brand',
    'art_name': 'name',
    'prod_unique_buyers': 'pr_unique_buyers',
    'prod_order_count': 'pr_order_counts',
    'prod_total_sales': 'pr_total_sales',
    'prod_avg_sale': 'pr_avg_sales',
    'prod_cat_revenue_pctile': 'pr_categ_percent',
}


def create_runner_script(gcs_output_path: str, epochs: int, learning_rate: float,
                         batch_size: int, gpu_count: int) -> str:
    """Generate the inner script that runs inside the Vertex AI Custom Job."""

    return f'''#!/usr/bin/env python3
"""
Taste Vector Experiment — Inner Runner Script
Runs inside Vertex AI Custom Job on GPU VM.

Reads from BigQuery, preprocesses, builds TFRS model with shared embedding
+ purchase_history taste vector, trains, evaluates, saves metrics.
"""
import os
import json
import time
import logging
import math
import numpy as np
import pandas as pd
from datetime import datetime
from collections import Counter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ID = '{PROJECT_ID}'
BQ_TRAIN_TABLE = '{BQ_TRAIN_TABLE}'
BQ_TEST_TABLE = '{BQ_TEST_TABLE}'
GCS_OUTPUT_PATH = '{gcs_output_path}'

EPOCHS = {epochs}
LEARNING_RATE = {learning_rate}
BATCH_SIZE = {batch_size}
GPU_COUNT = {gpu_count}

OUTPUT_EMBEDDING_DIM = 32
PRODUCT_EMBEDDING_DIM = 32
CUSTOMER_EMBEDDING_DIM = 64
MAX_HISTORY_LENGTH = 50
NUM_BUCKETS = 100
CROSS_HASH_BUCKETS = 5000
L2_REGULARIZATION = 0.02
TOP_K = 150

# Column aliases (BQ name -> model feature name)
COLUMN_ALIASES = {repr(COLUMN_ALIASES)}

# Features by role
BUYER_CATEGORICAL_FEATURES = []  # customer_id handled separately
BUYER_NUMERIC_FEATURES = ['cust_value', 'cust_last_purchase', 'cust_visits', 'cust_bought_SKU']
BUYER_NUMERIC_EMBED_DIM = 16
BUYER_CROSSES = [
    ('date', 'cust_value'),
    ('date', 'cust_bought_SKU'),
    ('date', 'cust_last_purchase'),
    ('date', 'cust_visits'),
]

PRODUCT_CATEGORICAL_FEATURES = {{
    'category': 8,
    'sub_category_v1': 16,
    'sub_category_v2': 16,
    'brand': 32,
    'name': 32,
}}
PRODUCT_NUMERIC_FEATURES = ['pr_unique_buyers', 'pr_order_counts', 'pr_total_sales', 'pr_avg_sales', 'pr_categ_percent']
PRODUCT_NUMERIC_EMBED_DIM = 16
PRODUCT_CROSSES = [
    ('sub_category_v1', 'brand'),
]


# =============================================================================
# DATA LOADING
# =============================================================================

def read_bigquery(table_name):
    """Read a BigQuery table/view into a pandas DataFrame."""
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID)
    query = f'SELECT * FROM `{{table_name}}`'
    logger.info(f"Reading from BigQuery: {{table_name}}")
    df = client.query(query).to_dataframe()
    logger.info(f"  Loaded {{len(df)}} rows, {{len(df.columns)}} columns")
    return df


def apply_aliases(df):
    """Rename columns using the alias mapping."""
    rename_map = {{k: v for k, v in COLUMN_ALIASES.items() if k in df.columns}}
    df = df.rename(columns=rename_map)
    return df


# =============================================================================
# PREPROCESSING
# =============================================================================

def build_vocabularies(train_df):
    """Build vocabulary mappings from training data. Index 0 is reserved for OOV/padding."""
    vocabs = {{}}

    # customer_id vocab
    unique_customers = train_df['customer_id'].dropna().unique()
    vocabs['customer_id'] = {{v: i + 1 for i, v in enumerate(sorted(unique_customers))}}
    logger.info(f"  customer_id vocab: {{len(vocabs['customer_id'])}} entries")

    # product_id vocab (shared with purchase_history)
    unique_products = train_df['product_id'].dropna().unique()
    vocabs['product_id'] = {{v: i + 1 for i, v in enumerate(sorted(unique_products))}}
    logger.info(f"  product_id vocab: {{len(vocabs['product_id'])}} entries (shared with purchase_history)")

    # Categorical feature vocabs
    for feat in list(PRODUCT_CATEGORICAL_FEATURES.keys()):
        unique_vals = train_df[feat].dropna().unique()
        vocabs[feat] = {{v: i + 1 for i, v in enumerate(sorted(unique_vals))}}
        logger.info(f"  {{feat}} vocab: {{len(vocabs[feat])}} entries")

    return vocabs


def compute_normalization_stats(train_df):
    """Compute mean/std for z-score normalization from training data."""
    stats = {{}}
    all_numeric = BUYER_NUMERIC_FEATURES + PRODUCT_NUMERIC_FEATURES
    for feat in all_numeric:
        col = train_df[feat].astype(float)
        stats[feat] = {{'mean': col.mean(), 'std': col.std() + 1e-8}}
        logger.info(f"  {{feat}}: mean={{stats[feat]['mean']:.4f}}, std={{stats[feat]['std']:.4f}}")

    # Date stats (seconds since epoch)
    date_seconds = train_df['date'].astype('int64') // 10**9
    stats['date'] = {{'mean': date_seconds.mean(), 'std': date_seconds.std() + 1e-8}}
    logger.info(f"  date: mean={{stats['date']['mean']:.0f}}, std={{stats['date']['std']:.0f}}")

    return stats


def compute_bucket_boundaries(train_df, stats):
    """Compute quantile-based bucket boundaries for each numeric feature."""
    boundaries = {{}}
    all_numeric = BUYER_NUMERIC_FEATURES + PRODUCT_NUMERIC_FEATURES
    for feat in all_numeric:
        # Compute normalized values first, then bucketize
        col = (train_df[feat].astype(float) - stats[feat]['mean']) / stats[feat]['std']
        quantiles = np.linspace(0, 1, NUM_BUCKETS + 1)[1:-1]
        bounds = np.quantile(col.dropna().values, quantiles)
        boundaries[feat] = bounds
    # Date boundaries
    date_seconds = train_df['date'].astype('int64') // 10**9
    col = (date_seconds - stats['date']['mean']) / stats['date']['std']
    quantiles = np.linspace(0, 1, NUM_BUCKETS + 1)[1:-1]
    boundaries['date'] = np.quantile(col.dropna().values, quantiles)
    return boundaries


def preprocess_dataframe(df, vocabs, stats, boundaries, is_test=False):
    """Preprocess a DataFrame into model-ready numpy arrays."""
    result = {{}}

    # --- customer_id → vocab index ---
    result['customer_id'] = df['customer_id'].map(vocabs['customer_id']).fillna(0).astype(np.int32).values

    # --- product_id → vocab index (shared vocab) ---
    result['product_id'] = df['product_id'].map(vocabs['product_id']).fillna(0).astype(np.int32).values

    # --- purchase_history → padded array of vocab indices ---
    product_vocab = vocabs['product_id']
    histories = []
    for hist in df['purchase_history']:
        if hist is None or (isinstance(hist, float) and np.isnan(hist)):
            histories.append(np.zeros(MAX_HISTORY_LENGTH, dtype=np.int32))
        else:
            mapped = [product_vocab.get(pid, 0) for pid in hist[:MAX_HISTORY_LENGTH]]
            padded = mapped + [0] * (MAX_HISTORY_LENGTH - len(mapped))
            histories.append(np.array(padded, dtype=np.int32))
    result['purchase_history'] = np.stack(histories)

    # --- Categorical features → vocab indices ---
    for feat in PRODUCT_CATEGORICAL_FEATURES:
        result[feat] = df[feat].map(vocabs[feat]).fillna(0).astype(np.int32).values

    # --- Numeric features → normalized + bucketized ---
    all_numeric = BUYER_NUMERIC_FEATURES + PRODUCT_NUMERIC_FEATURES
    for feat in all_numeric:
        col = df[feat].astype(float).values
        norm = (col - stats[feat]['mean']) / stats[feat]['std']
        norm = np.nan_to_num(norm, nan=0.0)
        result[f'{{feat}}_norm'] = norm.astype(np.float32)
        result[f'{{feat}}_bucket'] = np.digitize(norm, boundaries[feat]).astype(np.int32)

    # --- Date → normalized + cyclical + bucketized ---
    date_seconds = df['date'].astype('int64') // 10**9
    date_norm = ((date_seconds - stats['date']['mean']) / stats['date']['std']).values.astype(np.float32)
    result['date_norm'] = date_norm
    result['date_bucket'] = np.digitize(date_norm, boundaries['date']).astype(np.int32)

    # Cyclical date features
    timestamps = pd.to_datetime(df['date'])
    day_of_week = timestamps.dt.dayofweek.values.astype(float)
    day_of_month = timestamps.dt.day.values.astype(float)
    result['date_weekly_sin'] = np.sin(2 * np.pi * day_of_week / 7).astype(np.float32)
    result['date_weekly_cos'] = np.cos(2 * np.pi * day_of_week / 7).astype(np.float32)
    result['date_monthly_sin'] = np.sin(2 * np.pi * day_of_month / 31).astype(np.float32)
    result['date_monthly_cos'] = np.cos(2 * np.pi * day_of_month / 31).astype(np.float32)

    # --- Cross features → hash bucket indices ---
    for feat_a, feat_b in BUYER_CROSSES + PRODUCT_CROSSES:
        # Bucketize each feature into 10 bins for cross
        a_vals = result.get(f'{{feat_a}}_bucket', result.get(feat_a, np.zeros(len(df), dtype=np.int32)))
        b_vals = result.get(f'{{feat_b}}_bucket', result.get(feat_b, np.zeros(len(df), dtype=np.int32)))
        a_bins = np.clip(a_vals * 10 // (NUM_BUCKETS + 1), 0, 9)
        b_bins = np.clip(b_vals * 10 // (NUM_BUCKETS + 1), 0, 9)
        # Combine and hash
        combined = (a_bins.astype(np.int64) * 31 + b_bins.astype(np.int64)) % CROSS_HASH_BUCKETS
        result[f'{{feat_a}}_x_{{feat_b}}_cross'] = combined.astype(np.int32)

    return result


def create_tf_dataset(preprocessed, batch_size, shuffle=True):
    """Convert preprocessed numpy dict to tf.data.Dataset."""
    import tensorflow as tf

    ds = tf.data.Dataset.from_tensor_slices(preprocessed)
    if shuffle:
        ds = ds.shuffle(buffer_size=min(len(list(preprocessed.values())[0]), 50000))
    ds = ds.batch(batch_size)
    ds = ds.prefetch(tf.data.AUTOTUNE)
    return ds


# =============================================================================
# METRICS COLLECTOR (matches platform MetricsCollector format)
# =============================================================================

class MetricsCollector:
    """Collects training metrics and saves to GCS as training_metrics.json."""

    def __init__(self, gcs_output_path=None):
        self.gcs_output_path = gcs_output_path
        self._current_epoch = -1
        self.metrics = {{
            'epochs': [],
            'loss': {{}},
            'gradient': {{}},
            'weight_stats': {{
                'query': {{'mean': [], 'std': [], 'min': [], 'max': [], 'histogram': {{'bin_edges': [], 'counts': []}}}},
                'candidate': {{'mean': [], 'std': [], 'min': [], 'max': [], 'histogram': {{'bin_edges': [], 'counts': []}}}},
            }},
            'gradient_stats': {{
                'query': {{'mean': [], 'std': [], 'min': [], 'max': [], 'norm': [], 'histogram': {{'bin_edges': [], 'counts': []}}}},
                'candidate': {{'mean': [], 'std': [], 'min': [], 'max': [], 'norm': [], 'histogram': {{'bin_edges': [], 'counts': []}}}},
            }},
            'final_metrics': {{}},
            'params': {{}},
            'available': True,
        }}

    def log_param(self, key, value):
        self.metrics['params'][key] = value

    def log_params(self, params):
        for k, v in params.items():
            self.log_param(k, v)

    def log_metric(self, key, value, step=None):
        value = float(value)
        if step is not None and step > self._current_epoch:
            self._current_epoch = step
            if step not in self.metrics['epochs']:
                self.metrics['epochs'].append(step)
        if key.startswith('final_') or key.startswith('test_'):
            self.metrics['final_metrics'][key] = value
        elif 'weight_norm' in key:
            norm_key = key.replace('_weight_norm', '').replace('weight_norm', 'total')
            if norm_key not in self.metrics['gradient']:
                self.metrics['gradient'][norm_key] = []
            self.metrics['gradient'][norm_key].append(value)
        elif 'loss' in key:
            if key not in self.metrics['loss']:
                self.metrics['loss'][key] = []
            self.metrics['loss'][key].append(value)
        else:
            if key not in self.metrics['loss']:
                self.metrics['loss'][key] = []
            self.metrics['loss'][key].append(value)

    def log_weight_stats(self, tower, stats, histogram=None):
        ts = self.metrics['weight_stats'].get(tower, {{}})
        for s in ['mean', 'std', 'min', 'max']:
            if s in stats:
                if s not in ts: ts[s] = []
                ts[s].append(float(stats[s]))
        if histogram:
            if 'histogram' not in ts: ts['histogram'] = {{'bin_edges': None, 'counts': []}}
            if 'bin_edges' in histogram and histogram['bin_edges'] and not ts['histogram'].get('bin_edges'):
                ts['histogram']['bin_edges'] = histogram['bin_edges']
            if 'counts' in histogram:
                ts['histogram']['counts'].append(histogram['counts'])
        self.metrics['weight_stats'][tower] = ts

    def log_gradient_stats(self, tower, stats, histogram=None):
        ts = self.metrics['gradient_stats'].get(tower, {{}})
        for s in ['mean', 'std', 'min', 'max', 'norm']:
            if s in stats:
                if s not in ts: ts[s] = []
                ts[s].append(float(stats[s]))
        if histogram:
            if 'histogram' not in ts: ts['histogram'] = {{'bin_edges': None, 'counts': []}}
            if 'bin_edges' in histogram and histogram['bin_edges'] and not ts['histogram'].get('bin_edges'):
                ts['histogram']['bin_edges'] = histogram['bin_edges']
            if 'counts' in histogram:
                ts['histogram']['counts'].append(histogram['counts'])
        self.metrics['gradient_stats'][tower] = ts

    def save_to_gcs(self):
        if not self.gcs_output_path or not self.gcs_output_path.startswith('gs://'):
            logger.warning("No valid GCS output path")
            return False
        try:
            from google.cloud import storage
            self.metrics['saved_at'] = datetime.utcnow().isoformat() + 'Z'
            path = self.gcs_output_path[5:]
            bucket_name = path.split('/')[0]
            blob_path = '/'.join(path.split('/')[1:]) + '/training_metrics.json'
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            blob.upload_from_string(json.dumps(self.metrics, indent=2), content_type='application/json')
            logger.info(f"Saved metrics to gs://{{bucket_name}}/{{blob_path}}")
            return True
        except Exception as e:
            logger.warning(f"Could not save metrics: {{e}}")
            return False


_metrics_collector = None


# =============================================================================
# MODEL DEFINITION
# =============================================================================

def build_model_and_train():
    """Main function: build model, train, evaluate, save metrics."""
    import tensorflow as tf
    import tensorflow_recommenders as tfrs

    # --- GPU Setup ---
    logger.info("=" * 60)
    logger.info("GPU DETECTION")
    logger.info("=" * 60)
    logger.info(f"TensorFlow version: {{tf.__version__}}")

    physical_gpus = tf.config.list_physical_devices('GPU')
    logger.info(f"Physical GPUs: {{len(physical_gpus)}}")
    for i, gpu in enumerate(physical_gpus):
        logger.info(f"  GPU {{i}}: {{gpu.name}}")
        try:
            tf.config.experimental.set_memory_growth(gpu, True)
        except RuntimeError:
            pass

    if GPU_COUNT > 0 and len(physical_gpus) == 0:
        raise RuntimeError(f"GPU requested but none detected")

    strategy = tf.distribute.get_strategy()
    logger.info(f"Strategy: {{type(strategy).__name__}}")

    # --- Load Data ---
    logger.info("=" * 60)
    logger.info("LOADING DATA FROM BIGQUERY")
    logger.info("=" * 60)

    train_df = read_bigquery(BQ_TRAIN_TABLE)
    test_df = read_bigquery(BQ_TEST_TABLE)

    train_df = apply_aliases(train_df)
    test_df = apply_aliases(test_df)

    logger.info(f"Train: {{len(train_df)}} rows, {{train_df['customer_id'].nunique()}} customers, {{train_df['product_id'].nunique()}} products")
    logger.info(f"Test: {{len(test_df)}} rows, {{test_df['customer_id'].nunique()}} customers, {{test_df['product_id'].nunique()}} products")
    logger.info(f"Test null purchase_history: {{test_df['purchase_history'].isna().sum()}} ({{test_df['purchase_history'].isna().mean()*100:.1f}}%)")

    # --- Preprocessing ---
    logger.info("=" * 60)
    logger.info("PREPROCESSING")
    logger.info("=" * 60)

    vocabs = build_vocabularies(train_df)
    stats = compute_normalization_stats(train_df)
    boundaries = compute_bucket_boundaries(train_df, stats)

    product_vocab_size = len(vocabs['product_id'])
    customer_vocab_size = len(vocabs['customer_id'])
    logger.info(f"Product vocab size: {{product_vocab_size}} (+ 1 OOV = {{product_vocab_size + 1}})")
    logger.info(f"Customer vocab size: {{customer_vocab_size}} (+ 1 OOV = {{customer_vocab_size + 1}})")

    cat_vocab_sizes = {{feat: len(vocabs[feat]) for feat in PRODUCT_CATEGORICAL_FEATURES}}
    logger.info(f"Categorical vocab sizes: {{cat_vocab_sizes}}")

    train_data = preprocess_dataframe(train_df, vocabs, stats, boundaries)
    test_data = preprocess_dataframe(test_df, vocabs, stats, boundaries, is_test=True)

    logger.info(f"Preprocessed train: {{len(train_data['customer_id'])}} rows")
    logger.info(f"Preprocessed test: {{len(test_data['customer_id'])}} rows")
    logger.info(f"Purchase history shape: {{train_data['purchase_history'].shape}}")

    # --- Create tf.data.Dataset ---
    # Split train into train/val (90/10)
    n = len(train_data['customer_id'])
    n_val = int(n * 0.1)
    indices = np.random.permutation(n)
    val_indices = indices[:n_val]
    train_indices = indices[n_val:]

    train_split = {{k: v[train_indices] for k, v in train_data.items()}}
    val_split = {{k: v[val_indices] for k, v in train_data.items()}}

    train_ds = create_tf_dataset(train_split, BATCH_SIZE, shuffle=True)
    val_ds = create_tf_dataset(val_split, BATCH_SIZE, shuffle=False)
    test_ds = create_tf_dataset(test_data, BATCH_SIZE, shuffle=False)

    # --- Model Definition ---
    logger.info("=" * 60)
    logger.info("BUILDING MODEL")
    logger.info("=" * 60)

    class BuyerModel(tf.keras.Model):
        """Query tower with purchase_history taste vector."""

        def __init__(self, shared_product_embedding):
            super().__init__()
            self.shared_product_embedding = shared_product_embedding

            self.customer_id_embedding = tf.keras.layers.Embedding(customer_vocab_size + 1, CUSTOMER_EMBEDDING_DIM)

            # Numeric bucket embeddings
            self.cust_value_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, BUYER_NUMERIC_EMBED_DIM)
            self.cust_last_purchase_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, BUYER_NUMERIC_EMBED_DIM)
            self.cust_visits_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, BUYER_NUMERIC_EMBED_DIM)
            self.cust_bought_SKU_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, BUYER_NUMERIC_EMBED_DIM)
            self.date_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, BUYER_NUMERIC_EMBED_DIM)

            # Cross embeddings
            self.date_x_cust_value_cross_emb = tf.keras.layers.Embedding(CROSS_HASH_BUCKETS, 16)
            self.date_x_cust_bought_SKU_cross_emb = tf.keras.layers.Embedding(CROSS_HASH_BUCKETS, 16)
            self.date_x_cust_last_purchase_cross_emb = tf.keras.layers.Embedding(CROSS_HASH_BUCKETS, 16)
            self.date_x_cust_visits_cross_emb = tf.keras.layers.Embedding(CROSS_HASH_BUCKETS, 16)

        def call(self, inputs):
            features = []

            # customer_id
            features.append(self.customer_id_embedding(inputs['customer_id']))

            # ★ Purchase history taste vector (shared product embedding + masked average)
            history_ids = inputs['purchase_history']  # [batch, MAX_HISTORY_LENGTH]
            history_embs = self.shared_product_embedding(history_ids)  # [batch, 50, 32]
            mask = tf.cast(history_ids != 0, tf.float32)  # [batch, 50]
            mask = tf.expand_dims(mask, -1)  # [batch, 50, 1]
            avg_history = tf.reduce_sum(history_embs * mask, axis=1)  # [batch, 32]
            avg_history = avg_history / (tf.reduce_sum(mask, axis=1) + 1e-8)  # [batch, 32]
            features.append(avg_history)

            # Numeric features: normalized value (1D) + bucket embedding (16D)
            features.append(tf.reshape(inputs['cust_value_norm'], (-1, 1)))
            features.append(self.cust_value_bucket_emb(inputs['cust_value_bucket']))
            features.append(tf.reshape(inputs['cust_last_purchase_norm'], (-1, 1)))
            features.append(self.cust_last_purchase_bucket_emb(inputs['cust_last_purchase_bucket']))
            features.append(tf.reshape(inputs['cust_visits_norm'], (-1, 1)))
            features.append(self.cust_visits_bucket_emb(inputs['cust_visits_bucket']))
            features.append(tf.reshape(inputs['cust_bought_SKU_norm'], (-1, 1)))
            features.append(self.cust_bought_SKU_bucket_emb(inputs['cust_bought_SKU_bucket']))

            # Date: normalized + cyclical + bucket
            features.append(tf.reshape(inputs['date_norm'], (-1, 1)))
            features.append(tf.reshape(inputs['date_monthly_sin'], (-1, 1)))
            features.append(tf.reshape(inputs['date_monthly_cos'], (-1, 1)))
            features.append(tf.reshape(inputs['date_weekly_sin'], (-1, 1)))
            features.append(tf.reshape(inputs['date_weekly_cos'], (-1, 1)))
            features.append(self.date_bucket_emb(inputs['date_bucket']))

            # Cross features
            features.append(self.date_x_cust_value_cross_emb(inputs['date_x_cust_value_cross']))
            features.append(self.date_x_cust_bought_SKU_cross_emb(inputs['date_x_cust_bought_SKU_cross']))
            features.append(self.date_x_cust_last_purchase_cross_emb(inputs['date_x_cust_last_purchase_cross']))
            features.append(self.date_x_cust_visits_cross_emb(inputs['date_x_cust_visits_cross']))

            return tf.concat(features, axis=1)

    class ProductModel(tf.keras.Model):
        """Candidate tower (matches #162 exactly, uses shared product embedding)."""

        def __init__(self, shared_product_embedding):
            super().__init__()
            self.shared_product_embedding = shared_product_embedding

            self.category_emb = tf.keras.layers.Embedding(cat_vocab_sizes.get('category', 0) + 1, 8)
            self.sub_category_v1_emb = tf.keras.layers.Embedding(cat_vocab_sizes.get('sub_category_v1', 0) + 1, 16)
            self.sub_category_v2_emb = tf.keras.layers.Embedding(cat_vocab_sizes.get('sub_category_v2', 0) + 1, 16)
            self.brand_emb = tf.keras.layers.Embedding(cat_vocab_sizes.get('brand', 0) + 1, 32)
            self.name_emb = tf.keras.layers.Embedding(cat_vocab_sizes.get('name', 0) + 1, 32)

            # Product numeric bucket embeddings
            self.pr_unique_buyers_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, PRODUCT_NUMERIC_EMBED_DIM)
            self.pr_order_counts_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, PRODUCT_NUMERIC_EMBED_DIM)
            self.pr_total_sales_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, PRODUCT_NUMERIC_EMBED_DIM)
            self.pr_avg_sales_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, PRODUCT_NUMERIC_EMBED_DIM)
            self.pr_categ_percent_bucket_emb = tf.keras.layers.Embedding(NUM_BUCKETS + 1, PRODUCT_NUMERIC_EMBED_DIM)

            # Cross embedding
            self.sub_category_v1_x_brand_cross_emb = tf.keras.layers.Embedding(CROSS_HASH_BUCKETS, 16)

        def call(self, inputs):
            features = []

            features.append(self.shared_product_embedding(inputs['product_id']))
            features.append(self.category_emb(inputs['category']))
            features.append(self.sub_category_v1_emb(inputs['sub_category_v1']))
            features.append(self.sub_category_v2_emb(inputs['sub_category_v2']))
            features.append(self.brand_emb(inputs['brand']))
            features.append(self.name_emb(inputs['name']))

            # Product numerics
            features.append(tf.reshape(inputs['pr_unique_buyers_norm'], (-1, 1)))
            features.append(self.pr_unique_buyers_bucket_emb(inputs['pr_unique_buyers_bucket']))
            features.append(tf.reshape(inputs['pr_order_counts_norm'], (-1, 1)))
            features.append(self.pr_order_counts_bucket_emb(inputs['pr_order_counts_bucket']))
            features.append(tf.reshape(inputs['pr_total_sales_norm'], (-1, 1)))
            features.append(self.pr_total_sales_bucket_emb(inputs['pr_total_sales_bucket']))
            features.append(tf.reshape(inputs['pr_avg_sales_norm'], (-1, 1)))
            features.append(self.pr_avg_sales_bucket_emb(inputs['pr_avg_sales_bucket']))
            features.append(tf.reshape(inputs['pr_categ_percent_norm'], (-1, 1)))
            features.append(self.pr_categ_percent_bucket_emb(inputs['pr_categ_percent_bucket']))

            features.append(self.sub_category_v1_x_brand_cross_emb(inputs['sub_category_v1_x_brand_cross']))

            return tf.concat(features, axis=1)

    class TasteVectorRetrievalModel(tfrs.Model):
        """Two-tower retrieval model with shared product embedding for taste vector."""

        def __init__(self, shared_product_embedding):
            super().__init__()

            # Gradient accumulators (matching #162's pattern)
            self._grad_accum = {{}}
            for tower in ['query', 'candidate']:
                self._grad_accum[tower] = {{
                    'sum': tf.Variable(0.0, trainable=False, name=f'{{tower}}_grad_sum'),
                    'sum_sq': tf.Variable(0.0, trainable=False, name=f'{{tower}}_grad_sum_sq'),
                    'count': tf.Variable(0.0, trainable=False, name=f'{{tower}}_grad_count'),
                    'min': tf.Variable(float('inf'), trainable=False, name=f'{{tower}}_grad_min'),
                    'max': tf.Variable(float('-inf'), trainable=False, name=f'{{tower}}_grad_max'),
                    'hist_counts': tf.Variable(tf.zeros(25, dtype=tf.int32), trainable=False, name=f'{{tower}}_grad_hist'),
                }}

            self.buyer_model = BuyerModel(shared_product_embedding)
            self.product_model = ProductModel(shared_product_embedding)

            query_layers = [self.buyer_model]
            query_layers.append(tf.keras.layers.Dense(128, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(L2_REGULARIZATION)))
            query_layers.append(tf.keras.layers.Dense(64, activation='relu'))
            query_layers.append(tf.keras.layers.Dense(OUTPUT_EMBEDDING_DIM, activation='relu'))
            self.query_tower = tf.keras.Sequential(query_layers)

            candidate_layers = [self.product_model]
            candidate_layers.append(tf.keras.layers.Dense(128, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(L2_REGULARIZATION)))
            candidate_layers.append(tf.keras.layers.Dense(64, activation='relu'))
            candidate_layers.append(tf.keras.layers.Dense(OUTPUT_EMBEDDING_DIM, activation='relu'))
            self.candidate_tower = tf.keras.Sequential(candidate_layers)

            self.task = tfrs.tasks.Retrieval()

        def compute_loss(self, features, training=False):
            query_embeddings = self.query_tower(features)
            candidate_embeddings = self.candidate_tower(features)
            return self.task(query_embeddings, candidate_embeddings)

        def train_step(self, data):
            with tf.GradientTape() as tape:
                loss = self.compute_loss(data, training=True)
                regularization_loss = sum(self.losses) if self.losses else tf.constant(0.0)
                total_loss = loss + regularization_loss

            gradients = tape.gradient(total_loss, self.trainable_variables)
            self.optimizer.apply_gradients(zip(gradients, self.trainable_variables))

            # Accumulate gradient stats
            for grad, var in zip(gradients, self.trainable_variables):
                if grad is not None:
                    var_name = var.name.lower()
                    grad_flat = tf.reshape(tf.cast(grad, tf.float32), [-1])
                    if 'query' in var_name or 'buyer' in var_name:
                        tower = 'query'
                    elif 'candidate' in var_name or 'product' in var_name:
                        tower = 'candidate'
                    else:
                        continue
                    accum = self._grad_accum[tower]
                    accum['sum'].assign_add(tf.reduce_sum(grad_flat))
                    accum['sum_sq'].assign_add(tf.reduce_sum(tf.square(grad_flat)))
                    accum['count'].assign_add(tf.cast(tf.size(grad_flat), tf.float32))
                    accum['min'].assign(tf.minimum(accum['min'], tf.reduce_min(grad_flat)))
                    accum['max'].assign(tf.maximum(accum['max'], tf.reduce_max(grad_flat)))
                    grad_clipped = tf.clip_by_value(grad_flat, -1.0, 1.0)
                    hist = tf.histogram_fixed_width(grad_clipped, [-1.0, 1.0], nbins=25)
                    accum['hist_counts'].assign_add(hist)

            return dict(loss=loss, regularization_loss=regularization_loss, total_loss=total_loss)

    # --- Build and Compile ---
    with strategy.scope():
        shared_product_embedding = tf.keras.layers.Embedding(
            product_vocab_size + 1, PRODUCT_EMBEDDING_DIM, name='shared_product_embedding'
        )
        logger.info(f"Shared product embedding: ({{product_vocab_size + 1}}, {{PRODUCT_EMBEDDING_DIM}})")

        model = TasteVectorRetrievalModel(shared_product_embedding)
        optimizer = tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE, clipnorm=1.0)
        model.compile(optimizer=optimizer)

    logger.info(f"Optimizer: Adam (lr={{LEARNING_RATE}}, clipnorm=1.0)")

    # --- Initialize MetricsCollector ---
    global _metrics_collector
    _metrics_collector = MetricsCollector(gcs_output_path=GCS_OUTPUT_PATH)
    _metrics_collector.log_params({{
        'epochs': EPOCHS,
        'batch_size': BATCH_SIZE,
        'learning_rate': LEARNING_RATE,
        'optimizer': 'adam',
        'embedding_dim': OUTPUT_EMBEDDING_DIM,
        'model_type': 'retrieval',
        'taste_vector': True,
        'shared_embedding_dim': PRODUCT_EMBEDDING_DIM,
        'max_history_length': MAX_HISTORY_LENGTH,
        'product_vocab_size': product_vocab_size,
        'customer_vocab_size': customer_vocab_size,
        'baseline_experiment': 162,
    }})

    # --- Callbacks ---
    class MetricsCallback(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            if _metrics_collector and logs:
                for metric_name, value in logs.items():
                    _metrics_collector.log_metric(metric_name, float(value), step=epoch)

    class WeightNormCallback(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            if not _metrics_collector:
                return
            for tower_name in ['query', 'candidate']:
                tower = getattr(self.model, f'{{tower_name}}_tower', None)
                if tower:
                    all_weights = tf.concat([tf.reshape(w, [-1]) for w in tower.trainable_weights], axis=0)
                    norm = tf.norm(all_weights).numpy()
                    _metrics_collector.log_metric(f'{{tower_name}}_weight_norm', norm, step=epoch)
                    _metrics_collector.log_metric('weight_norm', norm, step=epoch)

    class WeightStatsCallback(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            if not _metrics_collector:
                return
            for tower_name in ['query', 'candidate']:
                tower = getattr(self.model, f'{{tower_name}}_tower', None)
                if tower:
                    all_w = tf.concat([tf.reshape(w, [-1]) for w in tower.trainable_weights], axis=0)
                    stats = {{
                        'mean': tf.reduce_mean(all_w).numpy(),
                        'std': tf.math.reduce_std(all_w).numpy(),
                        'min': tf.reduce_min(all_w).numpy(),
                        'max': tf.reduce_max(all_w).numpy(),
                    }}
                    hist = tf.histogram_fixed_width(tf.clip_by_value(all_w, -2.0, 2.0), [-2.0, 2.0], nbins=25)
                    bin_edges = np.linspace(-2.0, 2.0, 26).tolist()
                    _metrics_collector.log_weight_stats(tower_name, stats, {{
                        'bin_edges': bin_edges,
                        'counts': hist.numpy().tolist(),
                    }})

    class GradientStatsCallback(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            if not _metrics_collector:
                return
            for tower_name in ['query', 'candidate']:
                accum = self.model._grad_accum.get(tower_name)
                if accum:
                    count = accum['count'].numpy()
                    if count > 0:
                        mean = accum['sum'].numpy() / count
                        variance = (accum['sum_sq'].numpy() / count) - (mean ** 2)
                        std = np.sqrt(max(variance, 0))
                        norm = np.sqrt(accum['sum_sq'].numpy())
                        stats = {{
                            'mean': mean, 'std': std,
                            'min': accum['min'].numpy(),
                            'max': accum['max'].numpy(),
                            'norm': norm,
                        }}
                        bin_edges = np.linspace(-1.0, 1.0, 26).tolist()
                        _metrics_collector.log_gradient_stats(tower_name, stats, {{
                            'bin_edges': bin_edges,
                            'counts': accum['hist_counts'].numpy().tolist(),
                        }})
                    # Reset accumulators
                    accum['sum'].assign(0.0)
                    accum['sum_sq'].assign(0.0)
                    accum['count'].assign(0.0)
                    accum['min'].assign(float('inf'))
                    accum['max'].assign(float('-inf'))
                    accum['hist_counts'].assign(tf.zeros(25, dtype=tf.int32))

    class TrainingProgressCallback(tf.keras.callbacks.Callback):
        def __init__(self):
            super().__init__()
            self._epoch_start = None
            self._train_start = None
        def on_train_begin(self, logs=None):
            self._train_start = time.time()
        def on_epoch_begin(self, epoch, logs=None):
            self._epoch_start = time.time()
        def on_epoch_end(self, epoch, logs=None):
            elapsed = time.time() - self._epoch_start
            total_elapsed = time.time() - self._train_start
            remaining = (EPOCHS - epoch - 1) * (total_elapsed / (epoch + 1))
            loss = logs.get('loss', 0)
            val_loss = logs.get('val_loss', 0)
            logger.info(
                f"Epoch {{epoch+1}}/{{EPOCHS}} - "
                f"{{elapsed:.1f}}s - "
                f"loss: {{loss:.2f}} - val_loss: {{val_loss:.2f}} - "
                f"ETA: {{remaining/60:.1f}}m"
            )

    callbacks = [
        TrainingProgressCallback(),
        MetricsCallback(),
        WeightNormCallback(),
        WeightStatsCallback(),
        GradientStatsCallback(),
    ]

    # --- Train ---
    logger.info("=" * 60)
    logger.info("STARTING TRAINING")
    logger.info(f"  Epochs: {{EPOCHS}}")
    logger.info(f"  Batch size: {{BATCH_SIZE}}")
    logger.info(f"  Train batches: {{len(train_split['customer_id']) // BATCH_SIZE}}")
    logger.info(f"  Val batches: {{len(val_split['customer_id']) // BATCH_SIZE}}")
    logger.info("=" * 60)

    try:
        history = model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=EPOCHS,
            callbacks=callbacks,
        )
        logger.info("Training completed.")

        # Log final metrics from history
        if _metrics_collector:
            for metric_name, values in history.history.items():
                _metrics_collector.log_metric(f'final_{{metric_name}}', float(values[-1]))

        # --- Evaluate Recall on Test Set ---
        logger.info("=" * 60)
        logger.info("EVALUATING RECALL ON TEST SET")
        logger.info("=" * 60)

        # Pre-compute candidate embeddings (deduplicated by product_id)
        logger.info("Pre-computing candidate embeddings...")
        seen_products = set()
        unique_product_ids = []
        unique_embeddings = []

        for batch in test_ds:
            batch_embs = model.candidate_tower(batch)
            batch_pids = batch['product_id'].numpy()
            for i, pid in enumerate(batch_pids):
                pid = int(pid)
                if pid not in seen_products and pid != 0:
                    seen_products.add(pid)
                    unique_product_ids.append(pid)
                    unique_embeddings.append(batch_embs[i])

        # Also include products from training set not in test
        for batch in train_ds.take(5):
            batch_embs = model.candidate_tower(batch)
            batch_pids = batch['product_id'].numpy()
            for i, pid in enumerate(batch_pids):
                pid = int(pid)
                if pid not in seen_products and pid != 0:
                    seen_products.add(pid)
                    unique_product_ids.append(pid)
                    unique_embeddings.append(batch_embs[i])

        product_embeddings = tf.stack(unique_embeddings) if unique_embeddings else tf.zeros((0, OUTPUT_EMBEDDING_DIM))
        logger.info(f"Candidate pool: {{len(unique_product_ids)}} unique products")

        product_to_idx = {{pid: i for i, pid in enumerate(unique_product_ids)}}

        # Calculate recall
        total_recall = {{5: 0.0, 10: 0.0, 50: 0.0, 100: 0.0}}
        total_batches = 0

        for batch in test_ds:
            query_embs = model.query_tower(batch)
            similarities = tf.linalg.matmul(query_embs, product_embeddings, transpose_b=True)
            _, top_indices = tf.nn.top_k(similarities, k=min(TOP_K, len(unique_product_ids)))
            top_indices = top_indices.numpy()

            actual_pids = batch['product_id'].numpy()
            batch_size_actual = len(actual_pids)

            for k in [5, 10, 50, 100]:
                hits = 0
                for i in range(batch_size_actual):
                    pid = int(actual_pids[i])
                    if pid in product_to_idx:
                        if product_to_idx[pid] in top_indices[i, :k]:
                            hits += 1
                total_recall[k] += hits / batch_size_actual
            total_batches += 1

        if total_batches > 0:
            recall_results = {{
                'recall_at_5': total_recall[5] / total_batches,
                'recall_at_10': total_recall[10] / total_batches,
                'recall_at_50': total_recall[50] / total_batches,
                'recall_at_100': total_recall[100] / total_batches,
            }}
        else:
            recall_results = {{}}

        logger.info("=" * 60)
        logger.info("TEST SET RECALL RESULTS:")
        for k, v in recall_results.items():
            logger.info(f"  {{k}}: {{v:.4f}} ({{v*100:.2f}}%)")
        logger.info("=" * 60)

        # Log recall to metrics
        if _metrics_collector:
            for k, v in recall_results.items():
                _metrics_collector.log_metric(f'test_{{k}}', v)

            # Test loss evaluation
            test_loss_results = model.evaluate(test_ds, return_dict=True)
            for metric_name, value in test_loss_results.items():
                _metrics_collector.log_metric(f'test_{{metric_name}}', float(value))

        # --- Comparison with baseline ---
        logger.info("=" * 60)
        logger.info("COMPARISON WITH BASELINE (Experiment #162)")
        logger.info("=" * 60)
        baseline = {{'recall_at_5': 0.0523, 'recall_at_10': 0.0809, 'recall_at_50': 0.2196, 'recall_at_100': 0.3308}}
        for metric in ['recall_at_5', 'recall_at_10', 'recall_at_50', 'recall_at_100']:
            b = baseline.get(metric, 0)
            t = recall_results.get(metric, 0)
            diff = t - b
            pct = (diff / b * 100) if b > 0 else 0
            symbol = '+' if diff >= 0 else ''
            logger.info(f"  {{metric}}: baseline={{b:.4f}} -> taste={{t:.4f}} ({{symbol}}{{diff:.4f}}, {{symbol}}{{pct:.1f}}%)")
        logger.info("=" * 60)

    finally:
        if _metrics_collector:
            _metrics_collector.save_to_gcs()
            logger.info("Metrics saved to GCS")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    build_model_and_train()
'''


def submit_custom_job(runner_gcs_path: str, run_id: str, gpu_count: int):
    """Submit the Custom Job to Vertex AI."""
    from google.cloud import aiplatform

    aiplatform.init(project=PROJECT_ID, location=REGION)

    machine_type = 'n1-standard-16' if gpu_count >= 2 else 'n1-standard-8'

    job = aiplatform.CustomJob(
        display_name=f'taste-vector-{run_id}',
        worker_pool_specs=[{
            'machine_spec': {
                'machine_type': machine_type,
                'accelerator_type': 'NVIDIA_TESLA_T4',
                'accelerator_count': gpu_count,
            },
            'replica_count': 1,
            'container_spec': {
                'image_uri': TRAINER_IMAGE,
                'command': ['bash', '-c', f'gsutil cp {runner_gcs_path} /tmp/runner.py && python /tmp/runner.py'],
            },
        }],
        staging_bucket=f'gs://{JOB_STAGING_BUCKET}',
    )

    logger.info("Submitting Custom Job...")
    job.submit()
    return job


def wait_for_job_completion(job, timeout_minutes: int = 30) -> str:
    """Wait for job to complete and return final state."""
    from google.cloud import aiplatform

    logger.info(f"Waiting for job completion (timeout: {timeout_minutes} min)...")
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    job_name = job.resource_name

    while True:
        current_job = aiplatform.CustomJob.get(job_name)
        state = current_job.state.name
        elapsed = int(time.time() - start_time)

        if state in ['JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED']:
            logger.info(f"Job finished: {state} (after {elapsed}s)")
            return state

        if elapsed > timeout_seconds:
            logger.error(f"Job timed out after {timeout_minutes} minutes")
            return 'TIMEOUT'

        logger.info(f"Job state: {state} (elapsed: {elapsed}s)")
        time.sleep(30)


def fetch_metrics_from_gcs(gcs_output_path: str) -> dict:
    """Fetch training_metrics.json from GCS."""
    from google.cloud import storage
    import json

    path = gcs_output_path.replace('gs://', '')
    bucket_name = path.split('/')[0]
    blob_path = '/'.join(path.split('/')[1:]) + '/training_metrics.json'

    logger.info(f"Fetching metrics from gs://{bucket_name}/{blob_path}")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        logger.warning("Metrics file not found")
        return {}

    content = blob.download_as_string()
    metrics_data = json.loads(content)
    return metrics_data.get('final_metrics', {})


def main():
    parser = argparse.ArgumentParser(description='Taste Vector Validation Experiment')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs (default: 100)')
    parser.add_argument('--learning-rate', type=float, default=0.001, help='Learning rate (default: 0.001)')
    parser.add_argument('--batch-size', type=int, default=4096, help='Batch size (default: 4096)')
    parser.add_argument('--gpu-count', type=int, default=1, help='Number of GPUs (default: 1)')
    parser.add_argument('--dry-run', action='store_true', help='Generate and upload script without submitting')
    parser.add_argument('--wait', action='store_true', help='Wait for job completion and fetch metrics')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout in minutes for --wait (default: 60)')

    args = parser.parse_args()

    from google.cloud import storage

    run_id = f'taste-test-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    gcs_output_path = f'gs://{ARTIFACTS_BUCKET}/{run_id}'
    logger.info(f"Run ID: {run_id}")

    # Generate runner script
    runner_script = create_runner_script(
        gcs_output_path=gcs_output_path,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        gpu_count=args.gpu_count,
    )

    # Upload runner script to GCS
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)
    runner_blob_path = f'{run_id}/runner.py'
    bucket.blob(runner_blob_path).upload_from_string(runner_script)
    runner_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{runner_blob_path}'
    logger.info(f"Uploaded runner to {runner_gcs_path}")

    if args.dry_run:
        logger.info("DRY RUN — not submitting")
        logger.info(f"Inspect script: gsutil cat {runner_gcs_path}")
        return

    # Submit job
    job = submit_custom_job(runner_gcs_path, run_id, args.gpu_count)

    logger.info(f"""
================================================================================
TASTE VECTOR EXPERIMENT SUBMITTED
================================================================================
Run ID: {run_id}
Job: {job.resource_name}
Epochs: {args.epochs}
Learning Rate: {args.learning_rate}
Batch Size: {args.batch_size}
GPU: T4 x {args.gpu_count}

Baseline (Experiment #162):
  Recall@5:   0.0523
  Recall@10:  0.0809
  Recall@50:  0.2196
  Recall@100: 0.3308

Monitor:
  gcloud ai custom-jobs describe {job.resource_name.split('/')[-1]} --region={REGION}

Logs:
  gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="{job.resource_name.split('/')[-1]}"' \\
      --project={PROJECT_ID} --limit=100 --format='value(textPayload)'

Metrics (after completion):
  gsutil cat {gcs_output_path}/training_metrics.json | python -m json.tool | head -50
================================================================================
""")

    if args.wait:
        job_state = wait_for_job_completion(job, timeout_minutes=args.timeout)

        if job_state == 'JOB_STATE_SUCCEEDED':
            metrics = fetch_metrics_from_gcs(gcs_output_path)
            baseline = {
                'test_recall_at_5': 0.0523,
                'test_recall_at_10': 0.0809,
                'test_recall_at_50': 0.2196,
                'test_recall_at_100': 0.3308,
            }

            logger.info(f"""
================================================================================
EXPERIMENT COMPLETED — RESULTS
================================================================================
Taste Vector Results:
  Recall@5:   {metrics.get('test_recall_at_5', 'N/A')}
  Recall@10:  {metrics.get('test_recall_at_10', 'N/A')}
  Recall@50:  {metrics.get('test_recall_at_50', 'N/A')}
  Recall@100: {metrics.get('test_recall_at_100', 'N/A')}
  Loss:       {metrics.get('test_loss', metrics.get('final_loss', 'N/A'))}

Baseline (Experiment #162):
  Recall@5:   0.0523
  Recall@10:  0.0809
  Recall@50:  0.2196
  Recall@100: 0.3308

Full metrics:
  gsutil cat {gcs_output_path}/training_metrics.json | python -m json.tool
================================================================================
""")
        else:
            logger.error(f"Job failed: {job_state}")
            logger.error(f"Check logs: gcloud logging read 'resource.type=\"ml_job\" AND resource.labels.job_id=\"{job.resource_name.split('/')[-1]}\"' --project={PROJECT_ID} --limit=50 --format='value(textPayload)'")


if __name__ == '__main__':
    main()
