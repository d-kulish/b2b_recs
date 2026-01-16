#!/usr/bin/env python3
"""
GPU Validation Test Script for TFX Trainer GPU Container

This script validates that the GPU container works correctly in Vertex AI:
1. Detects available GPUs
2. Runs a simple TensorFlow computation on GPU
3. Tests MirroredStrategy for multi-GPU
4. Validates TFRS and ScaNN imports
5. Runs a small TFRS model training

Usage:
    python test_gpu.py

This script is designed to run inside the tfx-trainer-gpu container
on a Vertex AI Custom Job with GPU resources.
"""

import os
import sys
import time
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_tensorflow_gpu():
    """Test basic TensorFlow GPU functionality."""
    logger.info("=" * 60)
    logger.info("TEST 1: TensorFlow GPU Detection")
    logger.info("=" * 60)

    import tensorflow as tf

    logger.info(f"TensorFlow version: {tf.__version__}")
    logger.info(f"CUDA built: {tf.test.is_built_with_cuda()}")

    gpus = tf.config.list_physical_devices('GPU')
    logger.info(f"Available GPUs: {len(gpus)}")

    for i, gpu in enumerate(gpus):
        logger.info(f"  GPU {i}: {gpu}")

    if not gpus:
        logger.error("No GPUs detected! This container requires GPU resources.")
        return False

    # Test GPU computation
    logger.info("\nRunning GPU computation test...")
    with tf.device('/GPU:0'):
        a = tf.constant([[1.0, 2.0], [3.0, 4.0]])
        b = tf.constant([[1.0, 1.0], [0.0, 1.0]])
        c = tf.matmul(a, b)
        logger.info(f"GPU matmul result:\n{c.numpy()}")

    logger.info("TEST 1: PASSED")
    return True


def test_mirrored_strategy():
    """Test multi-GPU MirroredStrategy."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: MirroredStrategy (Multi-GPU)")
    logger.info("=" * 60)

    import tensorflow as tf

    strategy = tf.distribute.MirroredStrategy()
    logger.info(f"Number of devices: {strategy.num_replicas_in_sync}")

    # Test computation under strategy
    with strategy.scope():
        model = tf.keras.Sequential([
            tf.keras.layers.Dense(64, activation='relu', input_shape=(10,)),
            tf.keras.layers.Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')

    # Quick training test
    import numpy as np
    x = np.random.randn(1000, 10).astype(np.float32)
    y = np.random.randn(1000, 1).astype(np.float32)

    logger.info("Training simple model with MirroredStrategy...")
    history = model.fit(x, y, epochs=3, batch_size=128, verbose=0)
    logger.info(f"Final loss: {history.history['loss'][-1]:.4f}")

    logger.info("TEST 2: PASSED")
    return True


def test_tfrs_import():
    """Test TensorFlow Recommenders import."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: TensorFlow Recommenders")
    logger.info("=" * 60)

    import tensorflow_recommenders as tfrs

    logger.info(f"TFRS version: {tfrs.__version__}")

    # Test key imports
    from tensorflow_recommenders.tasks import Retrieval, Ranking
    logger.info("  Retrieval task: OK")
    logger.info("  Ranking task: OK")

    from tensorflow_recommenders.models import Model
    logger.info("  Model base class: OK")

    logger.info("TEST 3: PASSED")
    return True


def test_scann():
    """Test ScaNN import and basic functionality."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: ScaNN (Approximate Nearest Neighbors)")
    logger.info("=" * 60)

    import scann
    logger.info("ScaNN module: imported")

    from tensorflow_recommenders.layers.factorized_top_k import ScaNN as ScaNNLayer
    logger.info("TFRS ScaNN layer: imported")

    # Build a simple ScaNN index
    import numpy as np
    import tensorflow as tf

    # Create some candidate embeddings
    candidates = np.random.randn(1000, 32).astype(np.float32)
    candidates_dataset = tf.data.Dataset.from_tensor_slices(candidates)

    logger.info("Building ScaNN index with 1000 candidates...")
    scann_layer = ScaNNLayer(k=10)
    scann_layer.index_from_dataset(candidates_dataset.batch(100))

    # Query the index
    query = np.random.randn(1, 32).astype(np.float32)
    scores, indices = scann_layer(query)
    logger.info(f"Query result shape: scores={scores.shape}, indices={indices.shape}")
    logger.info(f"Top-10 indices: {indices.numpy()[0]}")

    logger.info("TEST 4: PASSED")
    return True


def test_tfrs_model_training():
    """Test a simple TFRS retrieval model training."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: TFRS Model Training")
    logger.info("=" * 60)

    import tensorflow as tf
    import tensorflow_recommenders as tfrs
    import numpy as np

    # Create synthetic data
    num_users = 100
    num_items = 500
    num_interactions = 2000

    user_ids = [f"user_{i}" for i in np.random.randint(0, num_users, num_interactions)]
    item_ids = [f"item_{i}" for i in np.random.randint(0, num_items, num_interactions)]

    interactions = tf.data.Dataset.from_tensor_slices({
        "user_id": user_ids,
        "item_id": item_ids
    }).batch(256)

    unique_user_ids = [f"user_{i}" for i in range(num_users)]
    unique_item_ids = [f"item_{i}" for i in range(num_items)]

    # Build model
    class SimpleRetrievalModel(tfrs.Model):
        def __init__(self):
            super().__init__()

            self.user_model = tf.keras.Sequential([
                tf.keras.layers.StringLookup(vocabulary=unique_user_ids, mask_token=None),
                tf.keras.layers.Embedding(num_users + 1, 32)
            ])

            self.item_model = tf.keras.Sequential([
                tf.keras.layers.StringLookup(vocabulary=unique_item_ids, mask_token=None),
                tf.keras.layers.Embedding(num_items + 1, 32)
            ])

            self.task = tfrs.tasks.Retrieval(
                metrics=tfrs.metrics.FactorizedTopK(
                    candidates=tf.data.Dataset.from_tensor_slices(unique_item_ids).batch(128).map(self.item_model)
                )
            )

        def compute_loss(self, features, training=False):
            user_embeddings = self.user_model(features["user_id"])
            item_embeddings = self.item_model(features["item_id"])
            return self.task(user_embeddings, item_embeddings)

    logger.info("Building TFRS retrieval model...")
    model = SimpleRetrievalModel()
    model.compile(optimizer=tf.keras.optimizers.Adagrad(learning_rate=0.1))

    logger.info("Training for 3 epochs...")
    start_time = time.time()
    history = model.fit(interactions, epochs=3, verbose=1)
    elapsed = time.time() - start_time

    logger.info(f"Training completed in {elapsed:.2f} seconds")
    logger.info(f"Final loss: {history.history['total_loss'][-1]:.4f}")

    logger.info("TEST 5: PASSED")
    return True


def test_tfx_components():
    """Test TFX component imports."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: TFX Components")
    logger.info("=" * 60)

    import tfx
    logger.info(f"TFX version: {tfx.__version__}")

    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    logger.info("  BigQueryExampleGen: OK")

    from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
    logger.info("  StatisticsGen: OK")
    logger.info("  SchemaGen: OK")
    logger.info("  Transform: OK")
    logger.info("  Trainer: OK")

    from tfx.components import Evaluator, Pusher
    logger.info("  Evaluator: OK")
    logger.info("  Pusher: OK")

    logger.info("TEST 6: PASSED")
    return True


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("TFX TRAINER GPU CONTAINER VALIDATION")
    logger.info("=" * 60)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("")

    tests = [
        ("TensorFlow GPU", test_tensorflow_gpu),
        ("MirroredStrategy", test_mirrored_strategy),
        ("TFRS Import", test_tfrs_import),
        ("ScaNN", test_scann),
        ("TFRS Model Training", test_tfrs_model_training),
        ("TFX Components", test_tfx_components),
    ]

    results = {}
    all_passed = True

    for name, test_fn in tests:
        try:
            passed = test_fn()
            results[name] = "PASSED" if passed else "FAILED"
            if not passed:
                all_passed = False
        except Exception as e:
            logger.error(f"TEST {name}: FAILED with exception: {e}")
            results[name] = f"FAILED: {str(e)}"
            all_passed = False

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    for name, result in results.items():
        status = "✅" if result == "PASSED" else "❌"
        logger.info(f"  {status} {name}: {result}")

    logger.info("")
    if all_passed:
        logger.info("ALL TESTS PASSED - GPU container is ready for training!")
        return 0
    else:
        logger.error("SOME TESTS FAILED - Review the output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
