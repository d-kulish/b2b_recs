# TFX Trainer Image with TensorFlow Recommenders
#
# Minimal extension of the TFX base image to add tensorflow-recommenders.
# Location: europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer

FROM gcr.io/tfx-oss-public/tfx:1.15.0

# Add TensorFlow Recommenders
RUN pip install --no-cache-dir tensorflow-recommenders>=0.7.3

# Verify installation
RUN python -c "import tensorflow_recommenders as tfrs; print(f'TFRS: {tfrs.__version__}')"
