# History (Taste Vector) No-Impact Investigation

**Date**: 2026-02-27
**Experiment under investigation**: quick-tests/168 (`exp_retv_v6`)
**Conclusion**: Two bugs found + one fundamental data design issue (label leakage)

---

## 1. Problem Statement

Three experiments were run to measure the incremental impact of scalar context features and purchase history taste vectors on retrieval metrics:

| Experiment | ID | Features | R@5 | R@10 | R@50 | R@100 |
|---|---|---|---|---|---|---|
| `retr_v3` | 147 | Baseline (no scalars, no history) | 3.8% | 6.7% | 21.9% | 32.8% |
| `retv_v5` | 162 | + scalar context features | 5.2% | 8.1% | 22.0% | 33.1% |
| `exp_retv_v6` | 168 | + scalar context + history vector | 5.4% | 9.3% | 23.3% | 34.2% |

Scalar features added 1-2% to R@5 and R@10. The history taste vector yielded negligible additional improvement despite being a 32D embedding derived from up to 50 product IDs per buyer.

The objective of this investigation: trace the entire pipeline end-to-end to find whether there is a bug preventing the history vector from having its expected impact.

---

## 2. Sources Analysed

### 2.1 Documentation

| File | Purpose |
|---|---|
| `docs/purchase_history.md` | Design document for averaged purchase history embedding feature |
| `docs/phase_configs.md` | Comprehensive spec for Configs domain, dataset wizard, feature engineering, model structure; Section "Chapter 5: Data - Training Views (Ternopil)" describes v3/v4 views |
| `README.md` | Project overview, architecture, tech stack |

### 2.2 SQL Views (BigQuery)

| File | Purpose |
|---|---|
| `sql/create_ternopil_train_v4_view.sql` | Training view definition — source of `purchase_history` column |
| `sql/create_ternopil_test_v4_view.sql` | Test view definition — point-in-time correct history from training period |

### 2.3 Code Generation (Python)

| File | Lines | Function | Purpose |
|---|---|---|---|
| `ml_platform/configs/services.py` | 927-988 | `PreprocessingFnGenerator.generate()` | Orchestrates transform code generation |
| `ml_platform/configs/services.py` | 937-946 | `generate()` | Detects `shared_cols` for vocabulary sharing |
| `ml_platform/configs/services.py` | 990-1023 | `_collect_all_features()` | Classifies features by type (text/numeric/temporal/history) |
| `ml_platform/configs/services.py` | 1269-1331 | `_generate_text_transforms()` | Generates `tft.vocabulary()` + `tft.apply_vocabulary()` split for shared cols |
| `ml_platform/configs/services.py` | 1613-1652 | `_generate_history_transforms()` | Generates `tft.apply_vocabulary()` for history using shared vocab tensor |
| `ml_platform/configs/services.py` | 1814-1840 | `_collect_features_by_type()` | Trainer-side feature type classification |
| `ml_platform/configs/services.py` | 1842-1886 | `_find_shared_embedding_pairs()` | Finds (history_col, primary_col) links via `shared_with` |
| `ml_platform/configs/services.py` | 2218-2257 | `_generate_history_padding_code()` | Generates SparseTensor → dense padding in `_input_fn` |
| `ml_platform/configs/services.py` | 2259-2326 | `_generate_input_fn()` | Generates `_input_fn()` with history padding `.map()` |
| `ml_platform/configs/services.py` | 2328-2535 | `_generate_buyer_model()` | Generates BuyerModel class with shared embedding + masked averaging |
| `ml_platform/configs/services.py` | 2537-2636 | `_generate_product_model()` | Generates ProductModel class with shared embedding for product_id |
| `ml_platform/configs/services.py` | 2743-2770 | `_generate_shared_embedding_code()` | Creates shared `tf.keras.layers.Embedding` |
| `ml_platform/configs/services.py` | 2772-2793 | `_generate_tower_instantiation_code()` | Passes shared embedding to both towers |
| `ml_platform/configs/services.py` | 2795-2915 | `_generate_retrieval_model()` | Generates RetrievalModel with `query_tower` and `candidate_tower` |
| `ml_platform/configs/services.py` | 2993-3016 | `_generate_serve_history_padding()` | Generates post-TFT padding for serve functions |
| `ml_platform/configs/services.py` | 3018-3074 | `_generate_raw_tensor_signature()` | Generates serve input spec including history `[None, max_length]` |
| `ml_platform/configs/services.py` | 4214-4413 | `_generate_run_fn()` | Generates TFX Trainer entry point |

### 2.4 Data Pipeline

| File | Lines | Function | Purpose |
|---|---|---|---|
| `ml_platform/datasets/services.py` | 1190-1239 | `generate_query()` | SQL query generation with column alias application |
| `ml_platform/datasets/services.py` | 1207-1209 | `generate_query()` | ARRAY columns pass through without COALESCE |
| `ml_platform/training/services.py` | 2930-3024 | `create_training_pipeline()` | TFX pipeline construction with BigQueryExampleGen |

### 2.5 Database Records (PostgreSQL)

| Model | ID | Key Fields |
|---|---|---|
| `QuickTest` | 168 | status=completed, split_strategy=random, epochs=100, batch_size=4096, lr=0.001, retrieval_algorithm=brute_force |
| `FeatureConfig` | 39 | name=`feat_retr_v6`, buyer features: customer_id, history, date, cust_value, cs_last_purch, cs_orders, cs_unique_skus |
| `Dataset` | 43 | name=`data_retr_v6`, primary_table=`raw_data.ternopil_train_v4` |
| `ModelConfig` | 34 | name=`mod_retr_v6`, model_type=retrieval, towers: 256→128→64→32 |

### 2.6 GCS Artifacts Inspected

| GCS Path | Content |
|---|---|
| `gs://b2b-recs-quicktest-artifacts/qt-168-20260226-180750/transform_module.py` | Deployed transform code (verified correct) |
| `gs://b2b-recs-quicktest-artifacts/qt-168-20260226-180750/trainer_module.py` | Deployed trainer module (1,678 lines, verified correct) |
| `gs://b2b-recs-quicktest-artifacts/qt-168-20260226-180750/training_metrics.json` | Training metrics (100 epochs, final test_recall_at_5=0.0538) |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-168-20260226-180750/.../SchemaGen_.../schema.pbtxt` | Pre-transform schema: history is INT type with `value_count { min: 1 }` |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-168-20260226-180750/.../Transform_.../post_transform_schema/schema.pbtxt` | Post-transform schema: history is INT type with `is_categorical: true` |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-168-20260226-180750/.../Transform_.../transform_graph/transform_fn/assets/product_id_vocab` | Vocabulary file: 976 entries, string representations of INT64 product IDs |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-168-20260226-180750/.../BigQueryExampleGen_.../examples/Split-train/data_tfrecord-00000-of-00001.gz` | Raw training TFRecords (74,346 examples) |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-168-20260226-180750/.../Transform_.../transformed_examples/Split-train/transformed_examples-00000-of-00001.gz` | Transformed training TFRecords |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-168-20260226-180750/.../Transform_.../transformed_examples/Split-test/transformed_examples-00000-of-00001.gz` | Transformed test TFRecords |

### 2.7 External References

| Source | Purpose |
|---|---|
| [TFX BigQueryExampleGen executor.py](https://github.com/tensorflow/tfx/blob/master/tfx/extensions/google_cloud_big_query/example_gen/executor.py) | Confirmed INT64 → `int64_list` serialization |
| [TFX BigQuery utils.py (row_to_example)](https://github.com/tensorflow/tfx/blob/master/tfx/extensions/google_cloud_big_query/utils.py) | Confirmed ARRAY<INT64> → `int64_list`, NULL → empty Feature |
| [tft.apply_vocabulary API docs](https://www.tensorflow.org/tfx/transform/api_docs/python/tft/apply_vocabulary) | Confirmed int64 input is accepted (auto-cast to string for lookup) |
| [TFX PR #1731](https://github.com/tensorflow/tfx/pull/1731/files) | BigQuery array support in BigQueryExampleGen |

---

## 3. End-to-End Pipeline Trace

### 3.1 Stage 1: BigQuery View (`ternopil_train_v4`)

**SQL definition** (`sql/create_ternopil_train_v4_view.sql`):

```sql
-- CTE 1: train_data = all rows EXCEPT last day
-- CTE 2: top_products = top 80% products by cumulative revenue
-- CTE 3: customer_products = unique (customer, product) pairs from train_data
-- CTE 4: customer_purchase_history =
SELECT customer_id,
       ARRAY_AGG(product_id ORDER BY last_purchase_date DESC LIMIT 50) AS purchase_history
FROM customer_products
GROUP BY customer_id
-- CTE 5: product_stats = aggregate stats per product

-- Final output:
SELECT t.*, ch.purchase_history, ps.*
FROM train_data t
LEFT JOIN customer_purchase_history ch ON t.customer_id = ch.customer_id
LEFT JOIN product_stats ps ON t.product_id = ps.product_id
WHERE t.product_id IN (SELECT product_id FROM top_products)
```

**Output column**: `purchase_history` is `ARRAY<INT64>` containing up to 50 product IDs per customer.

**Observation**: The purchase history is computed from the same `train_data` and then LEFT JOINed back. This means for a training row where customer X bought product Y, the `purchase_history` for customer X includes product Y.

### 3.2 Stage 2: SQL Query Generation

**Code**: `ml_platform/datasets/services.py:1207-1209`

```python
if is_array:
    # ARRAY columns pass through without COALESCE or TIMESTAMP conversion
    col_expr = f"{table_alias}.`{col}`"
```

**Column alias applied** (`services.py:1233-1239`):

```python
alias_key = f"{table_alias}_{col}"  # "ternopil_train_v4_purchase_history"
final_name = column_aliases.get(alias_key) or ...  # → "history"
select_cols.append(f"{col_expr} AS `{final_name}`")
```

**Result**: The generated SQL contains `ternopil_train_v4.purchase_history AS history`.

**No CAST to STRING occurs** — the ARRAY<INT64> passes through as-is.

### 3.3 Stage 3: BigQueryExampleGen

**Serialization** (confirmed from TFX source `utils.py:row_to_example`):

```python
# For INTEGER type:
feature[key] = tf.train.Feature(
    int64_list=tf.train.Int64List(value=value_list)
)
# ARRAY<INT64> → value is already a list → used directly
value_list = value if isinstance(value, list) else [value]
```

**TFRecord output**:
- `product_id` (INT64 scalar) → `int64_list` with 1 value → FixedLenFeature in schema
- `history` (ARRAY<INT64>) → `int64_list` with N values → VarLenFeature in schema (SparseTensor)

**Schema** (from `SchemaGen` output):
```protobuf
feature {
  name: "history"
  value_count { min: 1 }    # Variable-length → VarLenFeature → SparseTensor
  type: INT
  presence { min_fraction: 1.0  min_count: 1 }
}
feature {
  name: "product_id"
  type: INT
  shape { dim { size: 1 } }  # Fixed-length → FixedLenFeature → dense tensor
}
```

### 3.4 Stage 4: TFX Transform (preprocessing_fn)

**Deployed code** (`gs://b2b-recs-quicktest-artifacts/qt-168-20260226-180750/transform_module.py`):

```python
# product_id: split into tft.vocabulary() + tft.apply_vocabulary()
# so the deferred vocab tensor can be shared with history
product_id_vocab = tft.vocabulary(
    _densify(inputs['product_id'], b''),
    vocab_filename='product_id_vocab'
)
outputs['product_id'] = tft.apply_vocabulary(
    _densify(inputs['product_id'], b''),
    deferred_vocab_filename_tensor=product_id_vocab,
    num_oov_buckets=NUM_OOV_BUCKETS
)

# ... other features ...

# History: apply SAME vocabulary
outputs['history'] = tft.apply_vocabulary(
    inputs['history'],
    deferred_vocab_filename_tensor=product_id_vocab,
    num_oov_buckets=NUM_OOV_BUCKETS
)
```

**Type handling**:
- `product_id` enters as dense int64 tensor (FixedLenFeature). `_densify` no-ops (not SparseTensor).
- `tft.vocabulary()` accepts int64 input — converts to string internally for vocab file.
- `history` enters as int64 SparseTensor (VarLenFeature). `tft.apply_vocabulary()` accepts int64 — converts each element to string, looks up in vocab, returns vocab index.

**Vocabulary**: 976 entries, string representations of INT64 product IDs (e.g., `"378243001001"`).

### 3.5 Stage 5: Raw TFRecord Verification

**Inspected**: `BigQueryExampleGen/examples/Split-train/data_tfrecord-00000-of-00001.gz`

```
100 examples sampled:
- 100% have history data (int64_list)
- History values are raw product IDs: [157772001001, 107311001001, ...]
- product_id values: [157773001001], [370418001001], ...
- History lengths: min=2, max=50, avg=23.9
```

### 3.6 Stage 6: Transformed TFRecord Verification

**Inspected**: `Transform/transformed_examples/Split-train/transformed_examples-00000-of-00001.gz`

```
100 examples sampled:
- 100% have history data (int64_list with vocab indices)
- History values are valid vocab indices: [196, 21, 323, 37, 157, 24, 45], ...
- Range: 0 to 892 (within vocab_size=976)
- OOV rate: 0.0% (zero out-of-vocabulary values)
- History lengths preserved: min=2, max=50, avg=23.9
```

**Full dataset scan** (74,346 training examples):
```
Total history values: 1,804,301
Values equal to 0 (vocab idx 0): 31,371 (1.74%)
Examples containing history value 0: 31,371 (42.20%)
```

### 3.7 Stage 7: Trainer Data Loading

**Deployed code** (`trainer_module.py`, lines 310-324):

```python
def _input_fn(...):
    dataset = data_accessor.tf_dataset_factory(
        file_pattern,
        tfxio.TensorFlowDatasetOptions(batch_size=batch_size, num_epochs=1),
        tf_transform_output.transformed_metadata.schema
    )

    def _pad_history_features(features):
        if isinstance(features.get('history'), tf.SparseTensor):
            dense = tf.sparse.to_dense(features['history'], default_value=0)
            dense = dense[:, :50]
            pad_size = tf.maximum(50 - tf.shape(dense)[1], 0)
            features['history'] = tf.pad(dense, [[0, 0], [0, pad_size]])
        return features

    return dataset.map(_pad_history_features)
```

**Flow**: SparseTensor → `tf.sparse.to_dense(default_value=0)` → slice to max 50 → pad with 0 → dense `[batch, 50]`

### 3.8 Stage 8: BuyerModel (Query Tower)

**Deployed code** (`trainer_module.py`, lines 405-412):

```python
# history: taste vector (shared embedding + masked average)
history_ids = inputs['history']                              # [batch, 50]
history_embs = self.shared_product_embedding(history_ids)    # [batch, 50, 32]
history_mask = tf.cast(history_ids != 0, tf.float32)         # [batch, 50]
history_mask = tf.expand_dims(history_mask, -1)              # [batch, 50, 1]
history_avg = tf.reduce_sum(history_embs * history_mask, axis=1)  # [batch, 32]
history_avg = history_avg / (tf.reduce_sum(history_mask, axis=1) + 1e-8)  # [batch, 32]
features.append(history_avg)
```

### 3.9 Stage 9: Shared Embedding & Model Construction

**Deployed code** (`trainer_module.py`, lines 583-592):

```python
# Create shared product embedding (used by both towers for product_id)
product_id_vocab_size = tf_transform_output.vocabulary_size_by_name('product_id_vocab')
self.shared_product_embedding = tf.keras.layers.Embedding(
    product_id_vocab_size + NUM_OOV_BUCKETS, 32,
    name='shared_product_embedding'
)

# Feature extraction models (with shared embedding)
self.buyer_model = BuyerModel(tf_transform_output, shared_product_embedding=self.shared_product_embedding)
self.product_model = ProductModel(tf_transform_output, shared_product_embedding=self.shared_product_embedding)
```

### 3.10 Stage 10: Loss Computation

**Deployed code** (`trainer_module.py`, lines 614-617):

```python
def compute_loss(self, features, training=False):
    query_embeddings = self.query_tower(features)       # buyer_model → Dense(256→128→64→32)
    candidate_embeddings = self.candidate_tower(features)  # product_model → Dense(256→128→64→32)
    return self.task(query_embeddings, candidate_embeddings)
```

Both towers receive the same `features` dict. Each tower's model picks only its own features from the dict.

---

## 4. Findings

### 4.1 BUG: Padding/Masking Collision at Vocab Index 0

**Location**: Code generation in `ml_platform/configs/services.py`
- `_generate_history_padding_code()` (line 2246): `default_value=0`
- `_generate_buyer_model()` (line 2508): `history_mask = tf.cast(history_ids != 0, tf.float32)`

**The problem**: Padding fills empty slots with `0`. The mask removes entries where `history_ids == 0`. But vocab index `0` is a valid product — the most popular product (`378243001001`).

**Measured impact on exp 168 data**:
- 42.2% of training examples (31,371 / 74,346) contain the most popular product (vocab index 0) in their history
- In these examples, the most popular product is silently masked out of the taste vector
- Affects 1.74% of all history values (31,371 / 1,804,301)
- Conversely, the OOV bucket (index 976) is never masked, so any OOV entries would be wrongly included in the average

**Severity**: Low-to-medium. Affects only one product out of 976, but it's the highest-frequency one.

### 4.2 BUG: Stale Transform Code in Database

**Location**: `FeatureConfig.generated_transform_code` for FeatureConfig ID 39

**The problem**: The code stored in the DB uses the old pattern:
```python
# DB version (STALE):
outputs['product_id'] = tft.compute_and_apply_vocabulary(...)  # single call
outputs['history'] = tft.apply_vocabulary(
    inputs['history'],
    deferred_vocab_filename_tensor=tft.vocabulary('product_id_vocab'),  # BUG: tft.vocabulary() with string arg
    ...
)
```

The actually deployed code (GCS) uses the correct pattern:
```python
# GCS version (CORRECT):
product_id_vocab = tft.vocabulary(...)    # separate call, returns tensor
outputs['product_id'] = tft.apply_vocabulary(..., deferred_vocab_filename_tensor=product_id_vocab)
outputs['history'] = tft.apply_vocabulary(
    inputs['history'],
    deferred_vocab_filename_tensor=product_id_vocab,  # references local variable
    ...
)
```

**Root cause**: The pipeline submission regenerates fresh code and uploads to GCS. The DB code was saved at an earlier point before the `shared_cols` logic was implemented or before a code regeneration was triggered.

**Severity**: No impact on experiment 168 results (GCS version ran correctly). But the stale DB code would fail if executed — `tft.vocabulary('product_id_vocab')` with a string argument does not return a deferred tensor that `tft.apply_vocabulary` can use.

### 4.3 FUNDAMENTAL ISSUE: Label Leakage in Purchase History

**Location**: `sql/create_ternopil_train_v4_view.sql`, lines 38-52

**The problem**: The `customer_purchase_history` CTE aggregates product IDs from `customer_products`, which is derived from `train_data`. The final SELECT joins this history back to the same `train_data`. This means for every (customer_id, product_id) training row, the `purchase_history` array for that customer **already contains that product_id**.

**SQL flow showing the leak**:
```
train_data: all rows except last day
    ↓
customer_products: DISTINCT (customer_id, product_id) from train_data
    ↓
customer_purchase_history: ARRAY_AGG(product_id) per customer_id
    ↓
FINAL: train_data LEFT JOIN customer_purchase_history
       → Each row's target product_id IS in the history array
```

**Measured from TFRecords**:

| Split | Total Examples | Target in History | Percentage |
|---|---|---|---|
| Train | 74,346 | 73,369 | **98.7%** |
| Test | 4,511 | 4,444 | **98.5%** |

**Why this neutralizes the taste vector**:

1. **Signal dilution**: The taste vector averages ~24 product embeddings. The target product contributes only ~1/24 ≈ 4.2% of the average. After 4 dense layers (256→128→64→32), this weak signal is compressed further.

2. **Redundancy with customer_id**: The `customer_id` embedding (64D, per-customer learned vector) already encodes per-customer preferences. During training, the model learns a unique embedding for each customer that captures which products they prefer. The taste vector provides the same information in a diluted form.

3. **Optimization dynamics**: With customer_id providing a strong, direct signal and the taste vector providing a weak, indirect version of the same signal, gradient descent naturally allocates model capacity to the stronger signal. The taste vector weights converge to near-zero contribution because they're redundant.

4. **No new information at evaluation**: In the test set, 98.5% of examples also have the target in history (because history is computed from historical_data = training period, and the customer likely bought the same product before). So the leakage doesn't create a train/test discrepancy — it's consistent, but the signal is still too diluted to matter.

### 4.4 MINOR: Experiment Comparison Not Controlled

The three experiments differ in more than just the history feature:

| Variable | Exp 147 | Exp 162 | Exp 168 |
|---|---|---|---|
| Tower layers | 3 (128→64→32) | 3 (128→64→32) | **4 (256→128→64→32)** |
| Batch size | 1024 | 4096 | 4096 |
| Dataset | ternopil_train | ternopil_train_v4 | ternopil_train_v4 |
| Buyer text features | customer_id, segment | customer_id | customer_id |
| Buyer numeric features | cust_value | cust_value + 3 more | cust_value + 3 more |
| Product text features | 5 | 6 | 7 |
| Product numeric features | 0 | 5 | 5 |
| History | No | No | Yes (32D) |

The R@10 improvement from 162 (8.1%) to 168 (9.3%) could be partially or entirely from the larger tower (4 layers vs 3), not the taste vector.

### 4.5 MINOR: buyer_feature_details Missing History

The denormalized `buyer_feature_details` JSON on QuickTest 168 lists only 6 features:
```json
[
  {"dim": 64, "name": "customer_id"},
  {"dim": 4, "name": "date"},
  {"dim": 1, "name": "cust_value"},
  {"dim": 1, "name": "cs_last_purch"},
  {"dim": 1, "name": "cs_orders"},
  {"dim": 1, "name": "cs_unique_skus"}
]
```

The `history` feature (32D) is missing. This is a display-only bug in how `update_denormalized_fields` (or similar) computes the buyer feature dimension list — it likely skips history-type features.

---

## 5. Data Verification Summary

### 5.1 Raw TFRecords (Pre-Transform)

Sampled 100 of 74,346 training examples from `BigQueryExampleGen/examples/Split-train/`:

```
Example 1: history int64_list = [157772001001, 107311001001, 157773001001, 153792001001, 187910001001]
           product_id int64 = [157773001001]
Example 2: history int64_list = [9654001001, 374401001001, 376186001001, 382407001001, 280613001001, ...]
           product_id int64 = [370418001001]
Example 3: history int64_list = [378243001001, 333472001001, 41515001001, 324527001002, 383687001001, ...]
           product_id int64 = [333472001001]

Result: 100/100 examples have history data. Lengths: min=2, max=50, avg=23.9
```

### 5.2 Transformed TFRecords (Post-Transform)

Sampled 100 of 74,346 training examples from `Transform/transformed_examples/Split-train/`:

```
Example 1: history = [196, 21, 323, 37, 157, 24, 45]
           product_id = [323]       ← 323 IS in history
Example 2: history = [410, 511, 70, 10, 864, 25, 65, 73, 62, 202, ...]
           product_id = [7]         ← 7 is NOT in shown slice (but is elsewhere in full array)
Example 3: history = [0, 259, 348, 55, 87, 293, 3, 696, 9, 360, ...]
           product_id = [259]       ← 259 IS in history

Result: 100/100 examples have valid vocab indices. Range: 0-892. OOV: 0%.
```

### 5.3 Full Dataset Statistics

```
Training set (74,346 examples):
  Total history values: 1,804,301
  Average history per example: 24.3
  Values equal to vocab index 0: 31,371 (1.74%)
  Examples containing index 0: 31,371 (42.20%)   ← BUG #1 impact
  Target product_id IN history: 73,369 (98.7%)    ← Label leakage

Test set (4,511 examples):
  Target product_id IN history: 4,444 (98.5%)     ← Label leakage in test too
```

### 5.4 Product ID Vocabulary

```
File: transform_graph/transform_fn/assets/product_id_vocab
Entries: 976 unique product IDs
Format: string representations of INT64 (e.g., "378243001001")
First entry (index 0): "378243001001"  ← Most popular product, masked by BUG #1
```

---

## 6. Deployed Code Verification

### 6.1 Transform Module (GCS vs DB)

| Aspect | GCS (deployed) | DB (stored) |
|---|---|---|
| product_id vocab | `product_id_vocab = tft.vocabulary(...)` (split) | `tft.compute_and_apply_vocabulary(...)` (single) |
| history vocab ref | `deferred_vocab_filename_tensor=product_id_vocab` (local var) | `deferred_vocab_filename_tensor=tft.vocabulary('product_id_vocab')` (string arg) |
| Status | **Correct** | **Stale/incorrect** |

### 6.2 Trainer Module (GCS)

All components verified in the deployed trainer module:

- `_input_fn`: Pads history SparseTensor → dense [batch, 50] with `default_value=0`
- `BuyerModel.__init__`: Receives `shared_product_embedding` parameter, stores it
- `BuyerModel.call`: Embeds history via shared embedding, masks `!= 0`, averages, appends to features
- `ProductModel.__init__`: Receives `shared_product_embedding` parameter
- `ProductModel.call`: Uses shared embedding for `product_id` lookup
- `RetrievalModel.__init__`: Creates shared embedding (976+1 entries, 32D), passes to both models
- `RetrievalModel.compute_loss`: Passes features dict to both towers, computes retrieval loss
- Tower architecture: `Sequential([BuyerModel, Dense(256,relu,l2=0.02), Dense(128,relu,l2=0.02), Dense(64,relu), Dense(32,relu)])`

### 6.3 Training Results

```
Training: 100 epochs, 74,346 examples, batch_size=4096
Final training loss: 2528.8
Final validation loss: 19,632.5
Test loss: 3,784.6
Test Recall@5: 5.38%
Test Recall@10: 9.30%
Test Recall@50: 23.30%
Test Recall@100: 34.18%
```

---

## 7. Root Cause Conclusion

The history taste vector has near-zero impact due to a **combination of three factors**:

1. **Label leakage** (primary cause): 98.7% of training examples have the target product in the purchase history. The taste vector encodes a diluted version (1/24) of information that the 64D customer_id embedding already learns directly. The model's optimizer naturally ignores the weaker, redundant signal.

2. **Padding/masking bug** (secondary): The most popular product (vocab index 0) is incorrectly masked in 42% of examples, slightly degrading the taste vector quality.

3. **Uncontrolled experiment** (confounding): Experiment 168 uses larger towers than 162, so the observed R@10 improvement (8.1% → 9.3%) cannot be attributed to the taste vector.

---

## 8. Recommendations

### Fix Bug #1: Padding Value

Change padding from `0` to a dedicated padding index that won't collide with valid vocab indices:

- Option A: Use `-1` as padding value, mask with `history_ids >= 0`
- Option B: Shift all vocab indices by +1 (so valid range is 1-977, and 0 is reserved for padding)
- Option C: Use `vocab_size + num_oov_buckets` as padding value (guaranteed unused)

### Fix Bug #2: Stale DB Code

After pipeline submission, update the DB `generated_transform_code` field with the fresh code that was actually deployed.

### Fix Label Leakage

Modify the `ternopil_train_v4` SQL view to **exclude the current row's product from the history**:

```sql
-- Option: Compute history per (customer, product) pair, excluding the target product
customer_purchase_history AS (
  SELECT
    cp1.customer_id,
    cp1.product_id AS target_product_id,
    ARRAY_AGG(cp2.product_id ORDER BY cp2.last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products cp1
  CROSS JOIN customer_products cp2
  WHERE cp1.customer_id = cp2.customer_id
    AND cp1.product_id != cp2.product_id    -- EXCLUDE target product
  GROUP BY cp1.customer_id, cp1.product_id
)
```

Note: This changes the view from customer-level to (customer, product)-level history, which significantly increases query complexity. An alternative is to compute it at the application level during data generation.

### Run Controlled Experiment

After fixing the above, re-run with:
- Same tower architecture as exp 162 (128→64→32)
- Same batch size, learning rate, epochs
- Same dataset (v4)
- Only difference: with vs without history feature
