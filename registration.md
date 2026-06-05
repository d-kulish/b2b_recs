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

### Immediate (MVA signed — awaiting Producer Portal)

1. ~~**Reply to Agent JM**~~ — ✅ Done (case 71883638 closed)
2. ~~**Open new Partner Support case**~~ — ✅ Done (2026-06-04, case 71961480)
3. ~~**Sign Marketplace Vendor Agreement**~~ — ✅ Done (2026-06-05)
4. **Await Producer Portal access email** — ⏳ In progress
   - Google states: "If you're a new partner, you'll receive instructions via email to gain access to Producer Portal."
   - Check `d.kulish@recs.studio` inbox (including spam) over the next 1-3 business days.

### Parallel Prep (can do now)

While waiting for the portal, these tasks don't depend on it:

5. **Update Terms of Service and Privacy Policy** (`templates/website/terms.html`, `privacy.html`) — these will serve as your **Product EULA** for Marketplace customers.
6. **Draft the listing copy** — Product name, one-line description, detailed description, key features list, category tags.
7. **Capture screenshots** — Platform dashboard, ETL wizard, training pipeline, deployment interface. Marketplace listings require at least **3–5 screenshots**.
8. **Plan your pricing model** — Subscription vs. usage-based vs. BYOL? Free trial? This affects the fulfillment API integration you'll need to build.
9. **Research USD receiving options for Ukrainian ФОП** — You'll need a **Payment Account** in the Producer Portal. Common options: direct SWIFT transfer to Ukrainian bank, Payoneer, Wise Business. Check which ones your bank supports for incoming USD business transfers.

### Short-term (after Producer Portal access)

11. **Create `recs-studio-public` project**
12. **Grant IAM roles** to Google service accounts
13. **Submit Cloud Marketplace Project Info Form**
14. **Configure Payment Account** in Producer Portal
15. **Build listing** in Producer Portal
16. **Integrate SaaS fulfillment API** (sign-up flow, purchase tokens, billing metering)

### Medium-term

17. **Submit listing for Google review**
18. **Address feedback**
19. **Launch**

### Short-term (next 2-4 weeks)

4. **Start Marketplace listing application**
   - Select product track: **SaaS / Managed Service**
   - Begin listing draft in Partner Hub

5. **Technical onboarding**
   - Review [Marketplace SaaS fulfillment requirements](https://cloud.google.com/marketplace/docs/partners)
   - Plan integration for:
     - Sign-up flow accepting Google Cloud purchase tokens
     - Usage-based billing metering (if offering pay-as-you-go)
     - Partner Interconnect or SaaS fulfillment API

6. **Prepare listing materials**
   - Product description and value proposition
   - Screenshots / demo video
   - Pricing model (subscription, usage-based, or bring-your-own-license)
   - Support terms and SLA
   - Privacy policy and terms of service (review for Marketplace compliance)

### Medium-term (next 1-3 months)

7. **Submit Marketplace listing**
   - Complete listing draft in Partner Portal
   - Submit for Google review
   - Address any technical or compliance feedback

8. **Post-launch**
   - Monitor Marketplace analytics
   - Engage with Google Cloud field teams for co-selling
   - Maintain partner status (certifications, customer references if required)

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

**Last Updated:** 2026-06-05

