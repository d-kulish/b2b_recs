# Hybrid Model: Architecture, Testing & Next Steps

## Document Purpose

This document covers the hybrid (multitask) model architecture — how it works today, how it should work at production scale, what was tested, what bugs were found, and the roadmap to a fully operational two-stage retrieval→ranking recommendation pipeline.

**Created**: 2026-02-10
**Model tested**: `chern_hybrid_v3` (Vertex AI ID: `7115797362408161280`, training run `tr-29`)

---

## 1. How the Two-Stage Pipeline Works in Industry

### 1.1 The Standard Architecture

Every major recommendation system (Google, YouTube, Pinterest, Alibaba, Spotify) uses a **multi-stage funnel**:

```
Full Catalog (millions of items)
        │
        ▼
┌──────────────────────────┐
│  STAGE 1: RETRIEVAL      │  ← Fast, approximate
│  Input: user features    │
│  Output: top-K candidates│     K = 100–1000
│  Latency: 5–50ms        │
│  Method: ANN (ScaNN/FAISS)│
└──────────┬───────────────┘
           │  K candidates
           ▼
┌──────────────────────────┐
│  STAGE 2: FEATURE        │  ← Enrich candidates
│  ENRICHMENT              │     with full features
│  Source: Feature Store    │
│  Latency: 5–50ms        │
└──────────┬───────────────┘
           │  K candidates + features
           ▼
┌──────────────────────────┐
│  STAGE 3: RANKING        │  ← Precise scoring
│  Input: user + item      │
│  Output: scores per item │
│  Latency: 20–100ms      │
│  Method: Rating head     │
└──────────┬───────────────┘
           │  K scored candidates
           ▼
┌──────────────────────────┐
│  STAGE 4: RE-RANKING     │  ← Business rules
│  (Optional)              │
│  Diversity, freshness,   │
│  already-purchased filter│
└──────────┬───────────────┘
           │  Final N results
           ▼
      User sees N items
```

### 1.2 Why Multitask (Hybrid) Models Exist

The TFRS multitask model trains **both stages in a single model** with shared embeddings:

- **Retrieval task**: `tfrs.tasks.Retrieval()` — learns embeddings via in-batch negative sampling (dot product similarity)
- **Ranking task**: `tfrs.tasks.Ranking(loss=MSE)` — learns a rating head that predicts a target value (e.g., sales) from concatenated user+product embeddings
- **Combined loss**: `retrieval_weight × retrieval_loss + ranking_weight × ranking_loss`

**Benefits over separate models:**
- **Transfer learning**: The abundant retrieval signal (implicit feedback from all transactions) improves the ranking head (which has sparser signal from the target column)
- **Shared embeddings**: Both tasks inform the same embedding space, leading to more coherent recommendations
- **Single training pipeline**: One training run produces both capabilities
- **Simpler deployment**: One SavedModel with two serving signatures

**When separate models are better:**
- When retrieval and ranking use fundamentally different feature sets
- When the ranking target is very different from the retrieval signal
- When team ownership requires independent model lifecycles
- At very large scale (billions of items) where retrieval must be extremely fast

### 1.3 How Big Companies Organize This

#### Google / YouTube
- **Retrieval**: Two-tower model producing user/item embeddings, served via ScaNN or FAISS
- **Ranking**: Deep neural network with hundreds of features (user history, context, item metadata)
- **Feature Store**: Bigtable/Spanner for low-latency feature lookups
- **Orchestration**: A lightweight serving layer orchestrates the funnel
- Reference: [Deep Neural Networks for YouTube Recommendations (2016)](https://research.google.com/pubs/archive/45530.pdf)

#### Pinterest
- **Retrieval**: PinSage (graph-based) + two-tower models
- **Ranking**: Multi-task learning (engagement + quality + relevance)
- **Feature Store**: RealPin (custom) → now migrating to Feast
- Reference: [PinSage: A New Graph Convolutional Neural Network (2018)](https://arxiv.org/abs/1806.01973)

#### Alibaba
- **Retrieval**: MIND (Multi-Interest Network with Dynamic routing)
- **Ranking**: DIN (Deep Interest Network) with attention over user behavior
- **Feature Store**: Real-time feature computation on Flink
- Reference: [Deep Interest Network for Click-Through Rate Prediction (2018)](https://arxiv.org/abs/1706.06978)

### 1.4 The Missing Component: Feature Store

The critical piece connecting retrieval → ranking is a **feature store** — a low-latency database that maps `product_id → full product features`:

```
Retrieval returns:  [product_208, product_266, product_629, ...]
                              │
                              ▼
Feature Store lookup:  SELECT product_id, category, sub_category, price, ...
                       FROM product_features
                       WHERE product_id IN (208, 266, 629, ...)
                              │
                              ▼
Ranking receives:     [{customer_id: X, product_id: 208, category: "DRY", ...},
                       {customer_id: X, product_id: 266, category: "FRESH", ...},
                       ...]
```

**Options for our GCP stack:**

| Option | Latency | Cost/mo | Complexity | Best For |
|--------|---------|---------|------------|----------|
| **Redis / Memorystore** | ~1ms | ~$50–150 | Low | < 100K products, real-time |
| **Firestore** | ~10ms | ~$0–20 | Low | Already in stack, small catalogs |
| **BigQuery (cached view)** | ~200ms | ~$5 | Minimal | Batch/offline, acceptable latency |
| **Vertex AI Feature Store** | ~5ms | ~$100+ | Medium | Full MLOps, time-travel features |
| **Cloud SQL (existing)** | ~5ms | $0 (already paid) | Minimal | Use existing PostgreSQL |

**Recommended for our case**: Start with **Cloud SQL** (already running) or **Firestore** (already used for ETL). A simple `product_features` table with 1,071 rows is tiny — even BigQuery would work.

---

## 2. Current Implementation: What Exists Today

### 2.1 Model Architecture

The `chern_hybrid_v3` model was generated by `TrainerModuleGenerator._generate_multitask_trainer()`:

```
FeatureConfig: "cherng_v3_rank_#1" (ID: 9)
ModelConfig:   "hybrid_v1" (ID: 17)

Buyer features:   customer_id (INT, emb=64), date (TIMESTAMP, cyclical), cust_value (FLOAT, z-score+bucket)
Product features: product_id (INT, emb=32), category (STRING, emb=8), sub_category (STRING, emb=16)
Cross features:   customer_id × cust_value (hash=5000, emb=16), category × sub_category (hash=1000, emb=16)
Target column:    sales (FLOAT, clip 1th–90th percentile → log1p)

Query tower:      BuyerModel → Dense(128) → Dense(64) → Dense(32)
Candidate tower:  ProductModel → Dense(128) → Dense(64) → Dense(32)
Rating head:      Dense(128) → Dense(64) → Dense(32) → Dense(1)

Optimizer: Adam (lr=0.001)
Batch size: 1024
Epochs: 5
Retrieval weight: 1.0
Ranking weight: 1.0
Retrieval algorithm: brute_force (top_k=100)
```

### 2.2 Dual Serving Signatures

The SavedModel is exported with two TF functions:

| Signature | Purpose | Input | Output |
|-----------|---------|-------|--------|
| `serving_default` | Retrieval — get top-100 candidates | Serialized `tf.Example` (all features) | `product_ids` (int32[100]), `scores` (float32[100]) |
| `serve_ranking` | Ranking — score user-product pairs | Serialized `tf.Example` (all features) | `predictions` (float32[1]), `predictions_normalized` (float32[1]) |

### 2.3 Deployment Infrastructure

Two container images exist for Cloud Run serving:

| Container | Image | Use Case |
|-----------|-------|----------|
| `tf-serving-native` | `tensorflow/serving:2.19.0` + gsutil | Brute-force models — native TF Serving, lower latency |
| `tf-serving-scann` | Python 3.10 + Flask + ScaNN 1.3.0 | ScaNN models — custom Flask server for ScaNN custom ops |

Both download the SavedModel from GCS at startup and expose REST API on port 8501.

---

## 3. Testing: What Was Done and What We Found

### 3.1 Test Setup

- **Deployed**: `chern_hybrid_v3` to Cloud Run as `chern-hybrid-v3-test` using `tf-serving-native` container
- **Model source**: `gs://b2b-recs-training-artifacts/tr-29-20260128-103725/pushed_model/1769602690`
- **Catalog size**: 1,071 unique products (from eval split)
- **Vocabs**: 7,566 customers, 1,071 products, 7 categories, 245 sub-categories

### 3.2 Test 1: Health Check & Metadata

```
GET /v1/models/recommender
→ {"model_version_status": [{"version": "1", "state": "AVAILABLE", "status": {"error_code": "OK"}}]}

GET /v1/models/recommender/metadata
→ Two signatures confirmed: "serving_default" and "serve_ranking"
→ Both accept serialized tf.Example (DT_STRING input named "examples")
```

**Result**: Model loads correctly, both signatures registered.

### 3.3 Test 2: Retrieval — Different Customers Get Different Recommendations

Tested 3 customers with the `serving_default` signature:

| Customer ID | Top-5 Retrieved (vocab indices) | Top Score | Latency |
|------------|-------------------------------|-----------|---------|
| 120063316701 | 208, 266, 629, 218, 188 | 107.07 | 156ms |
| 670001128701 | 456, 497, 459, 383, 801 | 91.22 | 216ms |
| 390061346801 | 496, 538, 399, 171, 87 | 95.51 | 133ms |

**Result**: Each customer gets a **completely different** top-5. The model is producing personalized recommendations. Score ranges differ per customer (107 vs 91 vs 95), reflecting different engagement levels.

### 3.4 Test 3: Ranking — Different Products Get Different Scores

Tested customer `120063316701` with 3 different products using `serve_ranking`:

| Product ID | Category | Predicted Sales (original) | Predicted Sales (normalized) | Latency |
|-----------|----------|--------------------------|------------------------------|---------|
| 378243001001 | DRY | 28.93 | 3.40 | 158ms |
| 378245001001 | FRESH | 85.79 | 4.46 | 213ms |
| 256484001001 | NEAR FOOD | 97.92 | 4.59 | 130ms |

**Result**: The rating head produces **meaningfully different scores** per product. The inverse transform is working correctly — normalized log-scale values (3.4, 4.5, 4.6) are converted back to original sales scale (29, 86, 98) via `expm1()`.

### 3.5 Test 4: Batch Requests

Sent 3 product instances in a single API call to `serve_ranking`:

```json
POST /v1/models/recommender:predict
{
  "signature_name": "serve_ranking",
  "instances": [
    {"examples": {"b64": "<product_1>"}},
    {"examples": {"b64": "<product_2>"}},
    {"examples": {"b64": "<product_3>"}}
  ]
}
```

**Result**: All 3 predictions returned correctly in a single response. Scores matched individual requests. Latency: 333ms for batch of 3.

### 3.6 Test 5: Two-Stage Pipeline Simulation

Simulated the full retrieval → ranking pipeline:

1. **Stage 1 — Retrieval**: Called `serving_default` → got top-5 product vocab indices [208, 266, 629, 218, 188]
2. **Stage 2 — Ranking**: Called `serve_ranking` for each of the 5 products (batch request)

**Result**: The pipeline works mechanically. However, re-ranking produced identical scores (378.13) for all 5 candidates because **placeholder product features** were used (all "DRY"/"UNKNOWN"). This is expected — without a feature store to look up real product features for the retrieved IDs, the ranking head sees identical product inputs and produces identical scores.

**This demonstrates exactly why a feature store is the critical missing component.**

### 3.7 Input Format Discovery

Both signatures accept **serialized `tf.Example` protobuf** (not raw JSON). This is because the model was trained on 2026-01-28, before the raw JSON serving fix (2026-02-02).

Both signatures require **ALL features** from the original BigQuery schema — buyer features, product features, AND the target column (`sales`), plus unused columns (`city`, `region`). This is because `tf_transform_output.raw_feature_spec()` includes every column in the schema, and the TFT layer's `ParseExample` op enforces their presence.

For retrieval, only buyer features feed the query tower, so product/target values can be dummies — but they **must be present** in the serialized proto.

### 3.8 Latency Profile

| Operation | Latency | Notes |
|-----------|---------|-------|
| Cold start (first request after deploy) | ~485ms | Cloud Run instance startup + model load |
| Retrieval (single, warm) | 130–156ms | Includes network + TF Serving processing |
| Ranking (single, warm) | 130–213ms | Similar to retrieval |
| Ranking (batch of 3, warm) | 333ms | Sub-linear scaling |
| Ranking (batch of 5, warm) | 133ms | Cached/warmed, very fast |

---

## 4. Bugs Found

### Bug 1: Product IDs Are Vocabulary Indices (HIGH)

**Symptom**: The `serving_default` retrieval endpoint returns integers like `208, 266, 629` instead of real product IDs like `378243001001`.

**Root cause**: The `_load_original_product_ids()` function is **missing** from the generated trainer module for `chern_hybrid_v3`. The function has 0 occurrences in `tr-29/trainer_module.py`. Instead, the raw vocabulary indices from `_precompute_candidate_embeddings()` are stored directly in the serving model's `product_ids` variable.

**History**: This is the **code gen parity bug** documented on 2026-02-07. The `_load_original_product_ids` function was added to the ScaNN code path but not to the brute_force or multitask paths. `chern_hybrid_v3` was trained on 2026-01-28, before the fix.

**Impact**: Every retrieval call returns vocab indices that must be mapped client-side using the vocabulary file. The mapping is: `vocab_file_line[index] → real_product_id`.

**Fix**: Retrain the model after the 2026-02-07 code fix. New models will include `_load_original_product_ids()` which maps vocab indices back to original IDs before storing in the serving model.

### Bug 2: Both Signatures Require ALL Features (HIGH)

**Symptom**: Calling `serving_default` with only buyer features fails:
```
Error: Feature: category (data type: string) is required but could not be found.
```

**Root cause**: Both `serve()` and `serve_ranking()` use `self._raw_feature_spec = tf_transform_output.raw_feature_spec()` which includes **every column** from the original BigQuery query schema. The `tf.io.parse_example()` call enforces that all features are present.

**Impact**: For retrieval (which only uses buyer features in the query tower), you must still send product features and the target column with dummy values. This makes the API harder to use and wastes bandwidth.

**Ideal fix**: Generate separate feature specs for each signature:
- `serving_default`: Only buyer features required (product features optional/ignored)
- `serve_ranking`: Both buyer and product features required

This requires changes to `TrainerModuleGenerator._generate_serve_fn_multitask()` to build separate `tf.io.parse_example` specs per signature.

### Bug 3: Candidate Embeddings From Eval Split Only (MEDIUM)

**Symptom**: Only 1,071 products are retrievable. Products appearing only in the training split are missing from the candidate index.

**Root cause**: In `run_fn()`, candidate embeddings are pre-computed from the eval dataset:
```python
candidates_dataset = _input_fn(eval_files, ...)
product_ids, product_embeddings = _precompute_candidate_embeddings(model, candidates_dataset)
```

**Impact**: Products that appear only in the training split (not in eval) are unreachable via retrieval. New products not in either split are also missing.

**Fix**: Use the **full dataset** (train + eval) for candidate embedding computation, or better yet, use a dedicated product catalog table that includes all active products.

### Bug 4: `transform_params` is Empty (MEDIUM)

**Symptom**: The inverse transform for ranking predictions uses default parameters.

**Root cause**: In `run_fn()`:
```python
transform_params = {}
# TODO: Extract norm_min/norm_max from first batch if needed
```

**Impact**: If the target column had min-max normalization, the de-normalized predictions would use wrong bounds (0.0, 1.0 instead of actual min/max). For `chern_hybrid_v3`, only log transform was applied to `sales`, so `log_applied=True` and the `expm1()` inverse works correctly. But `normalize_applied=False` here, so no damage. The bug is latent — it would manifest if a future model uses z-score or min-max normalization on the target.

**Fix**: Extract actual normalization parameters from the TFT transform output (or first batch statistics) and pass them to the serving model.

### Bug 5: Input Format Is Serialized Protobuf (LOW — Fixed in Newer Code)

**Symptom**: Requests must contain base64-encoded `tf.Example` protobufs, not simple JSON.

**Root cause**: This model was trained before the 2026-02-02 fix that switched to raw tensor inputs.

**Impact**: Client code must construct protobuf messages, which is complex (see test code). Simple `{"customer_id": "X", "city": "Y"}` JSON doesn't work.

**Fix**: Already fixed in newer code generation. Retrain the model to get the raw JSON input format.

---

## 5. Next Steps

### Phase 1: Retrain with Bug Fixes (Effort: Low)

**Goal**: Get a hybrid model with correct product IDs and raw JSON inputs.

1. **Verify** that the 2026-02-07 code gen fix is applied to the multitask path — `_load_original_product_ids()` must be generated in the trainer module
2. **Verify** that the 2026-02-02 raw JSON serving fix is applied — the serve functions should accept raw tensors, not serialized tf.Example
3. **Retrain** `chern_hybrid_v3` (same configs, same dataset) to produce a new model version
4. **Deploy** to Cloud Run and re-run the tests from Section 3
5. **Validate** that product IDs are now real 12-digit IDs, not vocab indices

### Phase 2: Split Feature Specs per Signature (Effort: Medium)

**Goal**: Retrieval endpoint only requires buyer features.

Modify `TrainerModuleGenerator._generate_serve_fn_multitask()`:

```python
# Current (broken):
self._raw_feature_spec = tf_transform_output.raw_feature_spec()  # ALL features

# Target:
self._retrieval_feature_spec = {  # BUYER features only
    k: v for k, v in tf_transform_output.raw_feature_spec().items()
    if k in BUYER_FEATURE_NAMES
}
self._ranking_feature_spec = tf_transform_output.raw_feature_spec()  # ALL features
```

Then use `_retrieval_feature_spec` in `serve()` and `_ranking_feature_spec` in `serve_ranking()`.

**Complexity**: The TFT layer (`transform_features_layer()`) may still expect all features internally. May need to pass dummy values for missing features inside the `serve()` function, or create separate TFT layers per signature.

### Phase 3: Product Feature Store (Effort: Medium)

**Goal**: Enable the two-stage pipeline by providing product feature lookups.

**Option A — PostgreSQL table** (simplest):
```sql
CREATE TABLE product_features (
    product_id BIGINT PRIMARY KEY,
    category VARCHAR(50),
    sub_category VARCHAR(100),
    -- add other product features as needed
);

-- Populate from BigQuery raw_data tables
INSERT INTO product_features
SELECT DISTINCT product_id, category, sub_category
FROM raw_data.transactions;
```

Then add a Django API endpoint:
```
GET /api/products/features/?ids=378243001001,378245001001,...
→ {
    "378243001001": {"category": "DRY", "sub_category": "ГОРІЛКА ЧИСТА"},
    "378245001001": {"category": "FRESH", "sub_category": "ПІЛЬЗНЕР"},
    ...
  }
```

**Option B — Embedded in the model** (zero-latency):
Store a product feature lookup table as `tf.Variable` tensors inside the serving model. The `serve()` function would return enriched results directly:
```python
# In serve(), after getting top-K product IDs:
product_categories = tf.gather(self.product_categories_table, top_indices)
product_sub_categories = tf.gather(self.product_sub_categories_table, top_indices)
return {
    'product_ids': recommended_products,
    'scores': top_scores,
    'categories': product_categories,
    'sub_categories': product_sub_categories,
}
```

This eliminates the need for an external feature store entirely but increases model size.

### Phase 4: Orchestration API (Effort: Medium)

**Goal**: A single `/recommend` endpoint that handles the full pipeline.

Build a thin Django API (or separate Cloud Run service) that orchestrates retrieval → enrichment → ranking:

```python
# ml_platform/serving/views.py

@api_view(['POST'])
def recommend(request, endpoint_id):
    """
    Full two-stage recommendation pipeline.

    Input:  {"customer_id": "120063316701", "top_k": 10}
    Output: {"recommendations": [{"product_id": "378243001001", "score": 97.9}, ...]}
    """
    endpoint = DeployedEndpoint.objects.get(id=endpoint_id)
    service_url = endpoint.service_url

    # 1. RETRIEVE — call serving_default
    buyer_features = get_buyer_features(request.data['customer_id'])
    retrieval_response = call_tf_serving(
        service_url, signature='serving_default', instances=[buyer_features]
    )
    candidate_ids = retrieval_response['product_ids'][0][:100]

    # 2. ENRICH — look up product features
    product_features = ProductFeature.objects.filter(
        product_id__in=candidate_ids
    ).values()

    # 3. RANK — call serve_ranking with enriched features
    ranking_instances = []
    for pid, features in product_features.items():
        instance = {**buyer_features, **features}
        ranking_instances.append(instance)

    ranking_response = call_tf_serving(
        service_url, signature='serve_ranking', instances=ranking_instances
    )

    # 4. SORT by ranking score
    results = sorted(
        zip(candidate_ids, ranking_response['predictions']),
        key=lambda x: x[1], reverse=True
    )

    return Response({
        'recommendations': [
            {'product_id': pid, 'score': score}
            for pid, score in results[:request.data.get('top_k', 10)]
        ]
    })
```

### Phase 5: Full Dataset Candidate Index (Effort: Low)

**Goal**: All products are retrievable, not just those in the eval split.

Modify `_generate_run_fn_multitask()` to build candidate embeddings from the full dataset:

```python
# Current:
candidates_dataset = _input_fn(eval_files, ...)

# Target:
all_files = fn_args.train_files + fn_args.eval_files
candidates_dataset = _input_fn(all_files, ...)
```

Or, for even better coverage, use a dedicated product catalog query that includes all active products regardless of whether they appeared in the training period.

### Phase 6: Production Hardening (Effort: High)

Long-term improvements for production readiness:

1. **API Key authentication** for the serving endpoint (as designed in `phase_endpoints.md`)
2. **Serving metrics collection** — request count, latency, error rate from Cloud Monitoring
3. **A/B testing** — traffic splitting between model versions on Cloud Run
4. **Already-purchased filtering** — exclude products the customer already bought
5. **Diversity injection** — ensure recommendations span multiple categories
6. **Fallback strategy** — graceful degradation when model endpoint is down (e.g., popular items)
7. **Caching** — cache retrieval results per customer for short TTL (5–15 min)

---

## 6. Prioritized Roadmap

| Priority | Phase | What | Effort | Impact |
|----------|-------|------|--------|--------|
| **P0** | 1 | Retrain with bug fixes (product IDs + raw JSON) | Low | Fixes critical bugs |
| **P1** | 3 | Product feature store (PostgreSQL or Firestore) | Medium | Enables re-ranking |
| **P1** | 4 | Orchestration API (`/recommend` endpoint) | Medium | Usable API |
| **P2** | 2 | Split feature specs per signature | Medium | Cleaner retrieval API |
| **P2** | 5 | Full dataset candidate index | Low | Better coverage |
| **P3** | 6 | Production hardening (auth, metrics, A/B) | High | Production readiness |

**Estimated timeline to a working two-stage pipeline**: Phases 1 + 3 + 4 = a usable end-to-end pipeline with correct product IDs, feature enrichment, and a single API endpoint.
