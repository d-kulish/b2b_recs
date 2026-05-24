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
| Registered business entity | **TODO** | Self-employed (sole proprietorship) registered. Need to verify if this is sufficient for the final Marketplace listing agreement, or if an LLC is required. |
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

## Current Status (as of 2026-05-24)

| Component | State |
|---|---|
| Google Workspace Business Starter | Active, billing set up |
| Gmail (`d.kulish@recs.studio`) | Working, receiving mail |
| Domain verification | Complete |
| DKIM | Authenticated |
| MX records | Cut over to Google |
| SPF | Merged (Google + Resend subdomains) |
| Resend (website emails) | Preserved and functional |
| Partner Advantage application | **Submitted; verification email received and replied** |

**Blockers:** None for Workspace setup. Waiting for Partner Advantage response after submitting company details. The main open question is whether sole proprietorship will be accepted for the final Marketplace listing.

---

## Verification Email & Reply (2026-05-24)

Google Partner Advantage sent a verification email requesting company details. The following reply was sent to `concierge-amer@google.com`:

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

**Key decisions made:**
- Used the exact legal name as registered in the Ukrainian sole proprietorship records.
- Asked explicitly about sole proprietorship eligibility for Registered Partner tier.
- Asked explicitly about Marketplace listing entity requirements (typically stricter).
- Did not volunteer GCP project details unless requested.

---

## Next Steps

### Immediate (this week)

1. **Confirm Partner program path**
   - Go to [cloud.google.com/partners](https://cloud.google.com/partners)
   - Apply for **Google Cloud Partner Advantage** → **Technology Partner** (ISV / Build track)
   - Verify whether sole proprietorship/self-employed status is accepted at the Registered Partner tier

2. **Review Marketplace ISV requirements**
   - Read the [Google Cloud Marketplace Partner Guide](https://cloud.google.com/marketplace/docs/partners)
   - Confirm if an LLC or incorporated entity is mandatory for the listing agreement

3. **Business entity decision**
   - If sole proprietorship is **not** sufficient: form an LLC (or local equivalent) before proceeding with the listing application
   - If it **is** sufficient: proceed with Partner Advantage registration using self-employed details

### Short-term (next 2-4 weeks)

4. **Complete Partner Advantage registration**
   - Fill out company profile
   - Link GCP project (`b2b-recs`)
   - Select product track: **SaaS / Managed Service** for Recs Studio

5. **Technical onboarding**
   - Review Marketplace technical requirements (integration, billing, metering)
   - Implement marketplace-specific features if needed:
     - Usage-based billing metering (if offering pay-as-you-go)
     - Sign-up flow that accepts Google Cloud purchase tokens
     - Partner Interconnect or SaaS fulfillment API integration

6. **Prepare listing materials**
   - Product description and value proposition
   - Screenshots / demo video
   - Pricing model (subscription, usage-based, or bring-your-own-license)
   - Support terms and SLA
   - Privacy policy and terms of service (review for Marketplace compliance)

### Medium-term (next 1-3 months)

7. **Submit Marketplace listing**
   - Create listing in Partner Portal
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

- **Banking.** Google Workspace billing uses the personal/self-employed bank account. If an LLC is formed, update the Workspace billing entity and payment method accordingly.

- **SEO / Email deliverability.** The branded email signature (`website/email_signature.html`) references `dkulish@recs.studio`. If the primary contact email changes to `d.kulish@recs.studio`, update the signature HTML and re-copy it to Gmail.

---

## Resources

| Link | Purpose |
|---|---|
| [admin.google.com](https://admin.google.com) | Google Workspace Admin console |
| [cloud.google.com/partners](https://cloud.google.com/partners) | Google Cloud Partner program |
| [cloud.google.com/marketplace/docs/partners](https://cloud.google.com/marketplace/docs/partners) | Marketplace ISV documentation |
| [godaddy.com](https://godaddy.com) | DNS management |
| [resend.com](https://resend.com) | Transactional email service |

---

**Last Updated:** 2026-05-24
