# TensorFlow/TFX/TFRS Testing Guide

This document describes how to set up and run TensorFlow, TFX, and TensorFlow Recommenders tests locally.

## Prerequisites

### Conda Environments

The project uses conda environments with TensorFlow pre-installed. Available environments:

| Environment | Python | TensorFlow | TFX | Use Case |
|-------------|--------|------------|-----|----------|
| `tf_2.12_py39` | 3.9.18 | 2.15.1 | 1.15.0 | TFX pipeline testing |
| `metro_rec` | 3.7.12 | 2.10.0 | - | TFRS model development |
| `tflowenv` | varies | varies | - | General TF work |

### Installing TFX (if needed)

TFX 1.15.0 requires Python 3.9-3.10. To install in `tf_2.12_py39`:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39
pip install tfx==1.15.0
```

## Running Tests

### 1. Basic Test Execution

```bash
# Activate the TFX environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39

# Run a specific test file
python tests/test_proposed_split_fix.py

# Run with pytest (if installed)
python -m pytest tests/test_proposed_split_fix.py -v
```

### 2. Running TFX-Specific Tests

Tests that validate TFX pipeline configurations:

```bash
# Activate TFX environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39

# Run split strategy tests
python tests/test_split_strategies.py --no-django

# Run proposed fix validation
python tests/test_proposed_split_fix.py

# Run integration tests (requires Django)
python tests/test_proposed_fix_integration.py
```

### 3. Running Tests with Django

Some tests require Django models. Run from project root:

```bash
# Using the default Python environment with Django
python -m pytest tests/test_split_strategies.py -v

# Or run specific test class
python -m pytest tests/test_split_strategies.py::TestSQLGeneration -v
```

### 4. Running Tests Without Django

Tests that don't need Django (pure TFX/Python tests):

```bash
# Split strategy tests without Django
python tests/test_split_strategies.py --no-django

# This runs only:
# - TestHashBucketsRatios
# - TestInlineScript
```

## Test Files Reference

| Test File | Description | Requires Django | Requires TFX |
|-----------|-------------|-----------------|--------------|
| `tests/test_split_strategies.py` | Validates split strategy implementation | Partial | No |
| `tests/test_proposed_split_fix.py` | Validates temporal split fix | No | Yes |
| `tests/test_proposed_fix_integration.py` | Integration tests with BigQueryService | Yes | Yes |
| `tests/test_bq_example_gen.py` | BigQueryExampleGen configuration tests | No | Yes |

## Quick Test Commands

### Verify TFX Installation

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39
python -c "import tfx; print(f'TFX version: {tfx.__version__}')"
python -c "from tfx.proto import example_gen_pb2; print('TFX protos available')"
```

### Verify TensorFlow Recommenders

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate metro_rec
python -c "import tensorflow_recommenders as tfrs; print(f'TFRS version: {tfrs.__version__}')"
```

### Test TFX BigQueryExampleGen Configuration

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39
python -c "
from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
from tfx.proto import example_gen_pb2

# Test input_config with multiple splits
input_config = example_gen_pb2.Input(splits=[
    example_gen_pb2.Input.Split(name='train', pattern='SELECT 1'),
    example_gen_pb2.Input.Split(name='eval', pattern='SELECT 2'),
    example_gen_pb2.Input.Split(name='test', pattern='SELECT 3'),
])
example_gen = BigQueryExampleGen(input_config=input_config)
print('BigQueryExampleGen configured successfully')
print(f'Splits: {[s.name for s in input_config.splits]}')
"
```

### Test generate_output_split_names Function

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39
python -c "
from tfx.proto import example_gen_pb2
from tfx.components.example_gen import utils

# Test with input_config splits (recommended approach)
input_config = example_gen_pb2.Input(splits=[
    example_gen_pb2.Input.Split(name='train', pattern='Q1'),
    example_gen_pb2.Input.Split(name='eval', pattern='Q2'),
    example_gen_pb2.Input.Split(name='test', pattern='Q3'),
])
output_config = example_gen_pb2.Output()

split_names = utils.generate_output_split_names(input_config, output_config)
print(f'Generated split names: {split_names}')
assert split_names == ['train', 'eval', 'test'], 'Split names mismatch!'
print('Test PASSED')
"
```

## Debugging TFX Pipelines

### Inspect Protobuf Serialization

```python
from tfx.proto import example_gen_pb2
from google.protobuf import json_format

# Create config
output_config = example_gen_pb2.Output(
    split_config=example_gen_pb2.SplitConfig(
        splits=[
            example_gen_pb2.SplitConfig.Split(name='train', hash_buckets=16),
        ]
    )
)

# Serialize to JSON (as TFX does for Kubeflow)
json_str = json_format.MessageToJson(output_config, preserving_proto_field_name=True)
print(f"JSON: {json_str}")

# Parse back
parsed = example_gen_pb2.Output()
json_format.Parse(json_str, parsed)
print(f"Parsed splits: {[s.name for s in parsed.split_config.splits]}")
```

### Check Available TFX Components

```python
from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen

print("Available components:")
print(f"  - BigQueryExampleGen: {BigQueryExampleGen}")
print(f"  - StatisticsGen: {StatisticsGen}")
print(f"  - SchemaGen: {SchemaGen}")
print(f"  - Transform: {Transform}")
print(f"  - Trainer: {Trainer}")
```

## Common Issues

### 1. TFX Not Found

```
ModuleNotFoundError: No module named 'tfx'
```

**Solution:** Activate the correct conda environment:
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39
```

### 2. Python Version Incompatibility

```
ERROR: No matching distribution found for tfx==1.15.0
```

**Solution:** TFX 1.15.0 requires Python 3.9-3.10. Use `tf_2.12_py39` environment.

### 3. Django Not Available

```
ModuleNotFoundError: No module named 'django'
```

**Solution:** Run tests that don't require Django:
```bash
python tests/test_split_strategies.py --no-django
```

Or install Django in the conda environment (may cause conflicts).

### 4. TensorFlow Warnings

```
FutureWarning: You are using a non-supported Python version
```

These warnings can be ignored for testing purposes. The code still works.

## Environment Setup Script

Save this as `scripts/setup_tfx_env.sh`:

```bash
#!/bin/bash
# Setup TFX testing environment

echo "Activating TFX environment..."
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39

echo "Verifying TFX installation..."
python -c "import tfx; print(f'TFX {tfx.__version__} ready')"

echo "Running quick validation..."
python -c "
from tfx.proto import example_gen_pb2
from tfx.components.example_gen import utils
input_config = example_gen_pb2.Input(splits=[
    example_gen_pb2.Input.Split(name='train', pattern='Q1'),
    example_gen_pb2.Input.Split(name='eval', pattern='Q2'),
])
output_config = example_gen_pb2.Output()
names = utils.generate_output_split_names(input_config, output_config)
print(f'Split names: {names}')
print('Validation PASSED')
"

echo ""
echo "Environment ready. Run tests with:"
echo "  python tests/test_proposed_split_fix.py"
echo "  python tests/test_split_strategies.py --no-django"
```

## Related Documentation

- [TFX Documentation](https://www.tensorflow.org/tfx/guide)
- [BigQueryExampleGen](https://www.tensorflow.org/tfx/guide/examplegen#bigqueryexamplegen)
- [Split Configuration](https://www.tensorflow.org/tfx/guide/examplegen#split)
- [Bug Fix: Temporal Split Strategies](./bug_fix_temporal_split_strategies.md)
