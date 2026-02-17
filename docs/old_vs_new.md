# Old System vs. New Platform: Benefits of Switching

## Document Purpose
This document provides a comprehensive comparison between the legacy client-specific TFRS implementation (Metro Ukraine recommender) and the new B2B Recommendation SaaS Platform, highlighting the benefits of switching for prospective clients.

**Last Updated**: 2026-02-17

---

## Executive Summary

The legacy system was a production-grade but rigid single-purpose recommender: one model type (retrieval), 8 hardcoded features, manual Python development for any change, and monthly retraining via Airflow. The new platform transforms this into a configurable, no-code SaaS product supporting three model types, unlimited features, visual experiment-driven development, and automated production pipelines on Vertex AI.

---

## 1. From One Model Type to Three

**Old system:** Retrieval only (two-tower with brute-force nearest neighbor).

**New system:**

| Model Type | What It Does | Business Value |
|---|---|---|
| **Retrieval** | Finds candidate items from the full catalog | Same as before, but now with ScaNN for 10K+ catalogs |
| **Ranking** | Scores and re-ranks candidates with a configurable rating head | Predicts actual business metrics (revenue, quantity, rating) — not just similarity |
| **Multitask (Hybrid)** | Single model that does both retrieval AND ranking with tunable loss weights | Best of both worlds — one model, two objectives, shared embeddings for transfer learning |

The ranking model alone is a major differentiator. Instead of just answering *"which products are similar to what this buyer purchased,"* it can answer *"how much revenue will this buyer generate from this product"* — a much more actionable signal.

### Multitask Architecture

```
Shared Input Features
    │
    ├─► [BuyerModel + Dense Layers] → Query Embedding
    ├─► [ProductModel + Dense Layers] → Candidate Embedding
    │
    ├─► RETRIEVAL TASK ── Dot Product (Similarity) ── Loss_retrieval
    ├─► RANKING TASK ──── Concatenate + Rating Head → Scalar ── Loss_ranking
    │
    └─► Total Loss = w_retrieval × Loss_retrieval + w_ranking × Loss_ranking
```

A single model can simultaneously optimize for "find relevant products" (retrieval) AND "predict revenue" (ranking), with tunable weights to balance exploration vs. exploitation. This is the architecture used by major recommendation systems at scale.

---

## 2. Dramatically Expanded Feature Engineering

### Old System Features (8 total, hardcoded)

| Feature | Tower | Processing |
|---|---|---|
| customer_id | Query | StringLookup → Embedding(64D) |
| city | Query | StringLookup → Embedding(16D) |
| revenue | Query | Discretization(1000 buckets) → Embedding(32D) + Normalization(1D) |
| timestamp | Query | Discretization(120 buckets) → Embedding(32D) + Linear + Cyclical(8D) |
| product_id | Candidate | StringLookup → Embedding(32D) |
| art_name | Candidate | Not used in model (metadata only) |
| stratbuy_domain_desc | Candidate | StringLookup → Embedding(16D) |
| mge_main_cat_desc | Candidate | StringLookup → Embedding(24D) |
| customer×city cross | Query | Hash(5000 bins) → Embedding(16D) |
| revenue×time cross | Query | Hash(3000 bins) → Embedding(12D) |

**Total input dimensions:** Query tower: 173D, Candidate tower: 72D.

### New System Features (unlimited, configurable per deployment)

| Capability | Old | New |
|---|---|---|
| Feature count | 8 fixed | Unlimited — any column from BigQuery |
| String features | Fixed embedding dims | Per-feature: embedding_dim, max_vocabulary_size, oov_buckets, min_frequency |
| Numeric features | Discretization only | Normalization (z-score, min-max, log), Bucketization, Outlier clipping |
| Temporal features | Manual sin/cos (4 cycles) | Auto cyclical encoding (annual, quarterly, monthly, weekly, daily) |
| Cross features | 2 hardcoded | Auto-suggested + unlimited custom crosses with configurable hash buckets |
| Feature assignment | Fixed buyer/product split | Drag-and-drop assignment to Query or Candidate tower |
| Target column | N/A (retrieval only) | Any numeric column for ranking (revenue, quantity, margin, rating) |
| Semantic type inference | Manual | Automatic — system detects IDs, categories, dates, cyclical, numeric |

This means clients can bring **any data they have** — purchase quantities, margins, customer segments, product attributes, seasonal flags, geographic data — and the platform builds the right feature pipeline automatically.

---

## 3. No-Code Configuration vs. Python Development

**Old system:** Every change required modifying Python code in 4 separate modules (data_extractor, vocab_builder, trainer, cloud_run_service), rebuilding Docker images, and updating Airflow DAGs.

**New system:**

| Task | Old Approach | New Approach |
|---|---|---|
| Add a feature | Edit Python code in 4 files | Drag-and-drop in UI |
| Change model architecture | Edit trainer code, rebuild Docker | Visual tower builder with 5 presets |
| Adjust hyperparameters | Edit DAG config, redeploy | Wizard form with auto-suggestions |
| Change data source | Edit BigQuery SQL, rebuild extractor | ETL wizard (7 source types) |
| Try a different model type | Build entirely new codebase | Select from dropdown (Retrieval/Ranking/Multitask) |
| Schedule retraining | Edit Airflow DAG cron | UI scheduler (hourly/daily/weekly/monthly) |

### Supported Data Sources (New)

| Type | Examples |
|---|---|
| SQL Databases | PostgreSQL, MySQL, BigQuery (cross-project + public datasets) |
| NoSQL Databases | Firestore (with automatic schema inference) |
| Cloud Storage | GCS, S3, Azure Blob Storage |
| File Formats | CSV, Parquet, JSON/JSONL |

---

## 4. Experiment-Driven Model Development

**Old system:** No experimentation framework. You trained a model, evaluated manually, and hoped for the best. Recall@100 = 47% was the only metric ever tracked.

**New system:**

- **Quick Test pipeline** — validate any configuration on a sample before committing to full training
- **Experiment dashboard** — compare 2-4 experiments side-by-side
- **Hyperparameter insights** — TPE-based analysis showing which LR, batch size, and epoch values correlate with top 30% results
- **Suggested experiments** — AI-powered gap detection recommending what to try next
- **Training heatmaps** — epoch-by-experiment loss visualization
- **Dataset performance comparison** — compare results across different datasets

### Metrics Per Model Type

| Model Type | Tracked Metrics |
|---|---|
| Retrieval | Recall@5, Recall@10, Recall@50, Recall@100 |
| Ranking | RMSE, MAE, Test RMSE, Test MAE |
| Multitask | All 8 metrics simultaneously |

---

## 5. Neural Architecture Configurability

**Old system:** Fixed 128→64→32 dense layers in both towers. Fixed L1 regularization at 0.02. Adam optimizer only.

**New system:**

| Parameter | Old | New |
|---|---|---|
| Layer types | Dense only | Dense, Dropout, BatchNorm, LayerNorm |
| Regularization | L1 = 0.02 global | L1, L2, L1+L2 per-layer, configurable |
| Optimizers | Adam only | Adagrad, Adam, SGD, RMSprop, AdamW, FTRL |
| Tower presets | None | Minimal (64→32), Standard (128→64→32), Deep (256→128→64→32), Asymmetric, Regularized |
| Layer reordering | Not possible | Drag-and-drop |
| Rating head | N/A | Fully configurable dense/dropout/batchnorm stack |
| Retrieval algorithm | Brute-force only | Brute-force + ScaNN (for 10K+ product catalogs) |
| Loss functions | Fixed retrieval loss | MSE, Binary Crossentropy, Huber (for ranking/multitask) |

### Tower Architecture Example (Visual Builder)

```
Query Tower (Buyer):                    Candidate Tower (Product):
┌─────────────────────┐                ┌─────────────────────┐
│ Input Features      │                │ Input Features      │
│ (configurable)      │                │ (configurable)      │
├─────────────────────┤                ├─────────────────────┤
│ Dense(256, ReLU)    │                │ Dense(128, ReLU)    │
│ L2 reg: 0.01        │                │ L2 reg: 0.01        │
├─────────────────────┤                ├─────────────────────┤
│ BatchNorm           │                │ Dropout(0.2)        │
├─────────────────────┤                ├─────────────────────┤
│ Dense(128, ReLU)    │                │ Dense(64, ReLU)     │
├─────────────────────┤                ├─────────────────────┤
│ Dropout(0.3)        │                │ Dense(32) [output]  │
├─────────────────────┤                └─────────────────────┘
│ Dense(64, ReLU)     │
├─────────────────────┤
│ Dense(32) [output]  │
└─────────────────────┘
```

---

## 6. Production-Grade Training & Deployment Pipeline

### Old System: 4-Stage Airflow DAG

```
Data Extraction (Dataflow) → Vocabulary Building → GPU Training → Cloud Run Deploy
```

- Monthly execution only (2nd day of month)
- No model evaluation or blessing
- No model registry
- Manual Cloud Run deployment
- No artifact tracking beyond GCS

### New System: 8-Stage TFX Pipeline on Vertex AI

```
Compile → ExampleGen → StatisticsGen → SchemaGen → Transform → Trainer → Evaluator → Pusher
```

| Capability | Old | New |
|---|---|---|
| Pipeline orchestration | Airflow on GCE | Vertex AI Pipelines (managed, serverless) |
| Data validation | None | TFDV statistics, schema validation, data quality scoring |
| Model evaluation | Manual | Automated blessing with configurable thresholds |
| Model registry | None | Vertex AI Model Registry with native versioning |
| Deployment | Manual Cloud Run | One-click deploy to Vertex AI or Cloud Run |
| GPU training | Custom VM setup | Pre-built GPU container (TF 2.15.1 + CUDA 12.2 + ScaNN) |
| Scheduling | Monthly Airflow cron | Hourly/daily/weekly/monthly via Cloud Scheduler |
| Artifact tracking | GCS only | ML Metadata + GCS with lifecycle policies |
| Retraining | Rebuild entire pipeline | Click "Rerun" or set a schedule |
| Deployment status | Database field (stale) | Dynamic query from Vertex AI endpoint (single source of truth) |

### Automated Model Lifecycle

```
Quick Test (validate) → Full Training (GPU) → Evaluator (bless/reject) → Pusher (register) → Deploy (one-click)
```

---

## 7. Scalable Multi-Tenant Architecture

**Old system:** Single-tenant. One GCP project, one model, one client (Metro Ukraine). Hardcoded BigQuery queries, city filters, and product scope (top 2,000 products only).

**New system:**

| Aspect | Old | New |
|---|---|---|
| Tenancy | Single-tenant | Multi-tenant SaaS (isolated GCP project per client) |
| Data sources | 1 BigQuery dataset | 7 source types (PostgreSQL, MySQL, BigQuery, Firestore, GCS, S3, Azure) |
| Product scope | Top 2,000 by revenue | Any catalog size (ScaNN for 10K+) |
| Geographic scope | 19 Ukrainian cities (hardcoded) | Any geography, configurable filters |
| Customer scope | SCO target group, 3+ products | Configurable filters (revenue %, min transactions, segments) |
| Data freshness | 90-day fixed window | Configurable rolling window or fixed start date |
| ETL | Custom Apache Beam | Managed ETL with Dataflow for 1M+ rows |
| Infrastructure | Shared resources | Complete isolation per client |

### Shared Infrastructure

```
b2b-recs-platform (Central)          Client Projects (Isolated)
┌────────────────────────────┐      ┌─────────────┐ ┌─────────────┐
│ Artifact Registry          │      │ client-a    │ │ client-b    │
│ └── tfx-compiler:latest ◄──┼──────┤ Cloud Build │ │ Cloud Build │
│     (shared image)         │      │ Vertex AI   │ │ Vertex AI   │
└────────────────────────────┘      └─────────────┘ └─────────────┘
```

The shared TFX compiler image reduces pipeline compilation from 12-15 minutes to 1-2 minutes per client.

---

## 8. New Variables Available for Model Building

For clients considering the switch, here are concrete examples of what they can now leverage:

### Ranking Model Use Cases

| Use Case | Target Variable | Loss Function | Business Value |
|---|---|---|---|
| Revenue prediction | revenue per product per buyer | MSE | Optimize for total basket value |
| Purchase probability | buy/no-buy label | Binary Crossentropy | Predict conversion likelihood |
| Order quantity | units ordered | MSE or Huber | Optimize replenishment recommendations |
| Margin optimization | profit margin | MSE | Recommend high-margin products |

### New Feature Types Clients Can Leverage

| Feature | Type | Processing | Example Use |
|---|---|---|---|
| Customer segments | String embedding | Configurable dim + vocab | Enterprise/SMB/startup classification |
| Product margins | Numeric | Normalization or bucketization | Optimize for profitability |
| Order frequency | Numeric | Bucketization with embeddings | Distinguish weekly vs. monthly buyers |
| Seasonal indicators | Cyclical | Auto sin/cos encoding | Capture annual/quarterly patterns |
| Geographic hierarchies | String + crosses | Embedding + region×category cross | Location-specific preferences |
| Price sensitivity | Numeric | Z-score normalization | Discount responsiveness as signal |
| Inventory levels | Numeric | Normalization | Factor availability into recommendations |
| Customer lifetime value | Numeric | Log transform + normalization | Weight high-value customer preferences |
| Product age/freshness | Temporal | Cyclical encoding | New vs. established product behavior |
| Category affinity scores | Numeric | Bucketization | Pre-computed customer-category match |

### Cross Feature Examples

| Cross | Hash Buckets | Business Logic |
|---|---|---|
| customer_segment × product_category | 5,000 | Segment-specific category preferences |
| region × season | 1,000 | Regional seasonal patterns |
| price_tier × customer_segment | 2,000 | Price sensitivity by segment |
| product_category × day_of_week | 500 | Category-specific ordering patterns |
| customer_id × product_category | 10,000 | Individual category affinities |

---

## 9. Serving and Deployment Improvements

### Old System Serving

- **Single serving mode:** Brute-force nearest neighbor over 1,460 pre-computed product embeddings
- **Fixed input signature:** customer_id, city, revenue, timestamp (4 inputs)
- **Single output:** Top-100 product IDs + similarity scores
- **Deployment:** Manual Cloud Run with FastAPI wrapper
- **Batch processing:** Up to 1,000 customers, chunked at 100 for memory

### New System Serving

| Model Type | Input | Output | Serving Class |
|---|---|---|---|
| Retrieval (Brute Force) | Buyer features only (dynamic) | Top-K product IDs + scores | ServingModel |
| Retrieval (ScaNN) | Buyer features only (dynamic) | Top-K products via approximate NN | ScaNNServingModel |
| Ranking | Buyer + Product features (dynamic) | Predicted score + normalized score | RankingServingModel |
| Multitask | Dual signatures | Retrieval OR ranking on demand | MultitaskServingModel |

**Multitask serving workflow:**
1. Call `serve()` — retrieval signature returns top-K candidates
2. Call `serve_ranking()` — ranking signature scores specific buyer-product pairs
3. Combine for final recommendations

**Ranking inverse transform:** Predictions are automatically converted back to original scale (reversing log, normalization) — no manual post-processing needed.

---

## 10. Summary: Top-Line Benefits

| # | Benefit | Impact |
|---|---|---|
| 1 | **3x model types** — retrieval, ranking, and hybrid | Move beyond similarity to predict actual business metrics |
| 2 | **Unlimited features** — any column from any data source | Leverage all available data, not just 8 hardcoded fields |
| 3 | **Zero code required** — visual UI replaces 4 Python modules + DAGs | Business users can operate without engineering support |
| 4 | **Experiment before you commit** — quick test, compare, iterate | Data-driven model selection instead of guesswork |
| 5 | **Automated evaluation** — model blessing prevents bad deploys | No more manual validation of model quality |
| 6 | **Flexible scheduling** — hourly to monthly retraining | React to data changes at the right cadence |
| 7 | **ScaNN for scale** — fast approximate NN for large catalogs | Scale beyond 2,000 products to 100K+ |
| 8 | **Ranking predictions** — predict revenue, quantity, probability | Actionable business signals, not just similarity scores |
| 9 | **Multi-tenant ready** — isolated deployment per client | Serve multiple clients from one platform |
| 10 | **Full artifact lineage** — TFDV, schema validation, ML Metadata | Production-grade ML governance and reproducibility |
