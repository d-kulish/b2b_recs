# TFX Trainer Image with TensorFlow Recommenders and ScaNN
#
# Extension of the TFX base image to add tensorflow-recommenders and ScaNN
# for fast approximate nearest neighbor search in retrieval models.
# Location: europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer

FROM gcr.io/tfx-oss-public/tfx:1.15.0

# Add TensorFlow Recommenders (compatible with TF 2.15)
RUN pip install --no-cache-dir tensorflow-recommenders>=0.7.3

# Add ScaNN for approximate nearest neighbor search (10-20x faster for large catalogs)
# ScaNN 1.3.0 was compiled against TensorFlow 2.15 (same as TFX 1.15.0 base image)
# Use --no-deps to prevent any dependency conflicts
RUN pip install --no-cache-dir --no-deps scann==1.3.0

# Verify installations
RUN python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
RUN python -c "import tensorflow as tf; print(f'TensorFlow: {tf.__version__}')"
RUN python -c "import tensorflow_recommenders as tfrs; print(f'TFRS: {tfrs.__version__}')"
RUN python -c "import scann; print('ScaNN: installed')"
RUN python -c "from tensorflow_recommenders.layers.factorized_top_k import ScaNN; print('ScaNN layer: available')"
