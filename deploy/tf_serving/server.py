"""
Python-based model serving for TFRS models with ScaNN support.

This server loads TensorFlow SavedModels directly, bypassing TF Serving
to properly support ScaNN custom operations.

Compatible with TF Serving REST API format for drop-in replacement.
"""

import os
import json
import base64
import logging
from flask import Flask, request, jsonify

import tensorflow as tf

# Import scann to register custom ops
import scann

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global model reference
model = None
MODEL_NAME = os.environ.get('MODEL_NAME', 'recommender')


def load_model():
    """Load the SavedModel from the local path."""
    global model

    model_path = f"/models/{MODEL_NAME}/1"
    logger.info(f"Loading model from {model_path}")

    # Load the SavedModel
    model = tf.saved_model.load(model_path)

    # Check available signatures
    signatures = list(model.signatures.keys())
    logger.info(f"Available signatures: {signatures}")

    # Get the serving signature
    if 'serving_default' in signatures:
        logger.info("Using 'serving_default' signature")
    else:
        logger.warning(f"'serving_default' not found, available: {signatures}")

    logger.info("Model loaded successfully")
    return model


@app.route('/v1/models/<model_name>', methods=['GET'])
def get_model_status(model_name):
    """Return model status (TF Serving compatible)."""
    if model is None:
        return jsonify({
            "model_version_status": [{
                "version": "1",
                "state": "LOADING",
                "status": {"error_code": "UNKNOWN", "error_message": "Model not loaded"}
            }]
        })

    return jsonify({
        "model_version_status": [{
            "version": "1",
            "state": "AVAILABLE",
            "status": {"error_code": "OK", "error_message": ""}
        }]
    })


@app.route('/v1/models/<model_name>/metadata', methods=['GET'])
def get_model_metadata(model_name):
    """Return model metadata (TF Serving compatible)."""
    if model is None:
        return jsonify({"error": "Model not loaded"}), 503

    signatures = {}
    for sig_name in model.signatures.keys():
        sig = model.signatures[sig_name]
        inputs = {}
        outputs = {}

        # Get input specs
        for name, spec in sig.structured_input_signature[1].items():
            inputs[name] = {
                "dtype": spec.dtype.name,
                "tensor_shape": {"dim": [{"size": str(d) for d in spec.shape}]}
            }

        # Get output specs (from structured_outputs if available)
        if hasattr(sig, 'structured_outputs'):
            for name, tensor in sig.structured_outputs.items():
                outputs[name] = {
                    "dtype": tensor.dtype.name,
                    "tensor_shape": {"dim": [], "unknown_rank": True}
                }

        signatures[sig_name] = {
            "inputs": inputs,
            "outputs": outputs,
            "method_name": "tensorflow/serving/predict"
        }

    return jsonify({
        "model_spec": {"name": model_name, "signature_name": "", "version": "1"},
        "metadata": {"signature_def": {"signature_def": signatures}}
    })


@app.route('/v1/models/<model_name>:predict', methods=['POST'])
def predict(model_name):
    """Handle prediction requests. Supports raw JSON and base64 tf.Example."""
    if model is None:
        return jsonify({"error": "Model not loaded"}), 503

    try:
        data = request.get_json()
        instances = data.get('instances', [])

        if not instances:
            return jsonify({"error": "No instances provided"}), 400

        # Get the serving function and its input signature
        serve_fn = model.signatures['serving_default']
        input_specs = serve_fn.structured_input_signature[1]
        input_names = list(input_specs.keys())

        # Auto-detect input format based on first instance
        first_instance = instances[0]
        is_raw_json = isinstance(first_instance, dict) and 'b64' not in first_instance

        if is_raw_json:
            # Raw JSON format - build tensors from feature values
            input_tensors = {}
            for input_name in input_names:
                values = [inst.get(input_name) for inst in instances]
                dtype = input_specs[input_name].dtype
                input_tensors[input_name] = tf.constant(values, dtype=dtype)
            result = serve_fn(**input_tensors)
        else:
            # Base64 tf.Example format (legacy)
            serialized_examples = []
            for instance in instances:
                if isinstance(instance, dict) and 'b64' in instance:
                    serialized = base64.b64decode(instance['b64'])
                    serialized_examples.append(serialized)
                else:
                    return jsonify({"error": "Expected base64-encoded tf.Example"}), 400
            examples_tensor = tf.constant(serialized_examples, dtype=tf.string)
            result = serve_fn(examples=examples_tensor)

        # Convert result to JSON-serializable format (handle bytes for string product IDs)
        predictions = []
        for i in range(len(instances)):
            pred = {}
            for key, tensor in result.items():
                value = tensor[i].numpy()
                if hasattr(value, 'tolist'):
                    if isinstance(value, bytes):
                        # Single byte string value
                        pred[key] = value.decode('utf-8')
                    elif hasattr(value, 'dtype') and value.dtype.kind == 'S':
                        # Array of byte strings
                        pred[key] = [v.decode('utf-8') if isinstance(v, bytes) else v
                                     for v in value.tolist()]
                    else:
                        pred[key] = value.tolist()
                else:
                    pred[key] = value
            predictions.append(pred)

        return jsonify({"predictions": predictions})

    except Exception as e:
        logger.exception(f"Prediction error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Cloud Run."""
    if model is not None:
        return jsonify({"status": "healthy", "model": "loaded"})
    return jsonify({"status": "unhealthy", "model": "not loaded"}), 503


# Load model when module is imported (gunicorn preload)
logger.info("Loading model at module import...")
load_model()
logger.info("Model loaded, server ready to accept requests")

if __name__ == '__main__':
    # For local testing
    port = int(os.environ.get('PORT', 8501))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
