#!/usr/bin/env python3
"""
Test Model Improvements via Custom Jobs

Tests specific retrieval model improvements by patching QT-172's trainer_module.py
and submitting as Vertex AI Custom Jobs. Reuses QT-172's Transform/Schema artifacts
to skip the ~1 hour data processing step.

Experiment matrix:
  Rounds 1-4 (completed): L2-norm, temperature, early stopping, tower sweeps
  Round 5 (current — tuning on F2 [64, 32] optimal baseline):
    I1: F2 + Dropout(0.1)
    I2: F2 + Dropout(0.2)
    J:  F2 + batch_size=2048
    K:  F2 + remove_accidental_hits=True

Baseline (QT-172): R@5=17.0%, R@10=24.5%, R@50=42.2%, R@100=51.6%
Best (F2 [64, 32]): R@5=35.6%, R@10=44.3%, R@50=60.8%, R@100=66.8%

Usage:
    python scripts/test_model_improvements.py --experiment I1,I2,J,K --epochs 100
    python scripts/test_model_improvements.py --experiment I1 --dry-run
    python scripts/test_model_improvements.py --experiment J --epochs 100
"""

import argparse
import logging
import re
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────────

PROJECT_ID = 'b2b-recs'
REGION = 'europe-central2'
STAGING_BUCKET = 'b2b-recs-pipeline-staging'
JOB_STAGING_BUCKET = 'b2b-recs-pipeline-staging'  # Same region as data (europe-central2)
ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
TRAINER_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu:latest'

GPU_REGION = 'europe-west4'  # For --gpu mode
GPU_STAGING_BUCKET = 'b2b-recs-gpu-staging'

SOURCE_EXP = 'qt-172-20260227-153721'
SOURCE_TRAINER = f'gs://{ARTIFACTS_BUCKET}/{SOURCE_EXP}/trainer_module.py'


# ─── Patch Functions ────────────────────────────────────────────────────────────

def patch_l2_normalize_temperature(code: str, temperature: float = 0.05) -> str:
    """
    Patch A: L2-normalize both tower outputs and add temperature scaling.

    - In compute_loss(): add tf.math.l2_normalize on both embeddings
    - Replace self.task = tfrs.tasks.Retrieval() with Retrieval(temperature=temp)
    """
    # 1. Add L2 normalization in compute_loss
    old_compute = (
        "        query_embeddings = self.query_tower(features)\n"
        "        candidate_embeddings = self.candidate_tower(features)\n"
        "        return self.task(query_embeddings, candidate_embeddings)"
    )
    new_compute = (
        "        query_embeddings = self.query_tower(features)\n"
        "        candidate_embeddings = self.candidate_tower(features)\n"
        "        query_embeddings = tf.math.l2_normalize(query_embeddings, axis=-1)\n"
        "        candidate_embeddings = tf.math.l2_normalize(candidate_embeddings, axis=-1)\n"
        "        return self.task(query_embeddings, candidate_embeddings)"
    )
    if old_compute not in code:
        raise ValueError("Could not find compute_loss pattern to patch for L2 normalization")
    code = code.replace(old_compute, new_compute)

    # 2. Add temperature to Retrieval task
    code = _set_retrieval_task(code, temperature=temperature)

    return code


def patch_early_stopping(code: str, patience: int = 10, monitor: str = 'val_loss') -> str:
    """
    Patch B: Add EarlyStopping callback before model.fit().

    Inserts EarlyStopping callback after the existing callbacks list.
    """
    # Find the callbacks list and the model.fit call
    # Insert EarlyStopping right before `model.fit(`
    early_stop_code = (
        f"\n        # Early stopping to prevent overfitting\n"
        f"        callbacks.append(tf.keras.callbacks.EarlyStopping(\n"
        f"            monitor='{monitor}', patience={patience}, restore_best_weights=True\n"
        f"        ))\n"
    )

    # Insert before the "# Train" comment that precedes model.fit
    marker = "        # Train\n        logging.info(f\"Starting training"
    if marker not in code:
        # Try alternate marker
        marker = "        # Train\n"
        if marker not in code:
            raise ValueError("Could not find 'Train' marker to insert EarlyStopping")

    code = code.replace(marker, early_stop_code + "\n" + marker, 1)
    return code


def patch_label_smoothing(code: str, smoothing: float = 0.1, temperature: float = None) -> str:
    """
    Patch D: Replace Retrieval task with label-smoothed loss.

    Uses CategoricalCrossentropy with label_smoothing.
    """
    code = _set_retrieval_task(code, temperature=temperature, label_smoothing=smoothing)
    return code


def patch_hard_negatives(code: str, num: int = 10, temperature: float = None) -> str:
    """
    Patch E: Add num_hard_negatives to Retrieval task.
    """
    code = _set_retrieval_task(code, temperature=temperature, num_hard_negatives=num)
    return code


def patch_minimal_towers(code: str) -> str:
    """
    Patch F3: Replace [256, 128, 64, 32] towers with [32].

    Single Dense(32) projection layer per tower.
    """
    old_query = (
        "        query_layers.append(tf.keras.layers.Dense(256, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        query_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        query_layers.append(tf.keras.layers.Dense(64, activation='relu'))\n"
        "        query_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    new_query = (
        "        query_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    if old_query not in code:
        raise ValueError("Could not find query tower Dense(256)+Dense(128)+Dense(64)+Dense(32) pattern")
    code = code.replace(old_query, new_query)

    old_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(256, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(64, activation='relu'))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    new_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    if old_candidate not in code:
        raise ValueError("Could not find candidate tower Dense(256)+Dense(128)+Dense(64)+Dense(32) pattern")
    code = code.replace(old_candidate, new_candidate)

    code = code.replace(
        "# Buyer tower: Dense(256) → Dense(128) → Dense(64) → Dense(32)",
        "# Buyer tower: Dense(32)"
    )
    code = code.replace(
        "# Product tower: Dense(256) → Dense(128) → Dense(64) → Dense(32)",
        "# Product tower: Dense(32)"
    )

    return code


def patch_tiny_towers(code: str) -> str:
    """
    Patch F2: Replace [256, 128, 64, 32] towers with [64, 32].

    Removes Dense(256) and Dense(128) layers from both towers.
    """
    # Replace Dense(256)+Dense(128)+Dense(64) with just Dense(64) in query tower
    old_query = (
        "        query_layers.append(tf.keras.layers.Dense(256, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        query_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        query_layers.append(tf.keras.layers.Dense(64, activation='relu'))"
    )
    new_query = (
        "        query_layers.append(tf.keras.layers.Dense(64, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))"
    )
    if old_query not in code:
        raise ValueError("Could not find query tower Dense(256)+Dense(128)+Dense(64) pattern")
    code = code.replace(old_query, new_query)

    # Same for candidate tower
    old_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(256, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(64, activation='relu'))"
    )
    new_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(64, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))"
    )
    if old_candidate not in code:
        raise ValueError("Could not find candidate tower Dense(256)+Dense(128)+Dense(64) pattern")
    code = code.replace(old_candidate, new_candidate)

    # Update comment headers
    code = code.replace(
        "# Buyer tower: Dense(256) → Dense(128) → Dense(64) → Dense(32)",
        "# Buyer tower: Dense(64) → Dense(32)"
    )
    code = code.replace(
        "# Product tower: Dense(256) → Dense(128) → Dense(64) → Dense(32)",
        "# Product tower: Dense(64) → Dense(32)"
    )

    return code


def patch_smaller_towers(code: str) -> str:
    """
    Patch F: Replace [256, 128, 64, 32] towers with [128, 64, 32].

    Removes the Dense(256) layer from both query and candidate towers.
    """
    # Remove Dense(256) from query tower
    old_query = (
        "        query_layers.append(tf.keras.layers.Dense(256, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        query_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))"
    )
    new_query = (
        "        query_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))"
    )
    if old_query not in code:
        raise ValueError("Could not find query tower Dense(256)+Dense(128) pattern")
    code = code.replace(old_query, new_query)

    # Remove Dense(256) from candidate tower
    old_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(256, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))"
    )
    new_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(128, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))"
    )
    if old_candidate not in code:
        raise ValueError("Could not find candidate tower Dense(256)+Dense(128) pattern")
    code = code.replace(old_candidate, new_candidate)

    # Update the comment header
    code = code.replace(
        "# Buyer tower: Dense(256) → Dense(128) → Dense(64) → Dense(32)",
        "# Buyer tower: Dense(128) → Dense(64) → Dense(32)"
    )
    code = code.replace(
        "# Product tower: Dense(256) → Dense(128) → Dense(64) → Dense(32)",
        "# Product tower: Dense(128) → Dense(64) → Dense(32)"
    )

    return code


def patch_smaller_embeddings(code: str) -> str:
    """
    Patch G: Reduce embedding dimensions.

    - customer_id: 64 → 32
    - shared_product_embedding: 32 → 16
    - OUTPUT_EMBEDDING_DIM: 32 → 16
    - Last Dense layer in each tower: 32 → 16
    """
    # customer_id embedding: 64 → 32
    old_cust = "self.customer_id_embedding = tf.keras.layers.Embedding(customer_id_vocab_size + NUM_OOV_BUCKETS, 64)"
    new_cust = "self.customer_id_embedding = tf.keras.layers.Embedding(customer_id_vocab_size + NUM_OOV_BUCKETS, 32)"
    if old_cust not in code:
        raise ValueError("Could not find customer_id_embedding with dim=64")
    code = code.replace(old_cust, new_cust)

    # shared_product_embedding: 32 → 16
    old_prod = re.search(
        r"self\.shared_product_embedding = tf\.keras\.layers\.Embedding\(\s*"
        r"product_id_vocab_size \+ NUM_OOV_BUCKETS \+ 1, 32,",
        code
    )
    if not old_prod:
        raise ValueError("Could not find shared_product_embedding with dim=32")
    code = code.replace(old_prod.group(), old_prod.group().replace(", 32,", ", 16,"))

    # OUTPUT_EMBEDDING_DIM: 32 → 16
    code = code.replace("OUTPUT_EMBEDDING_DIM = 32", "OUTPUT_EMBEDDING_DIM = 16")

    # Last Dense layer in each tower: Dense(32) → Dense(16)
    code = code.replace(
        "query_layers.append(tf.keras.layers.Dense(32, activation='relu'))",
        "query_layers.append(tf.keras.layers.Dense(16, activation='relu'))"
    )
    code = code.replace(
        "candidate_layers.append(tf.keras.layers.Dense(32, activation='relu'))",
        "candidate_layers.append(tf.keras.layers.Dense(16, activation='relu'))"
    )

    return code


def patch_dropout(code: str, rate: float = 0.2) -> str:
    """
    Insert Dropout between Dense(64) and Dense(32) in both towers.

    Must be applied AFTER patch_tiny_towers (F2) which produces the [64, 32] layout.
    """
    # Query tower: insert Dropout after Dense(64)
    old_query = (
        "        query_layers.append(tf.keras.layers.Dense(64, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        query_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    new_query = (
        "        query_layers.append(tf.keras.layers.Dense(64, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        f"        query_layers.append(tf.keras.layers.Dropout({rate}))\n"
        "        query_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    if old_query not in code:
        raise ValueError("Could not find query tower Dense(64)+Dense(32) pattern (apply after F2 patch)")
    code = code.replace(old_query, new_query)

    # Candidate tower: insert Dropout after Dense(64)
    old_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(64, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    new_candidate = (
        "        candidate_layers.append(tf.keras.layers.Dense(64, activation='relu', "
        "kernel_regularizer=tf.keras.regularizers.l2(0.02)))\n"
        f"        candidate_layers.append(tf.keras.layers.Dropout({rate}))\n"
        "        candidate_layers.append(tf.keras.layers.Dense(32, activation='relu'))"
    )
    if old_candidate not in code:
        raise ValueError("Could not find candidate tower Dense(64)+Dense(32) pattern (apply after F2 patch)")
    code = code.replace(old_candidate, new_candidate)

    return code


def patch_remove_accidental_hits(code: str) -> str:
    """
    Patch K: Enable remove_accidental_hits and pass candidate_ids.

    1. Set Retrieval(remove_accidental_hits=True)
    2. Pass candidate_ids=features['product_id'] in compute_loss
    """
    # 1. Configure Retrieval task
    code = _set_retrieval_task(code, remove_accidental_hits=True)

    # 2. Pass candidate_ids in the task call
    old_call = "        return self.task(query_embeddings, candidate_embeddings)"
    new_call = "        return self.task(query_embeddings, candidate_embeddings, candidate_ids=tf.squeeze(features['product_id']))"
    if old_call not in code:
        raise ValueError("Could not find self.task(query_embeddings, candidate_embeddings) to add candidate_ids")
    code = code.replace(old_call, new_call)

    return code


def _set_retrieval_task(code: str, temperature: float = None, label_smoothing: float = None,
                        num_hard_negatives: int = None, remove_accidental_hits: bool = False) -> str:
    """
    Replace `self.task = tfrs.tasks.Retrieval(...)` with a configured version.

    Handles any existing Retrieval() call (with or without args).
    """
    # Match the existing Retrieval() line (possibly multi-line)
    pattern = r'self\.task = tfrs\.tasks\.Retrieval\([^)]*\)'
    if not re.search(pattern, code):
        raise ValueError("Could not find self.task = tfrs.tasks.Retrieval(...) to patch")

    # Build kwargs
    kwargs = []
    if temperature is not None:
        kwargs.append(f"temperature={temperature}")
    if num_hard_negatives is not None:
        kwargs.append(f"num_hard_negatives={num_hard_negatives}")
    if remove_accidental_hits:
        kwargs.append("remove_accidental_hits=True")

    if label_smoothing is not None:
        # Use custom loss with label smoothing
        loss_str = (
            "loss=tf.keras.losses.CategoricalCrossentropy(\n"
            f"                from_logits=True, label_smoothing={label_smoothing},\n"
            "                reduction=tf.keras.losses.Reduction.SUM\n"
            "            )"
        )
        kwargs.insert(0, loss_str)

    if kwargs:
        kwargs_str = ",\n            ".join(kwargs)
        replacement = f"self.task = tfrs.tasks.Retrieval(\n            {kwargs_str}\n        )"
    else:
        replacement = "self.task = tfrs.tasks.Retrieval()"

    code = re.sub(pattern, replacement, code)
    return code


# ─── Experiment Configs ─────────────────────────────────────────────────────────

EXPERIMENTS = {
    # ─── Round 1 (completed) ─────────────────────────────────────────────────
    'A': {
        'name': 'l2-norm-temp',
        'description': 'L2-normalize embeddings + temperature=0.05',
        'patches': [
            ('L2 normalize + temperature', lambda code: patch_l2_normalize_temperature(code, temperature=0.05)),
        ],
    },
    'B': {
        'name': 'early-stopping',
        'description': 'EarlyStopping(patience=10, restore_best_weights=True) on val_loss',
        'patches': [
            ('Early stopping', lambda code: patch_early_stopping(code, patience=10)),
        ],
    },
    'C': {
        'name': 'l2-norm-earlystop',
        'description': 'L2-normalize + temperature=0.05 + early stopping',
        'patches': [
            ('L2 normalize + temperature', lambda code: patch_l2_normalize_temperature(code, temperature=0.05)),
            ('Early stopping', lambda code: patch_early_stopping(code, patience=10)),
        ],
    },
    'D': {
        'name': 'l2-norm-earlystop-labelsmooth',
        'description': 'L2-normalize + early stopping + label_smoothing=0.1',
        'patches': [
            ('L2 normalize + temperature + label smoothing',
             lambda code: patch_l2_normalize_temperature(code, temperature=0.05)),
            ('Label smoothing', lambda code: patch_label_smoothing(code, smoothing=0.1, temperature=0.05)),
            ('Early stopping', lambda code: patch_early_stopping(code, patience=10)),
        ],
    },
    'E': {
        'name': 'l2-norm-earlystop-hardneg',
        'description': 'L2-normalize + early stopping + num_hard_negatives=10',
        'patches': [
            ('L2 normalize + temperature',
             lambda code: patch_l2_normalize_temperature(code, temperature=0.05)),
            ('Hard negatives', lambda code: patch_hard_negatives(code, num=10, temperature=0.05)),
            ('Early stopping', lambda code: patch_early_stopping(code, patience=10)),
        ],
    },
    # ─── Round 2: temperature tuning ─────────────────────────────────────────
    'A2': {
        'name': 'l2-norm-temp02',
        'description': 'L2-normalize + temperature=0.2 (warmer than A)',
        'patches': [
            ('L2 normalize + temperature=0.2', lambda code: patch_l2_normalize_temperature(code, temperature=0.2)),
        ],
    },
    'A3': {
        'name': 'l2-norm-temp05',
        'description': 'L2-normalize + temperature=0.5 (warmer)',
        'patches': [
            ('L2 normalize + temperature=0.5', lambda code: patch_l2_normalize_temperature(code, temperature=0.5)),
        ],
    },
    'A4': {
        'name': 'l2-norm-temp10',
        'description': 'L2-normalize + temperature=1.0 (no sharpening, just normalize)',
        'patches': [
            ('L2 normalize + temperature=1.0', lambda code: patch_l2_normalize_temperature(code, temperature=1.0)),
        ],
    },
    # ─── Round 2: early stopping on train loss ───────────────────────────────
    'B2': {
        'name': 'earlystop-trainloss',
        'description': 'EarlyStopping on loss (train), patience=15',
        'patches': [
            ('Early stopping on train loss',
             lambda code: patch_early_stopping(code, patience=15, monitor='loss')),
        ],
    },
    # ─── Round 3: smaller architecture ───────────────────────────────────────
    'F': {
        'name': 'smaller-towers',
        'description': 'Tower layers [128, 64, 32] instead of [256, 128, 64, 32]',
        'patches': [
            ('Smaller towers', lambda code: patch_smaller_towers(code)),
        ],
    },
    'G': {
        'name': 'smaller-embeddings',
        'description': 'Lower embedding dims: customer 64→32, product 32→16, output 32→16',
        'patches': [
            ('Smaller embeddings', lambda code: patch_smaller_embeddings(code)),
        ],
    },
    'H': {
        'name': 'smaller-all',
        'description': 'Smaller towers [128, 64, 32] + lower embedding dims (32/16/16)',
        'patches': [
            ('Smaller towers', lambda code: patch_smaller_towers(code)),
            ('Smaller embeddings', lambda code: patch_smaller_embeddings(code)),
        ],
    },
    # ─── Round 4: tower size sweep ───────────────────────────────────────────
    'F2': {
        'name': 'tiny-towers',
        'description': 'Tower layers [64, 32] — 2 layers only',
        'patches': [
            ('Tiny towers', lambda code: patch_tiny_towers(code)),
        ],
    },
    'F3': {
        'name': 'minimal-towers',
        'description': 'Tower layers [32] — single projection layer',
        'patches': [
            ('Minimal towers', lambda code: patch_minimal_towers(code)),
        ],
    },
    # ─── Round 5: tuning on F2 [64, 32] baseline ────────────────────────────
    'I1': {
        'name': 'f2-dropout01',
        'description': 'F2 [64, 32] + Dropout(0.1) between layers',
        'patches': [
            ('Tiny towers', lambda code: patch_tiny_towers(code)),
            ('Dropout 0.1', lambda code: patch_dropout(code, rate=0.1)),
        ],
    },
    'I2': {
        'name': 'f2-dropout02',
        'description': 'F2 [64, 32] + Dropout(0.2) between layers',
        'patches': [
            ('Tiny towers', lambda code: patch_tiny_towers(code)),
            ('Dropout 0.2', lambda code: patch_dropout(code, rate=0.2)),
        ],
    },
    'J': {
        'name': 'f2-batch2048',
        'description': 'F2 [64, 32] + batch_size=2048 (fewer in-batch negatives)',
        'patches': [
            ('Tiny towers', lambda code: patch_tiny_towers(code)),
        ],
        'batch_size': 2048,
    },
    'K': {
        'name': 'f2-accidental-hits',
        'description': 'F2 [64, 32] + remove_accidental_hits=True',
        'patches': [
            ('Tiny towers', lambda code: patch_tiny_towers(code)),
            ('Remove accidental hits', lambda code: patch_remove_accidental_hits(code)),
        ],
    },
}


# ─── Artifact Discovery ─────────────────────────────────────────────────────────

def find_artifacts(source_exp: str) -> dict:
    """Find Transform artifacts from a completed experiment."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(STAGING_BUCKET)

    prefix = f'pipeline_root/{source_exp}/'
    blobs = list(bucket.list_blobs(prefix=prefix))
    paths = [b.name for b in blobs]

    transform_base = None
    schema_path = None

    for p in paths:
        if 'Transform_' in p and '/transform_graph/' in p and not transform_base:
            parts = p.split('/')
            for i, part in enumerate(parts):
                if part.startswith('Transform_'):
                    transform_base = '/'.join(parts[:i + 1])
                    break
        if 'SchemaGen_' in p and 'schema.pbtxt' in p:
            schema_path = p

    if not transform_base or not schema_path:
        raise ValueError(f"Could not find artifacts in {prefix}")

    return {
        'transform_graph': f'gs://{STAGING_BUCKET}/{transform_base}/transform_graph',
        'transformed_examples_train': f'gs://{STAGING_BUCKET}/{transform_base}/transformed_examples/Split-train',
        'transformed_examples_eval': f'gs://{STAGING_BUCKET}/{transform_base}/transformed_examples/Split-eval',
        'schema': f'gs://{STAGING_BUCKET}/{schema_path}',
    }


# ─── Runner Script (runs inside the Custom Job) ────────────────────────────────

def create_runner_script(artifacts: dict, trainer_gcs_path: str, output_path: str,
                         gcs_output_path: str, epochs: int, learning_rate: float,
                         batch_size: int = 4096, gpu: bool = False) -> str:
    """Create the script that runs inside the Custom Job container."""
    return f'''#!/usr/bin/env python3
"""Runner script for model improvement experiment."""
import os
import sys
import logging
import tempfile
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("MODEL IMPROVEMENT EXPERIMENT")
    logger.info("="*60)

    work_dir = tempfile.mkdtemp(prefix='improvement_test_')
    logger.info(f"Work dir: {{work_dir}}")

    # Download trainer module
    trainer_local = os.path.join(work_dir, 'trainer_module.py')
    logger.info(f"Downloading trainer from {trainer_gcs_path}")
    subprocess.run(['gsutil', 'cp', '{trainer_gcs_path}', trainer_local], check=True)

    # Download transform graph
    transform_local = os.path.join(work_dir, 'transform_graph')
    os.makedirs(transform_local, exist_ok=True)
    logger.info(f"Downloading transform graph from {artifacts['transform_graph']}")
    subprocess.run(['gsutil', '-m', 'rsync', '-r', '{artifacts['transform_graph']}', transform_local], check=True)

    # Download schema
    schema_local = os.path.join(work_dir, 'schema.pbtxt')
    logger.info(f"Downloading schema from {artifacts['schema']}")
    subprocess.run(['gsutil', 'cp', '{artifacts['schema']}', schema_local], check=True)

    # Import trainer module
    logger.info("Importing trainer module...")
    sys.path.insert(0, work_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location("trainer_module", trainer_local)
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)

    # Create FnArgs
    class FnArgs:
        pass

    fn_args = FnArgs()
    fn_args.train_files = ['{artifacts['transformed_examples_train']}/*']
    fn_args.eval_files = ['{artifacts['transformed_examples_eval']}/*']
    fn_args.transform_output = transform_local
    fn_args.schema_file = schema_local
    fn_args.serving_model_dir = os.path.join(work_dir, 'serving_model')
    fn_args.model_run_dir = os.path.join(work_dir, 'model_run')
    fn_args.train_steps = None
    fn_args.eval_steps = None
    fn_args.custom_config = {{
        'epochs': {epochs},
        'batch_size': {batch_size},
        'learning_rate': {learning_rate},
        'gcs_output_path': '{gcs_output_path}',
        'gpu_enabled': {gpu},
        'gpu_count': {1 if gpu else 0},
    }}

    # Create data accessor
    from tfx_bsl.public import tfxio

    class DataAccessor:
        def tf_dataset_factory(self, file_pattern, options, schema):
            import tensorflow as tf

            if isinstance(file_pattern, list):
                file_pattern = file_pattern[0]

            files = tf.io.gfile.glob(file_pattern)
            logger.info(f"Found {{len(files)}} files matching {{file_pattern}}")

            dataset = tf.data.TFRecordDataset(files, compression_type='GZIP')

            import tensorflow_transform as tft
            tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)
            feature_spec = tf_transform_output.transformed_feature_spec()

            def parse_fn(example):
                parsed = tf.io.parse_single_example(example, feature_spec)
                expanded = {{}}
                for key, value in parsed.items():
                    if len(value.shape) == 0:
                        expanded[key] = tf.expand_dims(value, 0)
                    else:
                        expanded[key] = value
                return expanded

            dataset = dataset.map(parse_fn, num_parallel_calls=tf.data.AUTOTUNE)
            dataset = dataset.batch(options.batch_size)

            label_key = getattr(options, 'label_key', None)
            if label_key:
                logger.info(f"Ranking model: extracting label_key='{{label_key}}' from features")
                def extract_label(features):
                    label = features.pop(label_key)
                    return features, label
                dataset = dataset.map(extract_label, num_parallel_calls=tf.data.AUTOTUNE)

            dataset = dataset.prefetch(tf.data.AUTOTUNE)
            return dataset

    fn_args.data_accessor = DataAccessor()

    os.makedirs(fn_args.serving_model_dir, exist_ok=True)
    os.makedirs(fn_args.model_run_dir, exist_ok=True)

    logger.info("="*60)
    logger.info("STARTING TRAINING")
    logger.info("="*60)

    trainer.run_fn(fn_args)

    logger.info("="*60)
    logger.info("TRAINING COMPLETED SUCCESSFULLY")
    logger.info("="*60)

    logger.info(f"Uploading model to {output_path}")
    subprocess.run(['gsutil', '-m', 'cp', '-r', fn_args.serving_model_dir, '{output_path}'], check=True)

if __name__ == '__main__':
    main()
'''


# ─── Main ───────────────────────────────────────────────────────────────────────

def run_experiment(experiment_key: str, code: str, epochs: int, learning_rate: float,
                   batch_size: int = 4096, dry_run: bool = False, gpu: bool = False) -> dict:
    """Apply patches, upload, and submit a single experiment."""
    from google.cloud import storage

    exp = EXPERIMENTS[experiment_key]
    run_id = f'improvement-{experiment_key}-{exp["name"]}-{datetime.now().strftime("%Y%m%d-%H%M%S")}'

    logger.info(f"\n{'='*70}")
    logger.info(f"EXPERIMENT {experiment_key}: {exp['description']}")
    logger.info(f"Run ID: {run_id}")
    logger.info(f"{'='*70}")

    # Apply patches sequentially
    patched_code = code
    for patch_name, patch_fn in exp['patches']:
        logger.info(f"  Applying patch: {patch_name}")
        patched_code = patch_fn(patched_code)

    # Per-experiment batch_size override
    effective_batch_size = exp.get('batch_size', batch_size)

    # Override epochs, learning rate, and batch size
    patched_code = re.sub(r'EPOCHS = \d+', f'EPOCHS = {epochs}', patched_code)
    patched_code = re.sub(r'LEARNING_RATE = [\d.eE+-]+', f'LEARNING_RATE = {learning_rate}', patched_code)
    patched_code = re.sub(r'BATCH_SIZE = \d+', f'BATCH_SIZE = {effective_batch_size}', patched_code)

    # Validate syntax
    try:
        compile(patched_code, f'<experiment-{experiment_key}>', 'exec')
        logger.info("  Patched code is syntactically valid")
    except SyntaxError as e:
        logger.error(f"  SYNTAX ERROR in patched code: {e}")
        with open(f'/tmp/invalid_experiment_{experiment_key}.py', 'w') as f:
            f.write(patched_code)
        logger.error(f"  Saved invalid code to /tmp/invalid_experiment_{experiment_key}.py")
        return {'experiment': experiment_key, 'status': 'syntax_error', 'error': str(e)}

    # Upload patched trainer
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)

    trainer_blob_path = f'{run_id}/trainer_module.py'
    bucket.blob(trainer_blob_path).upload_from_string(patched_code)
    trainer_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{trainer_blob_path}'
    logger.info(f"  Uploaded patched trainer to {trainer_gcs_path}")

    # Find artifacts
    artifacts = find_artifacts(SOURCE_EXP)

    # Create runner script
    gcs_output_path = f'gs://{ARTIFACTS_BUCKET}/{run_id}'
    output_path = f'{gcs_output_path}/model'
    runner_script = create_runner_script(
        artifacts, trainer_gcs_path, output_path, gcs_output_path, epochs, learning_rate,
        batch_size=effective_batch_size, gpu=gpu
    )

    # Upload runner script
    runner_blob_path = f'{run_id}/runner.py'
    bucket.blob(runner_blob_path).upload_from_string(runner_script)
    runner_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{runner_blob_path}'
    logger.info(f"  Uploaded runner to {runner_gcs_path}")

    if dry_run:
        logger.info(f"  DRY RUN — not submitting job")
        logger.info(f"  Inspect patched trainer: gsutil cat {trainer_gcs_path}")
        return {'experiment': experiment_key, 'status': 'dry_run', 'run_id': run_id,
                'trainer_path': trainer_gcs_path}

    # Submit CustomJob
    from google.cloud import aiplatform

    if gpu:
        region = GPU_REGION
        staging_bucket = GPU_STAGING_BUCKET
        machine_spec = {
            'machine_type': 'n1-standard-8',
            'accelerator_type': 'NVIDIA_TESLA_T4',
            'accelerator_count': 1,
        }
    else:
        region = REGION
        staging_bucket = JOB_STAGING_BUCKET
        machine_spec = {
            'machine_type': 'n1-standard-8',
        }

    aiplatform.init(project=PROJECT_ID, location=region)

    job = aiplatform.CustomJob(
        display_name=f'improvement-{experiment_key}-{exp["name"]}',
        worker_pool_specs=[{
            'machine_spec': machine_spec,
            'replica_count': 1,
            'container_spec': {
                'image_uri': TRAINER_IMAGE,
                'command': ['bash', '-c',
                            f'gsutil cp {runner_gcs_path} /tmp/runner.py && python /tmp/runner.py'],
            },
        }],
        staging_bucket=f'gs://{staging_bucket}',
    )

    logger.info("  Submitting CustomJob...")
    job.submit()

    job_id = job.resource_name.split('/')[-1]

    logger.info(f"""
================================================================================
EXPERIMENT {experiment_key} SUBMITTED: {exp['description']}
================================================================================
Run ID: {run_id}
Job:    {job.resource_name}
Epochs: {epochs}, LR: {learning_rate}, Batch: {effective_batch_size}
Mode:   {'GPU (T4)' if gpu else 'CPU'} in {region}

Monitor:
  gcloud ai custom-jobs describe {job_id} --region={region}

Logs:
  https://console.cloud.google.com/logs/query?project={PROJECT_ID}

Patched trainer:
  gsutil cat {trainer_gcs_path}

Results (after completion):
  gsutil cat {gcs_output_path}/training_metrics.json | python -m json.tool | head -50

Baseline (QT-172): R@5=17.0%, R@10=24.5%, R@50=42.2%, R@100=51.6%
================================================================================
""")

    return {
        'experiment': experiment_key,
        'status': 'submitted',
        'run_id': run_id,
        'job_name': job.resource_name,
        'job_id': job_id,
        'metrics_path': f'{gcs_output_path}/training_metrics.json',
    }


def main():
    parser = argparse.ArgumentParser(
        description='Test model improvements via patched Custom Jobs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Experiments (round 1):
  A   L2-normalize + temperature=0.05     (too aggressive — R@5 dropped to 8.6%)
  B   EarlyStopping on val_loss            (stopped at epoch 11 — val_loss wrong signal)
  C   A + B combined
  D   C + label_smoothing=0.1
  E   C + num_hard_negatives=10

Experiments (round 2 — tuning):
  A2  L2-normalize + temperature=0.2
  A3  L2-normalize + temperature=0.5
  A4  L2-normalize + temperature=1.0      (normalize only, no sharpening)
  B2  EarlyStopping on train loss, patience=15

Experiments (round 3 — smaller architecture):
  F   Towers [128, 64, 32] instead of [256, 128, 64, 32]
  G   Embedding dims: customer 64→32, product 32→16, output 32→16
  H   F + G combined

Experiments (round 4 — tower size sweep):
  F2  Towers [64, 32] — 2 layers              (BEST: R@5=35.6%, R@100=66.8%)
  F3  Towers [32] — single projection layer

Experiments (round 5 — tuning on F2 [64, 32] baseline):
  I1  F2 + Dropout(0.1) between Dense(64) and Dense(32)
  I2  F2 + Dropout(0.2) between Dense(64) and Dense(32)
  J   F2 + batch_size=2048 (fewer in-batch negatives)
  K   F2 + remove_accidental_hits=True

Examples:
  %(prog)s --experiment I1,I2,J,K --epochs 100
  %(prog)s --experiment J --epochs 100
  %(prog)s --experiment I1,I2,J,K --dry-run
        """
    )
    parser.add_argument('--experiment', required=True,
                        help='Experiment to run: A, B, C, D, E, or "all"')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs (default: 100)')
    parser.add_argument('--lr', type=float, default=0.001, help='Learning rate (default: 0.001)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Upload patched code but do not submit job')
    parser.add_argument('--batch-size', type=int, default=4096,
                        help='Batch size (default: 4096, experiment J overrides to 2048)')
    parser.add_argument('--gpu', action='store_true',
                        help='Use GPU (T4) in europe-west4 instead of CPU in europe-central2')
    parser.add_argument('--source-trainer', default=SOURCE_TRAINER,
                        help=f'GCS path to source trainer_module.py (default: {SOURCE_TRAINER})')
    args = parser.parse_args()

    # Determine which experiments to run
    if args.experiment.lower() == 'all':
        experiment_keys = list(EXPERIMENTS.keys())
    else:
        experiment_keys = [k.strip().upper() for k in args.experiment.split(',')]
        for k in experiment_keys:
            if k not in EXPERIMENTS:
                logger.error(f"Unknown experiment: {k}. Valid: {', '.join(EXPERIMENTS.keys())}")
                sys.exit(1)

    # Download source trainer
    logger.info(f"Downloading source trainer from {args.source_trainer}...")
    from google.cloud import storage
    import tempfile

    # Parse GCS path
    path = args.source_trainer.replace('gs://', '')
    bucket_name = path.split('/')[0]
    blob_path = '/'.join(path.split('/')[1:])

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    source_code = blob.download_as_text()
    logger.info(f"Downloaded source trainer ({len(source_code)} chars)")

    # Run experiments
    results = []
    for key in experiment_keys:
        result = run_experiment(key, source_code, args.epochs, args.lr,
                                batch_size=args.batch_size, dry_run=args.dry_run, gpu=args.gpu)
        results.append(result)

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info("SUMMARY")
    logger.info(f"{'='*70}")
    for r in results:
        status = r['status']
        exp_key = r['experiment']
        exp_desc = EXPERIMENTS[exp_key]['description']
        if status == 'submitted':
            logger.info(f"  {exp_key}: SUBMITTED — {exp_desc}")
            logger.info(f"     Job ID: {r['job_id']}")
            logger.info(f"     Metrics: gsutil cat {r['metrics_path']} | python -m json.tool")
        elif status == 'dry_run':
            logger.info(f"  {exp_key}: DRY RUN — {exp_desc}")
            logger.info(f"     Trainer: gsutil cat {r['trainer_path']}")
        else:
            logger.info(f"  {exp_key}: {status.upper()} — {exp_desc}")


if __name__ == '__main__':
    main()
