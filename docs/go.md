# Go Backend — IP Protection & On-Premises Distribution

## Document Purpose

This document outlines the strategy for building a compiled Go backend of the B2B Recommendation System, enabling secure on-premises deployment to enterprise clients without exposing source code or intellectual property.

**Created**: 2026-03-02

---

## Executive Summary

### The Problem

1. **Client demand**: Enterprise clients aggressively push for self-hosted installations (their own GCP projects, AWS, or on-premises datacenters)
2. **IP exposure**: The current Django/Python stack is fully readable — anyone with container access can extract and understand the entire codebase
3. **AI threat**: Modern AI (Claude, GPT) can analyze extracted Python source code and reconstruct the business logic, refactor it, or translate it to another framework in minutes

### The Solution

Maintain **two release tracks** from the same business logic:

| Track | Technology | Deployment | Update Cadence | Target Clients |
|-------|-----------|------------|----------------|----------------|
| **SaaS** | Django (Python) | Our GCP infrastructure | Daily/continuous | Clients who accept SaaS |
| **Self-hosted** | Go (compiled binary) | Client's infrastructure | Quarterly (every 2-3 months) | Enterprise clients demanding on-prem |

### Why Go

| Factor | Python (.py) | Cython (.so) | Go Binary | Rust Binary |
|--------|-------------|-------------|-----------|-------------|
| **AI reverse-engineering** | 100% recoverable | 60-80% recoverable | 10-15% recoverable | 5-10% recoverable |
| **Learning curve** | N/A (current stack) | Low | Moderate (2-4 weeks) | High (3-6 months) |
| **Web framework maturity** | Excellent (Django) | N/A | Excellent (Gin, Echo) | Good (Actix, Axum) |
| **Google Cloud SDK** | First-party | N/A | First-party | Community-maintained |
| **Development speed vs Python** | 1x | 1x | 2-3x slower | 4-6x slower |
| **Hire developers** | Easy | N/A | Easy | Hard |

**Go is the right balance** — strong enough protection that reverse engineering is commercially impractical, with reasonable development speed and excellent GCP integration.

### Why Not Cython

Cython was considered and rejected for this specific application because our code generation engine works by building Python code strings. These template strings survive as **readable string literals** in compiled .so files and can be extracted with a simple `strings` command. The core IP would be exposed without any decompilation effort.

---

## Threat Analysis

### What We're Protecting

The system's intellectual property, ranked by value:

| Component | Current File | Lines | Value |
|-----------|-------------|-------|-------|
| **TFX Code Generation Engine** | `ml_platform/configs/services.py` | ~8,000 | Highest — months of domain knowledge |
| **TrainerModuleGenerator** | `ml_platform/configs/services.py` | ~2,000 | High — TFRS model generation |
| **PreprocessingFnGenerator** | `ml_platform/configs/services.py` | ~2,000 | High — TFX Transform generation |
| **SmartDefaults Engine** | `ml_platform/configs/services.py` | ~500 | High — semantic column analysis |
| **Pipeline Orchestration** | `ml_platform/training/services.py` | ~3,400 | Medium — Vertex AI integration |
| **Hyperparameter Analyzer** | `ml_platform/experiments/hyperparameter_analyzer.py` | ~860 | Medium — TPE analysis |
| **ETL Runner** | `etl_runner/` | ~4,000 | Low — commodity patterns |
| **Django UI** | `templates/`, `static/` | ~15,000 | Low — frontend is visible anyway |

### Attack Vectors (Current Python Stack)

1. **Container extraction**: `docker cp container:/app/ ./` — full source code in seconds
2. **Pod exec**: `kubectl exec -it pod -- cat /app/ml_platform/configs/services.py`
3. **Image inspection**: Pull Docker image, extract filesystem layers
4. **AI analysis**: Feed extracted Python to Claude/GPT for instant understanding and refactoring

### Post-Go Compilation

1. **Container extraction**: Gets a single binary — no readable source
2. **Decompilation**: Ghidra/IDA produce meaningless assembly-level pseudocode
3. **AI analysis**: Claude cannot reconstruct business logic from decompiled Go binaries
4. **String extraction**: Go binary embeds strings differently — template logic is compiled, not literal

---

## Architecture

### Two-Track Development Model

```
YOUR DEVELOPMENT WORKFLOW

Daily development (Django)
|
+-- Feature built & tested in Django
+-- Deployed to SaaS clients immediately
|
|   Every 2-3 months
|   |
|   v
|   Go release branch
|   +-- Port accumulated Django changes to Go
|   +-- Compile binary
|   +-- Test
|   +-- Ship to on-prem clients
|   +-- v1.4.0, v1.5.0, v1.6.0...
|
v
Continue daily Django development
```

### Industry Precedent

This is the standard model for enterprise software companies:

| Company | Fast Track (SaaS) | Slow Track (Self-hosted) |
|---------|-------------------|--------------------------|
| GitLab | gitlab.com updated daily | Self-managed release monthly |
| Sentry | sentry.io continuous | Self-hosted release every 2-3 months |
| Metabase | Cloud updated weekly | Self-hosted release quarterly |

### What the Client Receives

```
+--------------------------------------------------+
|  Single Docker Container                          |
|                                                   |
|  +--------------------------------------------+  |
|  |  codegen-server (Go binary, ~50-80MB)      |  |
|  |                                             |  |
|  |  - Web UI (embedded HTML/JS/CSS)           |  |
|  |  - Code generation engine (compiled)       |  |
|  |  - SmartDefaults (compiled)                |  |
|  |  - Pipeline builder (compiled)             |  |
|  |  - TrainerModuleGenerator (compiled)       |  |
|  |  - License verification (compiled)         |  |
|  |  - All API handlers (compiled)             |  |
|  +--------------------------------------------+  |
|                                                   |
|  license.token      <- signed license file        |
|  templates/         <- HTML (visible, not IP)     |
|  static/            <- JS/CSS (visible, not IP)   |
+--------------------------------------------------+
```

### Generated Code Flow

The Go binary generates Python code (TFX Transform and Trainer modules) at runtime. This generated code is **output**, not the generator:

```
Client clicks "Generate Pipeline" in UI
        |
        v
Go binary (internal/codegen/)
        |  Generates:
        |  - transform.py (TFX preprocessing)
        |  - trainer.py (TFRS model)
        |  - pipeline.json (KFP v2)
        v
Uploads to client's GCS
        |
        v
Submits to client's Vertex AI / SageMaker / K8s
```

Seeing one generated output doesn't reveal how the generator works across all permutations — the value is in the generator, not any single output.

---

## Licensing System

### Cryptographic Offline Tokens

Designed for air-gapped environments — **no network connection to our servers required**.

```
OUR SIDE (license server)              CLIENT SIDE (air-gapped)
+------------------------+            +-------------------------+
|                        |            |                         |
|  Private Key (RSA)     |            |  Go Binary              |
|  +------------------+  |  email /   |  +-------------------+  |
|  | Signs license    |--+- portal -->|  | Embedded Public   |  |
|  | tokens           |  |            |  | Key (RSA)         |  |
|  +------------------+  |            |  |                   |  |
|                        |            |  | Verifies token    |  |
|  License Portal (web)  |            |  | signature         |  |
|  - Generate tokens     |            |  | Checks expiry     |  |
|  - Track clients       |            |  | Checks features   |  |
|  - Renewal workflow    |            |  +-------------------+  |
+------------------------+            +-------------------------+
```

### Token Structure

```json
{
  "client_id": "acme-corp",
  "issued_at": "2026-03-02",
  "expires_at": "2027-03-02",
  "tier": "enterprise",
  "features": {
    "max_pipelines": 50,
    "model_types": ["retrieval", "ranking", "multitask"],
    "gpu_training": true,
    "max_data_sources": 20
  },
  "hardware_fingerprint": "sha256:a1b2c3...",
  "min_version": "1.4.0",
  "max_version": "2.0.0"
}
-- RSA-SHA256 signature --
```

### Renewal Flow (No Network Required)

```
Step 1: Client runs:     ./codegen-server license request
        Output:          License Request Code: eyJoYXJkd2FyZV9pZCI6...

Step 2: Client sends code to account manager (email, portal, phone)

Step 3: We generate a new signed token

Step 4: Client applies:  ./codegen-server license activate --token "eyJ0eXAi..."
        Output:          License valid until 2027-03-02
```

### Grace Period Strategy

```
License expires
      |
      v
Days 1-14:   Warning banner in UI, full functionality
Days 15-30:  Warning + read-only mode (view experiments, no new pipelines)
Day 31+:     System locked, only "license activate" command works
```

### Controllable Parameters

| Parameter | Token Field | Example |
|-----------|-------------|---------|
| Subscription expiry | `expires_at` | System stops generating pipelines after date |
| Feature gating | `features` map | Free = retrieval only, Enterprise = all 3 model types |
| Usage limits | `max_pipelines` | Cap pipeline runs per license period |
| Hardware binding | `hardware_fingerprint` | Token only works on specific machine/VM |
| Version control | `min_version` / `max_version` | Force upgrades or block outdated binaries |

---

## Project Structure

### Repository Layout

The Go backend lives alongside the existing Django project in the same repository:

```
b2b_recs/                           <- existing repo
|
|-- manage.py                       <- Django entry point
|-- config/                         <- Django settings
|-- ml_platform/                    <- Django app (daily development)
|-- etl_runner/                     <- ETL (stays Python)
|-- templates/                      <- HTML templates (shared)
|-- static/                         <- JS/CSS/images (shared)
|-- Dockerfile                      <- Django container
|
|-- go-backend/                     <- Go version
|   |-- go.mod
|   |-- go.sum
|   |-- Dockerfile                  <- Go container (single binary + distroless)
|   |
|   |-- cmd/
|   |   +-- server/
|   |       +-- main.go             <- CLI entry point, flags, startup
|   |
|   |-- internal/                   <- private packages (Go enforces this)
|   |   |
|   |   |-- codegen/                <- CORE IP
|   |   |   |-- preprocessing.go    <- PreprocessingFnGenerator
|   |   |   |-- trainer.go          <- TrainerModuleGenerator
|   |   |   |-- smart_defaults.go   <- SmartDefaultsService
|   |   |   |-- validator.go        <- code validation
|   |   |   +-- templates/          <- Go text/template files for TFX code
|   |   |
|   |   |-- pipeline/               <- pipeline builder
|   |   |   |-- builder.go          <- KFP v2 pipeline construction
|   |   |   +-- vertex.go           <- Vertex AI submission
|   |   |
|   |   |-- license/                <- licensing system
|   |   |   |-- license.go          <- token parsing & verification
|   |   |   |-- crypto.go           <- RSA signature validation
|   |   |   +-- hardware.go         <- machine fingerprinting
|   |   |
|   |   |-- models/                 <- database models (GORM)
|   |   |   |-- endpoint.go         <- ModelEndpoint
|   |   |   |-- dataset.go          <- Dataset, ColumnMapping
|   |   |   |-- feature_config.go   <- FeatureConfig, FeatureConfigVersion
|   |   |   |-- model_config.go     <- ModelConfig
|   |   |   |-- experiment.go       <- QuickTest
|   |   |   +-- training.go         <- TrainingRun, RegisteredModel
|   |   |
|   |   |-- api/                    <- HTTP handlers
|   |   |   |-- router.go           <- all route definitions
|   |   |   |-- middleware.go       <- auth, license check, CORS
|   |   |   |-- configs.go          <- /api/configs/* endpoints
|   |   |   |-- datasets.go         <- /api/datasets/* endpoints
|   |   |   |-- experiments.go      <- /api/experiments/* endpoints
|   |   |   |-- training.go         <- /api/training/* endpoints
|   |   |   +-- etl.go              <- /api/etl/* endpoints
|   |   |
|   |   |-- auth/                   <- authentication
|   |   |   |-- session.go          <- session management
|   |   |   +-- middleware.go       <- auth middleware
|   |   |
|   |   +-- cloud/                  <- GCP integrations
|   |       |-- bigquery.go         <- BigQuery client
|   |       |-- gcs.go              <- Cloud Storage client
|   |       |-- vertex.go           <- Vertex AI client
|   |       +-- scheduler.go        <- Cloud Scheduler client
|   |
|   |-- templates/ -> ../templates/ <- symlink to shared templates
|   |-- static/ -> ../static/       <- symlink to shared static files
|   |
|   +-- migrations/                 <- SQL migration files
|       |-- 001_initial.sql
|       |-- 002_add_training.sql
|       +-- ...
|
|-- docs/
|-- scripts/
|-- cloudbuild/
+-- deploy/
```

### Key Go Conventions

- **`internal/`**: Go compiler enforces that these packages cannot be imported by external code. Even if someone obtains the source, they cannot use these packages in their own projects.
- **`cmd/`**: Standard Go convention for executable entry points.
- **Symlinks for templates/static**: Both Django and Go serve the same frontend files. The JavaScript calls REST APIs and doesn't care which backend responds.

### Dockerfile (Go)

```dockerfile
# Build stage
FROM golang:1.22-alpine AS builder
WORKDIR /build
COPY go-backend/ .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o codegen-server ./cmd/server/

# Runtime stage — distroless: no shell, no package manager, nothing to exec into
FROM gcr.io/distroless/static:nonroot
COPY --from=builder /build/codegen-server /
COPY templates/ /templates/
COPY static/ /static/
ENTRYPOINT ["/codegen-server"]
```

Build flags explained:
- `CGO_ENABLED=0`: Pure Go binary, no C dependencies, fully static
- `-ldflags="-s -w"`: Strip debug symbols and DWARF info — smaller binary, harder to decompile

---

## Django-to-Go Mapping

### Models (Django ORM -> GORM)

```
Django:                              Go (GORM):

class ModelEndpoint(models.Model):   type ModelEndpoint struct {
    name = CharField(max=200)            gorm.Model
    slug = SlugField(unique=True)        Name string `gorm:"size:200"`
    ...                                  Slug string `gorm:"uniqueIndex"`
                                         ...
                                     }
```

### API Endpoints (Django Views -> Gin Handlers)

```
Django:                              Go (Gin):

@api_view(['GET'])                   func GetFeatureConfigs(c *gin.Context) {
def get_feature_configs(request):        modelID := c.Param("modelId")
    configs = FeatureConfig.objects       var configs []models.FeatureConfig
        .filter(model_endpoint=id)       db.Where("model_endpoint_id = ?",
    return JsonResponse(...)                 modelID).Find(&configs)
                                         c.JSON(200, configs)
                                     }
```

### Code Generation (Python string building -> Go text/template)

```
Django (services.py):                Go (codegen/preprocessing.go):

def generate_preprocessing():        func GeneratePreprocessing(
    code = "import tensorflow\n"         cfg FeatureConfig,
    code += f"def preprocessing_fn"  ) string {
    code += f"(inputs):\n"               tmpl := template.Must(
    for feat in features:                    template.ParseFS(
        code += f"  {feat}...\n"                 templates, "preprocessing.tmpl",
    return code                          ))
                                         var buf bytes.Buffer
                                         tmpl.Execute(&buf, cfg)
                                         return buf.String()
                                     }
```

---

## Implementation Plan

### Phase 1: Foundation + Core IP (Weeks 1-8)

**Goal**: Go binary that generates TFX code and enforces licensing.

| Week | Task | Django Equivalent |
|------|------|-------------------|
| 1-2 | Go project setup, database models (GORM), DB connection | `models.py` |
| 3-4 | PreprocessingFnGenerator in Go | `configs/services.py` (partial) |
| 5-6 | TrainerModuleGenerator + SmartDefaults in Go | `configs/services.py` (rest) |
| 7 | License system (RSA tokens, verification, grace period) | New — doesn't exist in Django |
| 8 | Pipeline builder (KFP v2 JSON generation) | `pipelines/pipeline_builder.py` |

**Deliverable**: `go build` produces a binary that can generate TFX code and validate licenses.

### Phase 2: API Layer + Auth (Weeks 9-16)

**Goal**: Go binary serves the web UI and all REST APIs.

| Week | Task | Django Equivalent |
|------|------|-------------------|
| 9-10 | HTTP server, template rendering, static file serving | Django views + URL routing |
| 11-12 | Configs API endpoints (feature configs, model configs) | `configs/api.py` |
| 13-14 | Dataset API endpoints, BigQuery integration | `datasets/api.py`, `datasets/services.py` |
| 15 | Experiments API endpoints | `experiments/api.py` |
| 16 | Auth middleware, session management | Django auth |

**Deliverable**: Full web application running from a single Go binary.

### Phase 3: Training + Cloud Integration (Weeks 17-22)

**Goal**: Complete feature parity with Django for training workflows.

| Week | Task | Django Equivalent |
|------|------|-------------------|
| 17-18 | Training run management, Vertex AI integration | `training/services.py` |
| 19-20 | Experiment dashboard, hyperparameter analysis | `experiments/services.py` |
| 21-22 | Cloud Scheduler integration, ETL orchestration | `etl/services.py`, `utils/` |

**Deliverable**: Full feature parity. Ready for first on-prem client.

### Phase 4: Hardening (Weeks 23-24)

| Task | Purpose |
|------|---------|
| Security audit of binary | Verify no string leaks |
| Load testing | Ensure performance parity with Django |
| Migration tooling | Script to set up client database from scratch |
| Documentation | Operator guide for on-prem deployment |
| CI/CD pipeline | Automated Go build + release process |

---

## Porting Workflow (Ongoing)

After initial release, new features follow this cycle:

```
1. Build and test feature in Django (daily development)

2. When Go release is due (every 2-3 months):
   a. Create release branch: git checkout -b go-release/v1.5.0
   b. Port accumulated Django changes to Go
   c. Run tests
   d. Build binary: cd go-backend && go build -o codegen-server ./cmd/server/
   e. Build Docker image
   f. Tag release: v1.5.0
   g. Ship to on-prem clients

3. Continue daily Django development on main branch
```

---

## Pricing Strategy

The self-hosted Go binary should be priced significantly higher than SaaS:

| Tier | Deployment | Updates | Price Multiplier |
|------|-----------|---------|-----------------|
| **SaaS** | Our infrastructure | Continuous | 1x (base) |
| **Self-hosted** | Client infrastructure | Quarterly | 2-3x |

Higher pricing:
- Compensates for the porting effort and support burden
- Pushes clients toward SaaS where IP is fully protected
- Makes the Go binary a premium option, not the default

---

## Client Messaging

### For clients accepting SaaS:

> "Your data stays 100% in your own GCP project. Our application runs on our infrastructure and connects to your data through secure, authenticated APIs. We never store your data."

### For clients demanding self-hosted:

> "We provide a fully self-contained application that runs entirely within your infrastructure. Your data never leaves your network. The application is delivered as a compiled binary with quarterly feature updates and offline license management."

### For clients asking about source code:

> "The application is delivered as compiled software, similar to how Oracle, SAP, or Databricks deliver their enterprise products. Source code is not included. An escrow agreement is available — if our company ceases operations, the source code is released to active licensees."

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Go rewrite takes longer than estimated | Delayed on-prem offering | Phase 1 alone (code gen + license) provides standalone value |
| Feature drift between Django and Go | Client confusion | Strict quarterly sync, shared test suite for API contracts |
| Go development slower for new features | Reduced velocity | Django remains primary — Go is a quarterly port, not daily dev |
| Client demands source code | IP exposure | Compiled binary only, escrow agreement for business continuity |
| License system bypassed | Revenue loss | License checks woven throughout binary, not just at startup |

---

## Next Steps

1. **Initialize Go project**: `go mod init`, set up directory structure
2. **Start with licensing**: Build the RSA token system first — it's standalone and immediately useful
3. **Port code generation engine**: The core IP, highest priority
4. **Build minimal API server**: Enough to serve the configs page with code generation
5. **First on-prem pilot**: Deploy to one friendly client for validation

---

## References

- [Go Gin Web Framework](https://gin-gonic.com/)
- [GORM ORM](https://gorm.io/)
- [Google Cloud Go SDK](https://cloud.google.com/go/docs/reference)
- [Go embed.FS](https://pkg.go.dev/embed) — embedding static files in binaries
- [Go text/template](https://pkg.go.dev/text/template) — template engine for code generation
- [distroless containers](https://github.com/GoogleContainerTools/distroless) — minimal Docker images
