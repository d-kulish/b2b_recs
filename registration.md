# Google Partner Registration & GCP Marketplace Listing

**Domain:** `recs.studio`
**Business Email:** `d.kulish@recs.studio`
**Start Date:** 2026-05-21

---

## Goal

Register as a **Google Cloud Technology Partner** and list the **Recs Studio** SaaS platform on the **Google Cloud Marketplace**.

This enables:
- Credibility as a Google-vetted ISV building on GCP
- Distribution through the GCP Marketplace to enterprise buyers
- Co-selling opportunities with Google Cloud field teams
- Access to partner benefits (credits, support, training)

---

## Prerequisites

| Requirement | Status | Notes |
|---|---|---|
| Verified domain (`recs.studio`) | Complete | GoDaddy registrar, Google Workspace DNS verification passed |
| Professional business email | Complete | `d.kulish@recs.studio` via Google Workspace Business Starter |
| Registered business entity | **Accepted** | Sole proprietorship (ФОП) verified by Partner Advantage; MVA signed 2026-06-05 |
| GCP project with billing | Complete | `b2b-recs` project active in `europe-central2` |
| Working SaaS product | Complete | Production-deployed multi-tenant TFRS platform |

---

## Completed Steps

### Phase 1: Domain & Email Foundation

**1.1 Domain Verification**
- Domain `recs.studio` verified in Google Workspace Admin console
- DNS TXT record (`google-site-verification=...`) added in GoDaddy

**1.2 Google Workspace Setup**
- Upgraded from **Cloud Identity Free** to **Google Workspace Business Starter**
- Billing active with self-employed tax details
- Gmail service enabled

**1.3 DKIM Authentication**
- Generated DKIM key in Google Workspace Admin console
- Added TXT record: `google._domainkey`
- Authentication confirmed

**1.4 MX Record Migration**
- Removed ImprovMX records (`mx1.improvmx.com`, `mx2.improvmx.com`)
- Added Google Workspace MX records:
  - `aspmx.l.google.com.` (Priority 1)
  - `alt1.aspmx.l.google.com.` (Priority 5)
  - `alt2.aspmx.l.google.com.` (Priority 5)
  - `alt3.aspmx.l.google.com.` (Priority 10)
  - `alt4.aspmx.l.google.com.` (Priority 10)
- Email to `d.kulish@recs.studio` now routes to Google Workspace inbox

**1.5 DNS Current State (GoDaddy)**
- **A/AAAA records:** Pointing to Google (for domain services)
- **MX records:** Google Workspace active
- **TXT records:**
  - `google-site-verification` — Google Workspace domain verification
  - `v=spf1 include:dc-aa8e722993._spfm.recs.studio ~all` — root SPF (Google + other services)
  - `dc-aa8e722993._spfm` — includes `_spf.google.com`
  - `dc-fd741b8612._spfm.send` — includes `amazonses.com` (Resend/SES)
  - `google._domainkey` — Google Workspace DKIM
  - `resend._domainkey` — Resend DKIM (kept for website transactional emails)
  - `send` — Resend SPF
  - `_dmarc` — DMARC policy (`p=quarantine`)
- **CNAME records:** `www` and `_domainconnect` (GoDaddy defaults)

**1.6 Cleanup**
- Removed `d.kulish@recs.studio` from Outlook desktop client
- Google Workspace Gmail is the primary client for business email
- Website demo request emails remain on Resend API (unchanged)

---

## Partner Advantage Verification Complete ✅ (2026-06-03)

| Component | State |
|---|---|
| Google Workspace Business Starter | Active, billing set up |
| Gmail (`d.kulish@recs.studio`) | Working, receiving mail |
| Domain verification | Complete |
| DKIM | Authenticated |
| MX records | Cut over to Google |
| SPF | Merged (Google + Resend subdomains) |
| Resend (website emails) | Preserved and functional |
| Partner Advantage enrollment | **COMPLETE** |
| Partner Network Hub access | **GRANTED** |

### Verification Emails Received

**Email 1 — Partner Advantage Membership Confirmation (2026-06-03)**
> Subject: It's official! Your company is now a member of Google Cloud Partner Advantage.
> Content: Welcome to the new way to cloud. Next steps: create Cloud Identity password and verify company domain for `recs.studio`.

**Email 2 — Partner Support Desk Case Resolution (2026-06-03, 4:39 PM GMT)**
> From: Agent JM (Partner Support Desk)
> Case: 71883638
> Content: Account verification is now complete. Full access to Partner Network Hub granted.
> Action requested: Confirm if case is ready to be closed.

**Key outcomes:**
1. Sole proprietorship (ФОП) was **accepted** by the data validation team.
2. Portal blocker (`"organisation is being registered"`) is resolved.
3. Can now sign in to Partner Hub and proceed with Marketplace listing.

---

## Escalation History (Resolved)

### Original Verification Request (2026-05-24)

Reply sent to `concierge-amer@google.com`:

```
Hi Partner Advantage Team,

Here is the requested information:

Legal Company Name: Dmytro Kulish
Street Address: 4 Chumaka str., apt 14
City: Kyiv
State: N/A
Zip: 03065
Country: Ukraine
Website: https://recs.studio

I operate as a sole proprietor. Please confirm if this structure is acceptable for
the Registered Partner tier, and whether an incorporated entity will be required for
a future Google Cloud Marketplace listing.

Best,
Dmytro Kulish
d.kulish@recs.studio
```

### Escalation Actions (2026-06-02)

After 9 days with no acknowledgment:

1. **Follow-up email** sent to `concierge-amer@google.com`
2. **Partner Support Desk form** submitted (Case 71883638)

### Partner Support Desk Exchange (2026-06-02 → 2026-06-03)

- **Incoming (2026-06-02):** Agent JM requested exact details as on official business documentation.
- **Outgoing (2026-06-03):** Replied with data block and re-stated sole proprietorship questions.
- **Resolution (2026-06-03):** Account verification confirmed complete.

---

## Marketplace Vendor Eligibility — RESOLVED ✅ (2026-06-05)

After closing case 71883638, a **new** Partner Support case was opened to confirm Marketplace-specific requirements before any technical work.

### Case Details

| Field | Value |
|---|---|
| **Issue Area** | Partner Support Desk |
| **Issue Type** | Google Cloud Marketplace |
| **Subject** | Ukrainian sole proprietor (ФОП): eligible to list SaaS on Marketplace? |
| **Category** | Countries and regions selling on Google Marketplace |
| **Case Number** | 71961480 |
| **Status** | **RESOLVED** |
| **Resolution** | Agent Gerardo confirmed account is verified and directed to MVA signing URL |

### Partner Support Desk Exchange (Case 71961480)

**Agent Gerardo's reply (2026-06-04, 7:24 PM GMT):**
> "To us, the commercial name of your company is not relevant. I can see your partner account is created successfully, so you can proceed to sign the MVA and start your MP onboarding process... I am happy to confirm that the account that has access to sign the Docs is d.kulish@recs.studio."

**Key finding:** The Partner Support Desk did not escalate the entity-type question to legal/compliance. Instead, they directed the existing verified account to the MVA signing portal. This is Google's operational confirmation that the verified sole proprietorship (ФОП) profile is acceptable for Marketplace.

---

## MVA Acceptance Complete ✅ (2026-06-05)

The Google Cloud Marketplace Vendor Agreement was accessed and accepted via `https://partners.cloud.google.com/marketplace-vendor-agreement`.

### Acceptance Details

| Field | Value |
|---|---|
| **Legal notice email** | `d.kulish@recs.studio` |
| **General contact email** | `d.kulish@recs.studio` |
| **Effective Date** | 2026-06-05 (date of acceptance) |
| **Entity bound** | Dmytro Kulish (sole proprietor / ФОП) |
| **Transaction model** | Merchant of Record (Ukraine is non-agency) |

### Contractual Confirmation: No LLC Required

The Agreement's **Definitions section (Section 15)** defines **"Vendor"** as:
> *"the **person or entity** specified in the information table above who is registered with and approved by Google for listing of software or services via the Marketplace."*

The explicit inclusion of **"person"** alongside "entity" confirms that a natural person operating as a sole proprietor is a valid contracting party. There is no requirement for an incorporated entity (LLC, corporation, etc.) anywhere in the agreement.

**Bottom line:** Your ФОП structure is contractually valid for the Marketplace Vendor Agreement. No LLC formation is required at this stage (or based on current contract terms).

### Key Commercial Terms (Merchant-of-Record Model)

Because Ukraine is **not** an Agency Jurisdiction, Google acts as the **merchant of record and reseller** (Section 2.2 + Section 13). This means:
- Google collects customer payments, handles chargebacks/refunds, and remits your share.
- You do **not** need your own merchant-of-record infrastructure in Ukraine.
- Google handles transaction tax (VAT) collection for non-U.S. customers.
- Payments are made monthly to your **Payment Account** (minimum payout: **$100 USD**).
- You retain ownership of your product and IP (Section 5.4).

### Next Actions from Google

Per the MVA acceptance page:
> *"If you're a new partner, you'll receive instructions via email to gain access to Producer Portal."*

**Status:** Awaiting email from Google with Producer Portal access instructions.

---

## Solution Validation Form — Escalated via Email (2026-06-06)

On 2026-06-05 at 11:48 AM GMT, **Agent Tanya P** (Case #71987890) confirmed MVA completion and sent the **Solution Validation form** link. The form is a Google Form (18 pages, typically 4–6 sections for SaaS) that gauges product fit and assigns a revenue share.

### Decisions Made

| Question | Decision | Rationale |
|---|---|---|
| **Product Type** | **SaaS — with billing integration** | True managed SaaS; enables Google billing, co-selling, procurement integration |
| **Workload location** | **Everything runs in the partner's tenant** | Recs Studio company pays GCP (~$800/mo per customer) and resells at margin. Customer pays Recs Studio, not Google directly. |
| **Single vs. Multi-tenant** | **Single-tenant per customer** | Each customer receives an isolated GCP project with dedicated Cloud Run, BigQuery, Vertex AI, etc. |

### Assets Prepared

| Asset | File / Status | Notes |
|---|---|---|
| **Architecture Diagram** | `docs/marketplace-architecture-variant1.html` | Two-container layout: Customer Infrastructure → GCP Project. Uses real Google Cloud product icons (inline SVG, official colors). **Fixed:** "React frontend" label corrected to "Django UI" (line 289). Ready for Print → PDF → form upload. |
| **Pricing Calculator Estimate** | *Text breakdown ready* | Target: **~$800/month per customer** — $300 base infra + $500 GPU training. See breakdown below. |
| **GTV / Market Projections** | *Drafted in escalation email* | 1-year projected Gross Transaction Value and small/medium/large customer pricing tiers. |
| **Terms of Service** | ✅ Deployed live | Updated to June 2026. Added Marketplace merchant-of-record clause, GCP Terms reference, data residency. No entity type disclosed publicly. Live at https://recs.studio/terms/ |
| **Privacy Policy** | ✅ Deployed live | Updated to June 2026. Added explicit subprocessor list (GCP + Resend), data residency clause, DPA/SCCs available upon request. Live at https://recs.studio/privacy/ |
| **Product Screenshots** | ⏳ Pending | Need 3–5 screenshots from live app (Dashboard, ETL Wizard, Schema Builder, Training Pipeline, Deployment). Compress to < 500 KB each. |

### Pricing Calculator Breakdown (Single-Tenant)

Target monthly cost per customer: **~$800 USD**.

| # | GCP Service | Monthly Estimate |
|---|---|---|
| 1 | Cloud Run (Services: Django App + Model Serving) | ~$130 |
| 2 | Cloud Run (Job: ETL Runner) | ~$90 |
| 3 | Cloud SQL (PostgreSQL 15, db-n1-standard-2) | ~$110 |
| 4 | BigQuery (500 GB storage + 5 TB queries) | ~$90 |
| 5 | Cloud Storage (300 GB Standard + 200 GB Nearline) | ~$35 |
| 6 | Cloud NAT (1 gateway + 500 GB) | ~$35 |
| 7 | Dataflow (3× n1-standard-4, 20 hrs/mo) | ~$60 |
| 8 | Cloud Build (~30 builds/mo) | ~$25 |
| 9 | Vertex AI Custom Training (n1-standard-16 + 2×T4, 24 hrs/mo) | ~$450 |
| 10 | Vertex AI Pipelines (20 runs/mo) | ~$50 |
| 11 | Platform services (Scheduler, Secrets, Monitoring) | ~$25 |
| | **Total** | **~$800–850** |

### Form Submission Failure & Escalation

**Problem:** The Solution Validation form returned the error **"Something went wrong. Please try again."** on every submission attempt.

**Attempts made:**
- **8 total submission attempts** across Chrome, Safari, and Chrome Incognito (no extensions)
- Multiple file sizes tested (all < 500 KB)
- Different upload methods (paste vs. upload) tested
- Form remained non-functional over multiple days (2026-06-05 through 2026-06-06)

**Escalation sent 2026-06-06:**

#### Escalation 1 — Direct Email to Solution Validation Team
**To:** `gcp-solution-validation@google.com`  
**Subject:** Solution Validation Form Technical Failure — Case 71987890 — Recs Studio SaaS

Full submission package sent, including:
- Architecture Diagram (PDF)
- Pricing Calculator breakdown (text)
- Product screenshots (5 images)
- GTV & Market Projections (text)
- Product details: SaaS with billing integration, single-tenant per customer, ~$800/mo infra
- Year 1 GTV projection: ~$235,000 USD
- Terms of Service: https://recs.studio/terms/
- Privacy Policy: https://recs.studio/privacy/

Requested either review of attached materials or an alternative submission method.

#### Escalation 2 — "Contact Form Owner" Popup
**Subject:** Form repeatedly fails with "Something went wrong" — Case 71987890  
**Message:** Brief technical report confirming 8+ failed attempts across multiple browsers, no extensions, and fallback email already sent to `gcp-solution-validation@google.com`. Requested form fix or manual forwarding to the Solution Validation team.

### Current Status (as of 2026-06-06)

- **Form submission:** ❌ Blocked — form appears non-functional
- **Email escalation:** ✅ Sent to `gcp-solution-validation@google.com`
- **Form owner contact:** ✅ Sent via popup
- **Awaiting:** Response from Solution Validation team (target: 2–4 business days)
- **Do not retry the form** — wait for email response or form fix

---

## Solution Validation — Google Follow-up Questions (2026-06-10)

Google Cloud Marketplace Team reviewed the submission and sent follow-up questions on **Case 72148641** regarding:
1. Whether the customer infrastructure (left side of the architecture diagram) is managed exclusively by the customer and if any components are deployed there.
2. Clarification on Vertex AI usage, given the earlier statement that the solution "does not use any AI."

### Response Sent (2026-06-10)

Clarification email sent to Google Cloud Marketplace Team with updated architecture diagram (`docs/marketplace-architecture-variant1.html`).

**Key clarifications provided:**
- **Customer Data Sources:** The left-side components (SQL Databases, NoSQL Stores, Object Storage) are the customer’s existing data stores. Recs Studio does not deploy any software, agents, or components into the customer environment. The ETL Runner (a Cloud Run Job within the isolated GCP project) connects via read-only APIs. The customer only needs to open network-level access (e.g., firewall whitelisting of the Cloud NAT static IP).
- **Vertex AI / "No AI" correction:** Recs Studio uses classical machine learning (not Generative AI / LLMs). The Vertex AI label refers to: Pipelines (TFX orchestration), Custom Training (TensorFlow Recommenders — two-tower collaborative filtering), and Model Registry. No pre-trained AI models or third-party AI APIs are used. Model serving runs on Cloud Run (TF Serving / ScaNN), not Vertex AI Prediction.

**Diagram updates made:**
- `Customer Infrastructure` → `Customer Data Sources`
- `Managed by the customer` → `No Recs Studio components deployed here`
- `TFX pipelines / TFRS training` → `Pipelines, Training, Registry / Classical ML only`
- Added notes: Vertex AI sub-products, explicit statement that no components are deployed into customer environment

---

## Technical Fixes Completed (2026-06-06)

### Website Deploy Script Bug Fix
**File:** `website/deploy_website.sh`  
**Issue:** Post-deploy `gcloud run services describe` failed with `ERROR: (gcloud.run.services.describe) Cannot find service [django-app-website]` because `--project ${PROJECT_ID}` was missing. The user's default gcloud project (`memo2-456215`) differed from the target project (`b2b-recs`).  
**Fix:** Added `--project ${PROJECT_ID}` to line 79. Deployments now complete cleanly.

### Website Deployment — Terms & Privacy Updates
**Revisions deployed:**
- `django-app-website-00009-lt4` (first deploy with entity disclosure error)
- `django-app-website-00010-8q9` (redeploy after removing "ФОП" from public Terms)

**What changed:**
- Terms of Service: June 2026 date, Marketplace merchant-of-record clause, GCP Terms reference, data residency
- Privacy Policy: June 2026 date, explicit subprocessors (GCP services + Resend), data residency, DPA/SCCs clause
- **Critical fix:** Removed "Dmytro Kulish, sole proprietor (ФОП) registered in Kyiv, Ukraine" from public-facing Terms. Entity type is disclosed only to Google via internal contracts (MVA), never to customers.

### Architecture Diagram Label Fix
**File:** `docs/marketplace-architecture-variant1.html` line 289  
**Before:** `React frontend`  
**After:** `Django UI`  
**Note:** The submitted file `variant2.html` never had this issue; variant1 is kept as backup.

---

## GCP Marketplace Technical Requirements (Research Complete)

### Project Setup

Google does **not** link `b2b-recs` in Partner Hub. Instead, you must create a **new, dedicated** project for the Marketplace integration.

| Project | Purpose | Action |
|---|---|---|
| `b2b-recs` | App infrastructure (Django, Cloud Run, BigQuery, Vertex AI) | **Leave as-is.** Do not move or change. |
| `recs-studio-public` (new) | Marketplace listing, billing APIs, procurement, Producer Portal | **Create after eligibility confirmed.** |

### IAM Roles Required (on `recs-studio-public`)

After creating the project, grant these roles to Google-managed service accounts:

| Service Account | Required Role(s) |
|---|---|
| `cloud-commerce-marketplace-onboarding@twosync-src.google.com` | `roles/editor` + `roles/servicemanagement.admin` |
| `cloud-commerce-producer@system.gserviceaccount.com` | `roles/servicemanagement.configEditor` |
| `cloud-commerce-procurement@system.gserviceaccount.com` | `roles/servicemanagement.admin` — OR both `roles/servicemanagement.serviceConsumer` + `roles/servicemanagement.serviceController` |

### Onboarding Workflow (after eligibility confirmed)

1. Create `recs-studio-public` project
2. Grant IAM roles to Google service accounts
3. Submit the **Cloud Marketplace Project Info Form**
4. Wait for Google Partner Engineer to enable **Producer Portal**
5. Access Producer Portal at `https://console.cloud.google.com/producer-portal?project=recs-studio-public`
6. Build listing, set pricing, integrate SaaS fulfillment API
7. Submit for review

### Agency Jurisdictions (relevant to Ukraine)

Per [Google Cloud Marketplace Agency Jurisdictions](https://cloud.google.com/terms/marketplace-agency-jurisdictions), the 14 Vendor Agency Countries are:

United States, Canada, Israel, France, Germany, United Kingdom, Belgium, Italy, Luxembourg, Netherlands, Poland, Spain, Sweden, Switzerland.

**Ukraine is not on this list.** For non-agency vendors, Google acts as the **merchant of record**, not payment agent. This is a different transaction model but does not automatically block listing.

Sources:
- [Setting up your SaaS product](https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas/set-up-environment)
- [Requirements for Google Cloud Marketplace](https://docs.cloud.google.com/marketplace/docs/partners/get-started)
- [Transaction models](https://docs.cloud.google.com/marketplace/docs/partners/transaction-models)

---

## Next Steps

### Immediate (as of 2026-06-10)

1. **Await response** from Google Cloud Marketplace Team on Case 72148641 (follow-up clarifications sent 2026-06-10).
2. **Capture product screenshots** — Platform dashboard, ETL wizard, training pipeline, deployment interface. Marketplace listings require at least **3–5 screenshots**. Compress each to < 500 KB.

### Done Today (2026-06-10)

| # | Task | Status |
|---|---|---|
| ✅ | Responded to Google follow-up questions (Case 72148641) | Sent clarifications + updated architecture diagram |
| ✅ | Architecture diagram updated | `Customer Infrastructure` → `Customer Data Sources`; Vertex AI details clarified; no-deployment note added |

### Done Earlier (2026-06-06)

| # | Task | Status |
|---|---|---|
| ✅ | Terms of Service updated + deployed | Live at https://recs.studio/terms/ |
| ✅ | Privacy Policy updated + deployed | Live at https://recs.studio/privacy/ |
| ✅ | Website deploy script bug fixed | `--project` flag added to `describe` command |
| ✅ | Architecture diagram label corrected | `React frontend` → `Django UI` in variant1.html |
| ✅ | USD receiving capability confirmed | Existing SWIFT account handles USD payments from EU clients |

### Short-term (after Solution Validation approval)

3. **Await Product Validation Letter** (2–4 business days after submission acceptance)
4. **Await Producer Portal access email** from Google
5. **Create `recs-studio-public` project** and grant IAM roles to Google service accounts
6. **Submit Cloud Marketplace Project Info Form**
7. **Configure Payment Account** in Producer Portal
8. **Build listing** in Producer Portal
9. **Integrate SaaS fulfillment API** (sign-up flow, purchase tokens, billing metering)

### Medium-term (next 1–3 months)

10. **Submit listing for Google review**
11. **Address feedback**
12. **Launch**

---

## Important Notes

- **Keep Resend for transactional emails.** The website's demo request form (`website/views.py`) sends emails via Resend API. Do not delete Resend DNS records (`resend._domainkey`, `send` SPF, `dc-fd741b8612._spfm.send`) or the `RESEND_API_KEY` secret from GCP Secret Manager.

- **DMARC report address.** Currently reports go to `dmarc_rua@onsecureserver.net` (GoDaddy's service). Consider updating `_dmarc` to `rua=mailto:d.kulish@recs.studio` to receive reports directly.

- **Banking.** Google Workspace billing uses the personal/self-employed bank account. The Marketplace payout will go to a **Payment Account** configured in the Producer Portal (minimum payout $100 USD/month). Research USD-receiving options for Ukrainian ФОП (e.g., bank SWIFT transfer, Payoneer, Wise) so you are ready to configure the account when the portal opens.

- **Marketplace project vs. app project.** Do not confuse `b2b-recs` (your app) with `recs-studio-public` (the Marketplace storefront). They are separate projects with separate purposes. The app project stays private; the public project is only for Google's billing and procurement APIs.

- **SEO / Email deliverability.** The branded email signature (`website/email_signature.html`) references `dkulish@recs.studio`. If the primary contact email changes to `d.kulish@recs.studio`, update the signature HTML and re-copy it to Gmail.

---

## Resources

| Link | Purpose |
|---|---|
| [admin.google.com](https://admin.google.com) | Google Workspace Admin console |
| [partner.cloud.google.com](https://partner.cloud.google.com) | **Partner Hub** (now accessible!) |
| [cloud.google.com/partners](https://cloud.google.com/partners) | Google Cloud Partner program |
| [cloud.google.com/marketplace/docs/partners](https://cloud.google.com/marketplace/docs/partners) | Marketplace ISV documentation |
| [godaddy.com](https://godaddy.com) | DNS management |
| [resend.com](https://resend.com) | Transactional email service |

---

**Last Updated:** 2026-06-10

