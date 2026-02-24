# Feature: Averaged Purchase History Embedding

**Date**: 2026-02-24
**Status**: Research / Design
**Related**: `docs/rank_prob_improve.md` (Section 6.3, Item 7)

---

## 1. Problem Statement

The current TFRS ranking model for predicting "probability to buy" (binary label) uses only per-row features: customer ID, product ID, categorical attributes (category hierarchy, brand, segment), and scalar numerics (sales, cust_value). The model has no way to know **what a buyer has purchased before** — it sees each (customer, product) pair in isolation.

Adding behavioral features like "customer purchase frequency per category" was considered, but the naive approach of creating one column per category (26 categories, 156 sub-categories, 706 sub-sub-categories) would blow up tower dimensions — especially with Google's recommended Bucketize+Embed preprocessing (+32D per column).

The averaged purchase history embedding solves this by encoding the buyer's entire purchase behavior into a **single fixed-width dense vector** (e.g., 32D) regardless of how many products or categories the buyer has purchased from.

---

## 2. Industry Sources and References

### 2.1 YouTube: Deep Neural Networks for Recommendations (Google, 2016)

**Paper**: Covington, Adams, Sargin. "Deep Neural Networks for YouTube Recommendations." RecSys 2016.
**URL**: https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/
**Full text**: https://cseweb.ucsd.edu/classes/fa17/cse291-b/reading/p191-covington.pdf

The foundational paper for two-tower recommendation architectures. YouTube's candidate generation model (the "user tower") takes these features as input, all concatenated:

1. **Watch history** — variable-length sequence of video IDs, each mapped to a learned embedding, then **averaged into a single fixed-width dense vector**
2. **Search history** — tokenized into unigrams/bigrams, embeddings averaged
3. **Geographic region** — embedded categorical
4. **Gender** — normalized to [0, 1]
5. **Age** — normalized to [0, 1]
6. **Logged-in state** — binary
7. **Example age** — scalar (training time offset; set to zero at serving)

Key quotes:
- "A user's watch history is represented as a variable-length sequence of sparse video IDs mapped to their dense embeddings. These embeddings are then averaged into a fixed-width vector."
- "Inspired by continuous bag of words language models, we learn high dimensional embeddings for each video in a fixed vocabulary and feed these embeddings into a feedforward neural network."
- Alternative aggregation methods (sum, component-wise max) were tested; **averaging performed best**.

The watch history embedding uses the **same embedding table** as the candidate (item) tower — this shared table is what makes the dot product between user and item embeddings meaningful.

**Architecture diagram** (from the paper):

```
Watch history IDs ──→ [Embed each] ──→ [Average] ──→ ┐
Search tokens ──────→ [Embed each] ──→ [Average] ──→ ├─→ [Concatenate] → Dense(ReLU) → Dense(ReLU) → User Embedding
Geographic region ──→ [Embed] ────────────────────→ │
Gender, Age ────────→ [Normalize] ────────────────→ │
Example age ────────→ ────────────────────────────→ ┘
```

### 2.2 Uber Eats: Two-Tower Embeddings (Uber, 2022)

**URL**: https://www.uber.com/blog/innovative-recommendation-applications-using-two-tower-embeddings/

Uber Eats applies the same pattern for food/restaurant recommendations:

- **Eater (user) tower**: Collects several months of previously ordered `store_id`s per eater, sorted by recency. These are embedded and averaged into a "BOW features" (Bag-of-Words) vector — a fixed-width representation of the eater's order history.
- This approach reduced model size by 20x compared to using raw eater_uuid embeddings, while partially addressing cold-start.
- The eater tower also includes contextual features: query time, order location.
- The store tower encodes: store ID, grocery items, geo-location, prices, ratings, delivery distance, menu text.

### 2.3 Snapchat Spotlight: Embedding-Based Retrieval (Snap, 2023)

**URL**: https://eng.snap.com/embedding-based-retrieval

Snapchat's two-tower model for content recommendation:

- **User tower**: Dense features (demographics, past engagement statistics) + sparse features (sequence lists of past engagement, processed with **average pooling** into fixed-width vectors).
- **Story tower**: Story metadata, creator features, content embeddings.
- Key design principle: "We should keep the features from each side independent from each other, since the embeddings generation should only include the information for just one type of entity."

### 2.4 Pinterest: PinnerSage Multi-Modal User Embeddings (Pinterest, 2020)

**URL**: https://www.researchgate.net/publication/343782799_PinnerSage_Multi-Modal_User_Embedding_Framework_for_Recommendations_at_Pinterest

Pinterest goes beyond simple averaging — they use clustering to create **multiple user interest vectors** (capturing that a user may have distinct interests like "cooking" and "travel"). However, the base approach remains: embed interacted items, aggregate into fixed-width user representation.

### 2.5 Common Pattern Across All Systems

Every production system follows the same recipe for the user tower:

| Feature Type | Examples | Encoding |
|---|---|---|
| **User ID** | customer_id | Learned embedding (captures individual taste) |
| **Averaged interaction history** | List of purchased product IDs | Embed each, average into fixed-width vector |
| **Demographics / static attributes** | Segment, region, age | Embedded categorical or normalized scalar |
| **Aggregate behavioral statistics** | Total purchases, days since last activity | Normalized scalar |

The averaged interaction history is the most impactful feature beyond the ID — it encodes **what kind of items** the user prefers, in the same embedding space as the items themselves.

---

## 3. How It Works

### 3.1 Core Concept

Every product in the model has a learned embedding — a 32D vector that encodes "what kind of product this is." Products in the same category cluster together in this embedding space.

For a buyer who purchased products P1 (Milk), P2 (Cheese), P3 (Yogurt), P4 (Beer), P5 (Bread):

```
Product embeddings (32D each, learned during training):
  P1 (Milk)      → [0.8, -0.2, 0.5, ...]   ← Dairy region
  P2 (Cheese)    → [0.7, -0.1, 0.6, ...]   ← Dairy region
  P3 (Yogurt)    → [0.9, -0.3, 0.4, ...]   ← Dairy region
  P4 (Beer)      → [-0.3, 0.7, 0.1, ...]   ← Drinks region
  P5 (Bread)     → [0.1, 0.2, 0.8, ...]    ← Bakery region

Average:         → [0.44, 0.06, 0.48, ...]  ← Buyer's "taste center"
```

This averaged vector sits in the **same embedding space** as products. A buyer who mostly buys Dairy gets a taste vector near the Dairy region. A diverse buyer gets a vector in the middle. The dot product between this taste vector and a candidate product's embedding naturally reflects affinity.

### 3.2 Shared Embedding Table

The critical architectural detail: the product embedding table is **shared** between both towers. The same `tf.keras.layers.Embedding` layer is used to:
1. Embed the candidate product in the product tower
2. Embed each product in the buyer's purchase history in the buyer tower

This shared table is what makes the system work — buyer history and candidate products live in the same vector space.

```
                    SHARED PRODUCT EMBEDDING TABLE
                    ┌─────────────────────────────┐
                    │ Embedding(vocab_size, 32)    │
                    │                              │
                    │ P1 → [0.8, -0.2, 0.5, ...]  │
                    │ P2 → [0.7, -0.1, 0.6, ...]  │
                    │ P3 → [0.9, -0.3, 0.4, ...]  │
                    │ ...                          │
                    └──────────┬──────────┬────────┘
                               │          │
              ┌────────────────┘          └──────────────┐
              ▼                                          ▼
    BUYER TOWER                                  PRODUCT TOWER
    ┌──────────────────────┐              ┌──────────────────┐
    │ customer_id → embed  │              │ product_id → embed│
    │                      │              │   (same table)    │
    │ purchase_history:    │              │                   │
    │   [P1, P2, P3, P4]  │              │ category → embed  │
    │   → lookup each      │              │ brand → embed     │
    │   → average → 32D   │              │ ...               │
    │                      │              └─────────┬─────────┘
    │ segment → embed      │                        │
    │ ...                  │                        │
    └─────────┬────────────┘                        │
              │                                     │
              ▼                                     ▼
         buyer_emb (32D)                  product_emb (32D)
              │                                     │
              └──────────── dot product ────────────┘
```

### 3.3 Why Averaging Works

Averaging seems crude (loses ordering, loses individual item identity), but it works because:

1. **Dense layers learn to interpret the average.** A vector near the Dairy region with high norm means "strong Dairy preference." Near the center means "diverse buyer."
2. **The embedding space is shaped by the averaging.** During training, the model learns to place products such that their averages are useful for prediction. Products in the same category are pushed together because that makes the averaged history more predictive.
3. **YouTube tested alternatives** — sum, component-wise max — averaging performed best. It's robust to different history lengths.
4. **The history vector is just one input.** It's concatenated with customer_id embedding (individual taste), segment, and other features. The dense layers combine all signals.

### 3.4 Handling Variable-Length Histories

Different buyers have different numbers of purchases. This is handled via padding + masking:

```python
# purchase_history is padded to max_length with 0s
history_ids = inputs['purchase_history']               # [batch, max_len]
history_embs = self.product_embedding(history_ids)     # [batch, max_len, 32]

# Mask out padding (0 = padding token)
mask = tf.cast(history_ids != 0, tf.float32)           # [batch, max_len]
mask = tf.expand_dims(mask, -1)                        # [batch, max_len, 1]

# Masked average: sum of real embeddings / count of real items
avg_history = tf.reduce_sum(history_embs * mask, axis=1)   # [batch, 32]
avg_history = avg_history / (tf.reduce_sum(mask, axis=1) + 1e-8)
```

A buyer with 3 purchases and a buyer with 50 purchases both produce a single 32D vector.

---

## 4. Implementation Plan for This System

### 4.1 Training Data (BigQuery SQL)

Add `purchase_history` as a BigQuery `ARRAY<INT64>` or `ARRAY<STRING>` column to the training views. Each row carries the buyer's full (or recent) purchase history:

```sql
-- Pre-compute purchase history per customer
-- Excludes the current row's product_id to avoid data leakage
customer_history AS (
  SELECT
    customer_id,
    ARRAY_AGG(DISTINCT product_id ORDER BY product_id LIMIT 50) AS purchase_history
  FROM `raw_data.tfrs_training_examples_v2_Ternopil`
  GROUP BY customer_id
)

-- Join to each training row
SELECT
  t.*,
  ch.purchase_history
FROM training_rows t
LEFT JOIN customer_history ch ON t.customer_id = ch.customer_id
```

**Leakage consideration**: For ranking model training rows, the `purchase_history` should exclude the current row's `product_id` to avoid leaking the label. This can be done with `ARRAY_REMOVE` or by filtering.

**History limit**: Cap at 50 most recent products (or all if fewer) to keep TFRecord sizes manageable.

### 4.2 TFX Pipeline: BigQueryExampleGen

BigQuery `ARRAY` columns are naturally serialized as variable-length features in TFRecords (`tf.io.VarLenFeature`). No changes needed to ExampleGen.

### 4.3 TFX Pipeline: Transform

The `preprocessing_fn` must apply the **same product vocabulary** to both `product_id` (single value) and `purchase_history` (array of values):

```python
def preprocessing_fn(inputs):
    outputs = {}

    # Single product_id → vocabulary index (existing pattern)
    outputs['product_id'] = tft.compute_and_apply_vocabulary(
        inputs['product_id'],
        vocab_filename='product_id_vocab'
    )

    # Purchase history → apply SAME vocabulary to each element
    outputs['purchase_history'] = tft.apply_vocabulary(
        inputs['purchase_history'],
        deferred_vocab_filename_tensor=
            tft.vocabulary('product_id_vocab')  # reuse same vocab
    )

    # ... other features unchanged
    return outputs
```

### 4.4 TFX Pipeline: Trainer

The Trainer module needs:
1. A shared `tf.keras.layers.Embedding` for product IDs
2. Averaging logic in the buyer tower
3. The shared embedding also used by the product tower

```python
class BuyerModel(tf.keras.Model):
    def __init__(self, product_embedding_layer, ...):
        super().__init__()
        self.shared_product_embedding = product_embedding_layer  # shared
        self.customer_embedding = tf.keras.layers.Embedding(...)
        # ... other feature embeddings
        self.dense_layers = tf.keras.Sequential([...])

    def call(self, inputs):
        features = []

        # Standard buyer features
        features.append(self.customer_embedding(inputs['customer_id']))

        # Averaged purchase history
        history_ids = inputs['purchase_history']
        history_embs = self.shared_product_embedding(history_ids)
        mask = tf.cast(history_ids != 0, tf.float32)
        mask = tf.expand_dims(mask, -1)
        avg_history = tf.reduce_sum(history_embs * mask, axis=1)
        avg_history = avg_history / (tf.reduce_sum(mask, axis=1) + 1e-8)
        features.append(avg_history)

        # ... other features (segment, target_group, etc.)

        return self.dense_layers(tf.concat(features, axis=-1))


class ProductModel(tf.keras.Model):
    def __init__(self, product_embedding_layer, ...):
        super().__init__()
        self.shared_product_embedding = product_embedding_layer  # same layer
        # ... other feature embeddings
        self.dense_layers = tf.keras.Sequential([...])

    def call(self, inputs):
        features = []
        features.append(self.shared_product_embedding(inputs['product_id']))
        # ... category, brand, etc.
        return self.dense_layers(tf.concat(features, axis=-1))


# In the main model:
shared_product_emb = tf.keras.layers.Embedding(product_vocab_size + OOV, 32)
buyer_model = BuyerModel(shared_product_emb, ...)
product_model = ProductModel(shared_product_emb, ...)
```

### 4.5 Inference / Serving

**Offline (periodic):**
- Run product tower for all ~990 products → store 990 vectors in ANN index (ScaNN/BruteForce)
- Materialize buyer purchase histories to a fast-access store

**Online (per buyer request):**
1. Fetch buyer's purchase history from BigQuery / Firestore / in-memory cache
2. Send to buyer tower:
   ```json
   {
     "customer_id": "C1",
     "segment": "Premium",
     "target_group": "HoReCa",
     "purchase_history": [15, 27, 33, 88]
   }
   ```
3. Buyer tower computes 32D embedding
4. ANN search against pre-computed product embeddings → top-100 recommendations

**History storage options:**

| Option | Latency | Fits the stack |
|---|---|---|
| BigQuery table (pre-computed) | ~1-2s | Yes — already use BQ everywhere |
| Firestore document per buyer | ~50ms | Yes — already have Firestore ETL |
| In-memory at startup | ~1ms | Works for ~1K buyers (B2B scale) |

---

## 5. Impact on Feature Config System

The current Feature Config system treats each feature as a single-value column assigned to a tower (buyer or product). Supporting averaged purchase history requires a new feature type:

| Change | Scope | Description |
|---|---|---|
| **New feature type: "History"** | Feature Config model + UI | A variable-length sequence of IDs that gets embedded and averaged |
| **Shared embedding concept** | TrainerModuleGenerator | The history feature must share its embedding table with the product tower's product_id embedding |
| **Transform generation** | PreprocessingFnGenerator | Must apply the same vocabulary to both the single product_id and the history array |
| **Dimension calculation** | FeatureConfig._calc_feature_dim() | History feature adds +embedding_dim to the buyer tower (e.g., +32D) |

This is a non-trivial extension but self-contained — the new feature type doesn't break existing features.

---

## 6. Dimension Impact

| Tower | Current (example) | With History | Change |
|---|---|---|---|
| Buyer | ~96D (IDs + categoricals) | ~128D | +32D (one averaged history vector) |
| Product | ~160D (IDs + categoricals) | ~160D | No change |

The buyer tower gains exactly **+embedding_dim** (e.g., +32D) regardless of how many products are in the history. This is the key advantage over per-category columns.

---

## 7. Open Questions

1. **History scope**: Should `purchase_history` include all-time purchases or only recent N months? YouTube uses "recent" history — recency-weighted or capped.

2. **Deduplication**: Should the history contain unique product IDs, or should repeated purchases of the same product appear multiple times (giving them more weight in the average)?

3. **Leakage handling**: For ranking training rows, the history must exclude the current row's product_id. For retrieval training, this may be less critical since negatives are sampled.

4. **Cold-start buyers**: Buyers with no purchase history get a zero or mean-initialized vector. The model should learn to rely on other features (segment, target_group) for these buyers.

5. **History for negative samples**: Negative (customer, product) pairs get the same customer history as positive pairs — the customer's purchase history is a buyer-level feature, independent of the candidate product.

6. **TrainerModuleGenerator changes**: The code generator needs to handle the shared embedding pattern. This is the most significant engineering change.

---

## 8. Next Steps

1. **Prototype SQL**: Create a v3 training view with `purchase_history` ARRAY column for Ternopil data
2. **Manual trainer module**: Write a trainer_module.py manually (not auto-generated) that implements the shared embedding + averaging pattern, to validate the approach with a Quick Test
3. **Evaluate**: Compare RMSE/AUC-ROC with and without purchase history on the ranking model
4. **If successful**: Extend the Feature Config system and TrainerModuleGenerator to support the new "History" feature type

---

## Appendix A: Alternative Approaches Considered

### A.1 Per-Category Distribution Vector (+26D)

Compute purchase proportion per category as 26 FLOAT columns. Values in [0, 1], sum to 1.0.

- **Pros**: Simple, fits current Feature Config system, no code changes
- **Cons**: Fixed to one hierarchy level; doesn't capture which specific products were purchased; grows linearly with category count; sub-category level (156, 706 columns) is impractical

### A.2 Top-K Categories per Buyer

Encode buyer's top 3-5 most purchased categories as text features with embeddings.

- **Pros**: Fixed-size, fits current system, captures dominant preferences
- **Cons**: Loses information about non-top categories; arbitrary K; doesn't capture product-level preferences

### A.3 Pre-Computed Embeddings from Previous Model

Train model v1 without history, extract product embeddings, pre-compute averaged vectors per buyer in BigQuery, use as frozen 32D features in model v2.

- **Pros**: Simpler than end-to-end shared embeddings; works with current Feature Config (32 FLOAT columns)
- **Cons**: Embeddings are frozen (not updated during training); requires a trained model to bootstrap from; two-stage training process

### A.4 Averaged Purchase History (Selected Approach)

End-to-end shared embedding table with variable-length history input.

- **Pros**: Embeddings learned jointly with the rest of the model; single fixed-width vector regardless of history size; proven at scale (YouTube, Uber, Snapchat, Pinterest); captures product-level preferences, not just category-level
- **Cons**: Requires extending Feature Config system; more complex Transform/Trainer code generation; variable-length input handling

---

## Appendix B: File References

| File | Relevance |
|---|---|
| `sql/create_ternopil_prob_train_v2_view.sql` | Current training view — needs `purchase_history` column |
| `sql/create_ternopil_prob_test_v2_view.sql` | Current test view — same change |
| `ml_platform/configs/services.py` | PreprocessingFnGenerator + TrainerModuleGenerator — need extensions |
| `ml_platform/models.py` | FeatureConfig model — needs "History" feature type |
| `templates/ml_platform/model_configs.html` | Feature Config UI — needs History feature option |
| `docs/rank_prob_improve.md` | Related: ranking model improvement tracking |
| `past/recommenders.ipynb` | Reference: basic TFRS retrieval with TFX |
| `past/ranking_tfx.ipynb` | Reference: TFRS ranking with TFX |
| `past/multitask.ipynb` | Reference: TFRS multitask model |
