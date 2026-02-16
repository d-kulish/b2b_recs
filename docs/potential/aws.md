# Why This System Cannot Be Replicated on AWS ML Platforms

## Document Purpose

This document provides detailed technical arguments for why the B2B Recommendation SaaS platform cannot be meaningfully ported to or replicated on AWS. It is intended as a reference for client negotiations where the prospect uses AWS and questions why the system runs on GCP.

**Last Updated**: 2026-02-16

---

## Executive Summary

This platform is built on three Google-created technologies that have no AWS equivalents: **TFX** (TensorFlow Extended), **TFRS** (TensorFlow Recommenders), and **ScaNN** (Scalable Nearest Neighbors). These are not interchangeable cloud services -- they are deeply integrated open-source frameworks designed to run on GCP infrastructure. The closest AWS alternative, Amazon Personalize, is a fundamentally different product: a black-box managed service with severe limitations on model customization, feature engineering, and data structure.

---

## 1. Replicating System Complexity on AWS

### 1.1 The Technology Stack Is GCP-Native

The platform relies on a chain of tightly coupled components, each with deep GCP integration:

```
BigQuery ──→ BigQueryExampleGen ──→ StatisticsGen ──→ SchemaGen ──→ Transform ──→ Trainer ──→ Evaluator ──→ Pusher
   │              (TFX)              (TFDV/Beam)      (TFDV)      (tf.Transform   (TFRS)      (TFMA)       (Vertex AI
   │                                                                /Dataflow)                              Registry)
   GCP only       GCP only           Dataflow          Local       Dataflow        Vertex AI    Local        GCP only
```

On AWS, every component marked "GCP only" or "Dataflow" would need to be replaced. There are no drop-in substitutes.

### 1.2 Component-by-Component Migration Assessment

| Component | AWS Equivalent | Migration Effort | Gap |
|---|---|---|---|
| **TFX Pipeline Framework** | No equivalent | Massive rewrite | SageMaker Pipelines cannot orchestrate TFX |
| **Vertex AI Pipelines** | SageMaker Pipelines | Massive rewrite | Different DSL, no TFX support |
| **BigQueryExampleGen** | None | Custom development | No RedshiftExampleGen or AthenaExampleGen exists in TFX |
| **tf.Transform on Dataflow** | Beam on Flink/EMR | Large effort, compatibility risks | Dataflow is proprietary; Flink runner poorly tested with TFX |
| **StatisticsGen (TFDV)** | Custom processing | Moderate | No TFDV equivalent on AWS |
| **ScaNN** (in-model ANN) | External services (FAISS, OpenSearch) | Moderate | AWS alternatives are external services, not embedded TF layers |
| **Cloud Build + Artifact Registry** | CodeBuild + ECR | Moderate | Infrastructure is similar; pipeline compilation scripts need rewriting |
| **TF Serving on Cloud Run** | TF Serving on ECS/SageMaker | Moderate | Same TF Serving technology, different hosting |
| **Cloud SQL / Secret Manager / Scheduler** | RDS / Secrets Manager / EventBridge | Trivial | Standard infrastructure with direct equivalents |

### 1.3 No TFX Orchestrator for SageMaker

TFX supports the following production orchestrators:

- `KubeflowV2DagRunner` -- **Vertex AI Pipelines (GCP only)**
- `KubeflowDagRunner` -- Kubeflow on Kubernetes (requires self-managed K8s cluster)
- `AirflowDagRunner` -- Apache Airflow (portable, but no native TFX component support for AWS services)
- `BeamDagRunner` -- Apache Beam (limited to local/Dataflow runners in practice)

There is **no `SageMakerDagRunner`**. Google has never built one. No maintained third-party implementation exists. SageMaker Pipelines use a proprietary step-based DSL (`ProcessingStep`, `TrainingStep`, `RegisterModel`) that is architecturally incompatible with TFX's component/channel/artifact system.

The only viable path to run TFX on AWS is deploying Kubeflow Pipelines on Amazon EKS (Elastic Kubernetes Service), which requires managing a Kubernetes cluster -- eliminating the benefit of managed ML infrastructure.

### 1.4 Dataflow Has No AWS Equivalent

Apache Beam (the framework TFX uses for distributed data processing) was created by Google. The only fully managed, production-grade Beam runner is Google Cloud Dataflow.

AWS alternatives for running Apache Beam:

| AWS Service | Beam Support | Problem |
|---|---|---|
| AWS Glue | None | Spark-based, no Beam runner |
| Amazon EMR (Spark) | SparkRunner | Poorly tested with tf.Transform; requires TensorFlow on all Spark workers |
| Amazon Managed Flink | FlinkRunner | Poorly tested with TFX workloads; requires significant infrastructure setup |
| Direct processing | DirectRunner | Single-machine only, does not scale beyond ~1M rows |

TFX's `Transform` and `StatisticsGen` components depend on Beam internally. Without a reliable Beam runner, these components either cannot run at scale or require untested configurations with known compatibility risks.

### 1.5 BigQueryExampleGen Has No AWS Counterpart

The platform uses `BigQueryExampleGen` to read training data directly from BigQuery via SQL, convert to TFRecords, and apply train/eval splitting -- all in a single TFX component.

TFX provides no equivalent for AWS data sources:

- No `RedshiftExampleGen`
- No `AthenaExampleGen`
- No `S3ExampleGen` for structured data

Workarounds (writing a custom `ExampleGen` by subclassing `QueryBasedExampleGen`) require handling query splitting, TFRecord serialization, MLMD artifact registration, and train/eval split logic -- a non-trivial development effort.

### 1.6 Estimated Replication Cost

| Item | Effort | Cost |
|---|---|---|
| Rewrite TFX pipeline in SageMaker Pipelines | 3-4 months, 2 senior ML engineers | $150-200K |
| Build custom data ingestion (replace BigQueryExampleGen) | 1-2 months | $50-80K |
| Replicate tf.Transform preprocessing embedding | 2-3 months (research + implementation) | $100-150K |
| Build UI for model configuration (feature engineering, model structure, experiments) | 4-6 months, 2 full-stack developers | $200-300K |
| Build experiment tracking dashboard | 2-3 months | $80-120K |
| Build ETL system with 7 source types | 2-3 months | $80-120K |
| Testing, integration, deployment | 2-3 months | $80-120K |
| **Total** | **12-18 months** | **$740K - $1.1M** |

---

## 2. Limitations of Amazon Personalize

Amazon Personalize is AWS's managed recommendation service. It is a fundamentally different product from this platform -- a black-box API service versus a configurable ML pipeline system.

### 2.1 Black-Box Architecture

Users select a "recipe" (pre-built algorithm) and have no control over:

- Model architecture (no two-tower customization)
- Layer configuration (no Dense, Dropout, BatchNorm choices)
- Embedding dimensions (not configurable per feature)
- Optimizer selection (no Adagrad/Adam/SGD/etc. choice)
- Loss functions (not configurable)
- Learning rate, regularization, or any hyperparameter beyond what Amazon exposes

**This platform** provides full transparency: visual tower architecture builder, configurable layers per tower, 6 optimizers, adjustable embedding dimensions based on cardinality, and three model types (retrieval, ranking, multitask).

### 2.2 Severe Data Structure Limitations

| Constraint | Amazon Personalize | This Platform |
|---|---|---|
| **Interactions metadata fields** | Max 5 custom fields | Unlimited columns from BigQuery |
| **Data format** | Flat CSV only, Avro schema | Any BigQuery table structure |
| **Nested data** | Not supported | Supported via BigQuery |
| **Feature engineering** | Mark as `categorical` or `textual` only | 6 processing types: embedding, normalization (z-score/min-max/log), bucketization, cyclical encoding, cross features |
| **Feature crosses** | Not available | Configurable hash bucket crosses |
| **Supported types** | string, int, long, float, double, boolean | All BigQuery types with automatic type mapping |

A typical B2B transaction has 15-30 relevant features (customer segment, region, sales channel, order type, payment terms, product category hierarchy, seasonal flags, contract tier, etc.). With Personalize's 5-field limit on interactions, most of this signal must be discarded.

### 2.3 No Multi-Task Learning

Amazon Personalize requires separate models for retrieval and ranking:

- `User-Personalization-v2` for retrieval (returns recommended items)
- `Personalized-Ranking-v2` for ranking (re-ranks a provided list)

These are separate campaigns, separate endpoints, separate billing. There is no way to train a single model that optimizes both objectives simultaneously.

**This platform** supports multitask models that combine retrieval and ranking in a single model with configurable loss weights, providing better training signal and a unified serving endpoint.

### 2.4 ID-Based Inference vs. Feature-Based Inference

**Amazon Personalize inference** requires sending a user ID:

```json
{
  "campaignArn": "arn:aws:personalize:...:campaign/my-campaign",
  "userId": "user-123",
  "numResults": 25
}
```

The model looks up pre-indexed user data from the last training run. If a customer's profile has changed since training (new contract tier, different purchasing pattern, updated revenue), the model still uses stale data.

**This platform's inference** accepts raw feature values:

```json
{
  "instances": [
    {"customer_id": "C001", "city": "Warsaw", "segment": "Enterprise", "revenue": 500000}
  ]
}
```

The model processes current feature values at query time via the embedded tf.Transform graph. If a customer's revenue changed from $50K to $500K since last training, the model factors it in immediately. This matters in B2B where customer profiles evolve (new contracts, seasonal purchasing, budget cycles).

### 2.5 No Model Export

Models trained in Amazon Personalize cannot be exported. You cannot:

- Inspect the model architecture
- Deploy it outside of AWS
- Run it in a custom serving environment
- Audit the model for regulatory compliance
- Migrate to another platform

**This platform** produces standard TensorFlow SavedModels that can be deployed anywhere TF Serving runs -- including on the client's own AWS infrastructure (ECS, SageMaker endpoints).

### 2.6 Pricing at Scale

Amazon Personalize charges per request: **$0.15 per 1,000 recommendations**.

| Volume | Daily Requests | Monthly Personalize Cost | Monthly Platform Cost (Cloud Run) |
|---|---|---|---|
| Small | 10K/day | ~$45 | ~$20-40 |
| Medium | 100K/day | ~$450 | ~$30-80 |
| Large | 1M/day | ~$4,500 | ~$150-500 |

At scale, per-request pricing grows linearly. Container-based serving (Cloud Run or ECS) has better unit economics because one container handles thousands of requests per second. Additionally, Personalize enforces a minimum 1 TPS charge even with zero traffic; Cloud Run scales to zero.

---

## 3. Training-Serving Skew

Training-serving skew is the #1 cause of silent ML model degradation in production. It occurs when the data transformations applied during training differ from those applied during inference.

### 3.1 What Training-Serving Skew Looks Like

**Vocabulary ordering mismatch:**

Training builds vocabulary:
```
"Enterprise" → 0, "SMB" → 1, "Startup" → 2
```

Serving loads a regenerated vocabulary after retraining with new data:
```
"Enterprise" → 0, "Mid-Market" → 1, "SMB" → 2, "Startup" → 3
```

"SMB" now maps to index 2 instead of 1. The embedding layer returns the wrong vector. Every recommendation for SMB customers is silently wrong. No error is raised.

**Normalization statistics drift:**

Training computed z-score: `mean=50000, std=30000`
Serving uses stale hardcoded values or recomputes from a different sample: `mean=55000, std=35000`

A customer with revenue 80,000:
- Training saw: `(80000 - 50000) / 30000 = 1.0`
- Serving computes: `(80000 - 55000) / 35000 = 0.71`

The model receives a different number than what it learned from. Recommendations degrade silently.

**Other common skew sources:**
- Missing value handling divergence (`fillna(0)` vs `fillna(mean)`)
- Feature crossing inconsistency (different hash functions or bucket counts)
- Type coercion differences (int vs float rounding)
- Code changes in one path but not the other

### 3.2 Why Skew Is Dangerous

1. **Silent.** The model still returns recommendations. No exceptions, no 500 errors. Just worse results.
2. **Hard to detect.** A/B tests might catch it weeks later. Or the business sees a gradual 5-10% revenue decline and blames "model quality."
3. **Compounds over time.** Each retraining cycle can introduce new subtle mismatches.
4. **Universal.** Google, Uber, Airbnb, and Netflix have all published papers about fighting this problem.

### 3.3 The Standard AWS Pattern (Without tf.Transform)

On AWS with SageMaker, the typical pattern requires maintaining preprocessing code in two separate places:

```
Training:   Redshift → PySpark preprocessing → Parquet/CSV → SageMaker Training Job
                         ↑
                     Code version A (updated monthly)

Serving:    REST API → Lambda/Python preprocessing → SageMaker Endpoint
                         ↑
                     Code version B (updated... when someone remembers)
```

Two completely separate codebases doing "the same" transformations. Maintained by different people, updated at different times. The training pipeline runs monthly; the serving code was last updated 6 months ago. Nobody notices the drift.

---

## 4. Benefits of tf.Transform

### 4.1 How tf.Transform Eliminates Skew

tf.Transform creates a TensorFlow graph for all preprocessing operations (vocabulary generation, normalization, feature crossing, bucketization). This graph is **embedded directly into the SavedModel**.

```
Raw JSON input → [tf.Transform Graph (inside SavedModel)] → [Model Weights] → Predictions
```

The exact same code that computed vocabulary indices and normalization statistics during training is literally baked into the serving artifact. At inference time, there is no separate preprocessing step. Raw data goes in, predictions come out.

It is **mathematically impossible** for the training and serving transformations to differ.

### 4.2 Preprocessing Operations Embedded in the Model

The platform's `PreprocessingFnGenerator` creates a `preprocessing_fn` that uses these tf.Transform operations, all of which become part of the serving model:

| Operation | tf.Transform Function | What It Does |
|---|---|---|
| Vocabulary encoding | `tft.compute_and_apply_vocabulary()` | Maps strings to integer indices (e.g., "Enterprise" → 0) |
| Z-score normalization | `tft.scale_to_z_score()` | Normalizes using training-set mean and std |
| Min-max normalization | `tft.scale_to_0_1()` | Scales to [0, 1] range using training-set min/max |
| Log normalization | `tf.math.log1p()` | Applies log(1+x) transform |
| Bucketization | `tft.bucketize()` | Converts continuous values to bucket indices |
| Feature crossing | `tf.sparse.cross_hashed()` | Creates interaction features with hash buckets |
| Cyclical encoding | `tf.math.sin()` / `tf.math.cos()` | Encodes temporal features (hour, day of week, month) |

### 4.3 What This Means for Inference

**With tf.Transform (this platform):**

The client sends raw, unprocessed values:
```json
{
  "instances": [{
    "customer_id": "C001234",
    "city": "Warsaw",
    "segment": "Enterprise",
    "total_revenue": 80000.0,
    "last_order_date": "2025-11-15"
  }]
}
```

Inside the model:
1. `city` → vocabulary lookup → embedding (all inside TF graph)
2. `total_revenue` → z-score normalization with training-set stats (inside TF graph)
3. `segment` → vocabulary lookup → embedding (inside TF graph)
4. Cross features computed (inside TF graph)
5. Query tower processes transformed features → recommendations returned

No preprocessing service. No Lambda. No feature store sync. The model is fully self-contained.

**Without tf.Transform (the AWS/SageMaker pattern):**

A separate preprocessing service must be maintained:
```python
# Lambda or Python application -- SEPARATE from the model
city_index = vocabulary_lookup["Warsaw"]           # Which version of the vocab file?
revenue_normalized = (80000 - mean) / std          # Which mean/std? From which training run?
segment_index = segment_vocab["Enterprise"]        # Synced with the model's expectations?

# Then send preprocessed values to the model endpoint:
{"instances": [{"city": 0, "total_revenue": 1.0, "segment": 2}]}
```

Every time the model retrains (new vocabulary entries, updated normalization stats), the preprocessing Lambda must be updated in lockstep. Miss an update → silent accuracy degradation.

### 4.4 Portable Serving

Because tf.Transform is embedded in the SavedModel, the trained model is a self-contained artifact that works on any TF Serving instance:

- **Google Cloud Run** (current platform deployment)
- **AWS ECS/Fargate** with TF Serving container
- **AWS SageMaker Endpoints** with TF Serving container
- **On-premise** Docker with TF Serving
- **Any Kubernetes cluster** with TF Serving pod

The client can train models on this SaaS platform and deploy the exported SavedModel on their own AWS infrastructure. Raw JSON in, recommendations out -- no preprocessing infrastructure required on the client side.

---

## 5. Summary: Three Unassailable Points

1. **Technology lock.** TFX + TFRS + ScaNN + Dataflow is a GCP-native technology stack. It cannot be meaningfully ported to AWS without a complete rewrite costing $740K-$1.1M and 12-18 months of engineering.

2. **Amazon Personalize is not a substitute.** It is a black-box service with max 5 metadata fields, no architecture control, no multi-task learning, no model export, and ID-based inference that uses stale data. It solves a different problem for a different audience.

3. **tf.Transform eliminates the #1 production ML problem.** Training-serving skew causes silent accuracy degradation. tf.Transform embeds all preprocessing into the model itself, making skew mathematically impossible. No AWS service provides this guarantee. The exported models work on any TF Serving deployment, including AWS infrastructure.

---

## Related Documentation

- [Implementation Overview](../implementation.md) -- SaaS architecture and multi-tenant design
- [Training Phase](../phase_training.md) -- TFX pipeline stages and GPU configuration
- [Deployment Phase](../phase_endpoints.md) -- Model serving and endpoint management
