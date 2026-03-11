# Website App (`website/`)

The public-facing website at **recs.studio** — landing page, legal pages, and demo request form.

## Architecture

The website runs as a separate Cloud Run service (`django-app-website`) from the same Docker image as the ML platform (`django-app`). Both share the same Django codebase and database but are deployed to different regions with different resource allocations.

| | Platform (`django-app`) | Website (`django-app-website`) |
|---|---|---|
| Region | europe-central2 (Warsaw) | europe-west4 (Netherlands) |
| Domain | Cloud Run default URL | recs.studio |
| Memory / CPU | 2 Gi / 2 | 512 Mi / 1 |
| Max instances | 10 | 3 |

The website service is publicly accessible (`--allow-unauthenticated`). Authenticated users hitting the landing page are redirected to the platform dashboard.

## Pages

| URL | View | Template |
|-----|-------|----------|
| `/` | `landing` | `templates/website/landing.html` |
| `/terms/` | `terms` | `templates/website/terms.html` |
| `/privacy/` | `privacy` | `templates/website/privacy.html` |

## Request a Demo

A popup modal on the landing page collects demo requests from potential customers.

### How it works

1. User clicks "Request a Demo" (hero section button or footer link)
2. Modal opens with email (required), description (optional), and a hidden honeypot field
3. JS sends `POST /api/request-demo/` with JSON body and CSRF token
4. Backend validates, saves `DemoRequest` to the database, and sends a notification email via Resend API
5. Modal shows success message and auto-closes after 2 seconds

### Anti-spam

- **Honeypot field:** A hidden field named "company" is positioned off-screen. Bots that fill it get a silent `{"success": true}` response — no DB write, no email.
- **CSRF:** `@ensure_csrf_cookie` on the landing view ensures the CSRF cookie is set for anonymous users (no Django form on the page to trigger it otherwise).

### Email notification

- **Sender:** `Recs Studio <noreply@recs.studio>` (domain verified in Resend)
- **Recipient:** `kulish.dmytro@gmail.com` (direct to Gmail, bypasses ImprovMX forwarding for reliable delivery)
- **API key:** `RESEND_API_KEY` env var — stored in GCP Secret Manager (`resend-api-key`) and mounted to both Cloud Run services via `--set-secrets`
- **Failure handling:** Email errors are logged but don't fail the request. The database is the source of truth.

### Admin

`DemoRequest` is registered in Django admin as read-only. No add/edit permissions — submissions only come through the public form.

### Files

| File | Purpose |
|------|---------|
| `website/models.py` | `DemoRequest` model |
| `website/admin.py` | Read-only admin registration |
| `website/views.py` | `request_demo` POST endpoint |
| `website/urls.py` | `/api/request-demo/` route |
| `templates/website/landing.html` | Button, modal, JS |

## Deployment

Both services are deployed from a single script:

```bash
./deploy_django.sh
```

This builds the Docker image once and deploys it to both Cloud Run services (steps 2 and 5). The script also updates the ETL runner with the platform service URL (step 4).

**Gotcha — comma escaping:** The website's `CSRF_TRUSTED_ORIGINS` contains multiple comma-separated origins. The `gcloud run deploy --set-env-vars` flag treats commas as key-value separators by default. The script uses `^##^` as a custom delimiter prefix so commas are preserved as literal characters. Without this, the website deploy fails and the site is not updated.

### Deploying website only

If you need to redeploy only the website (e.g. after a failed deploy or to skip rebuilding):

```bash
gcloud run deploy django-app-website \
    --image gcr.io/b2b-recs/django-app \
    --region europe-west4 \
    --project b2b-recs \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "^##^CSRF_TRUSTED_ORIGINS=https://recs.studio,https://www.recs.studio,https://django-app-555035914949.europe-central2.run.app" \
    --set-secrets "RESEND_API_KEY=resend-api-key:latest" \
    --service-account "django-app@b2b-recs.iam.gserviceaccount.com"
```

### Secrets (GCP Secret Manager)

| Secret name | Env var | Used by |
|---|---|---|
| `django-db-password` | `DB_PASSWORD` | Both services |
| `django-secret-key` | `DJANGO_SECRET_KEY` | Both services |
| `resend-api-key` | `RESEND_API_KEY` | Both services (demo request notifications) |

---

# Corporate Email Setup: dkulish@recs.studio

## Overview

The `dkulish@recs.studio` business email is built from three independent services,
each handling a specific part of the email pipeline:

| Function   | Service    | Role                                      |
|------------|------------|-------------------------------------------|
| Sending    | Resend     | SMTP relay for outgoing email             |
| Receiving  | ImprovMX   | MX forwarding to Gmail                    |
| Compose/UI | Gmail web  | Primary client for sending (branded sig)  |
| Reading    | Outlook    | Desktop client for reading (Gmail via IMAP)|

## Architecture

```
Outgoing (branded):
  Gmail web (compose as dkulish@recs.studio) → Resend SMTP → recipient
  Signature auto-appended by Gmail (Option D)

Outgoing (plain, legacy):
  Outlook (compose) → Resend SMTP → recipient
  No HTML signature (Outlook doesn't support custom HTML signatures)

Incoming:
  sender → MX (ImprovMX) → forwards to kulish.dmytro@gmail.com → Gmail IMAP → Outlook
```

## Service Details

### 1. Resend (sending)

- **Account email:** dkulish@recs.studio
- **Domain:** recs.studio (verified)
- **SMTP credentials:**
  - Server: `smtp.resend.com`
  - Port: `465` (SSL)
  - Username: `resend`
  - Password: Resend API key
- **DNS records managed by Resend:**
  - TXT `resend._domainkey` — DKIM signing key
  - TXT `send` — SPF for send subdomain
  - TXT `dc-fd741b8612._spfm.send` — SPF include for Amazon SES
  - MX `send` — feedback loop for Amazon SES
- **Enable Receiving:** OFF (ImprovMX handles receiving)

### 2. ImprovMX (receiving/forwarding)

- **Account email:** kulish.dmytro@gmail.com
- **Domain:** recs.studio
- **Alias:** dkulish@recs.studio → kulish.dmytro@gmail.com
- **DNS records managed by ImprovMX:**
  - MX `@` → `mx1.improvmx.com` (priority 10)
  - MX `@` → `mx2.improvmx.com` (priority 20)
- **SPF:** included in root TXT `@` record

### 3. Outlook (email client)

- **Account type:** IMAP (manual configuration)
- **Email address:** dkulish@recs.studio
- **IMAP settings (incoming — reads from Gmail):**
  - Server: `imap.gmail.com`
  - Port: `993` (SSL)
  - Username: `kulish.dmytro@gmail.com`
  - Password: Gmail App Password
- **SMTP settings (outgoing — sends via Resend):**
  - Server: `smtp.resend.com`
  - Port: `465` (SSL)
  - Username: `resend`
  - Password: Resend API key

### 4. Gmail (compose + inbox storage)

- **Role:** primary client for composing branded emails as `dkulish@recs.studio`; also stores incoming mail forwarded by ImprovMX
- **"Send mail as" configured:** `dkulish@recs.studio` via Resend SMTP (verified)
- **Signature:** Option D (dashboard style) — auto-appended when composing as `dkulish@recs.studio`
- **App Password:** generated for Outlook IMAP access (Google Account → Security → 2-Step Verification → App Passwords)
- **Personal email (kulish.dmytro@gmail.com)** uses separate Gmail app / Apple Mail

## DNS Records (GoDaddy)

Domain: `recs.studio` (registered with GoDaddy)

### MX Records
| Name | Value                  | Priority |
|------|------------------------|----------|
| @    | mx1.improvmx.com      | 10       |
| @    | mx2.improvmx.com      | 20       |

### TXT Records
| Name                       | Value                                                              |
|----------------------------|--------------------------------------------------------------------|
| @                          | v=spf1 include:spf.improvmx.com ~all                              |
| resend._domainkey          | (DKIM public key for Resend)                                       |
| send                       | v=spf1 include:dc-fd741b8612._spfm.send.recs.studio ~all          |
| dc-fd741b8612._spfm.send  | v=spf1 include:amazonses.com ~all                                  |
| _dmarc                     | v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@... |

## Known Behaviors

- **Gmail deduplication:** If you send from `kulish.dmytro@gmail.com` to `dkulish@recs.studio`, the forwarded copy won't appear in Gmail/Outlook because Gmail suppresses duplicate Message-IDs. This only affects self-to-self testing — external senders are not affected.
- **SPF for Resend sending:** The root `@` SPF record currently only includes ImprovMX. Resend relies on its DKIM signature for deliverability. Ideally the root SPF should be: `v=spf1 include:dc-8e814c8572._spfm.recs.studio include:spf.improvmx.com ~all` (GoDaddy had issues saving this merged record).

## Accounts Summary

| Service   | Login                      | URL                        |
|-----------|----------------------------|----------------------------|
| Resend    | dkulish@recs.studio        | https://resend.com         |
| ImprovMX  | kulish.dmytro@gmail.com    | https://improvmx.com       |
| GoDaddy   | (domain registrar account) | https://godaddy.com        |
| Zoho Mail | dkulish@recs.studio        | DECOMMISSIONED             |

## Branded Email Signature

A branded HTML email signature (Option D — dashboard style with logo and label) is defined in
`website/email_signature.html`. The logo is hosted publicly on GCS.

### Logo Hosting

- **Bucket:** `gs://recs-studio-public` (us-central1, public read)
- **URL:** `https://storage.googleapis.com/recs-studio-public/logo/recs_logo.png`
- **Source file:** `static/images/recs_logo.png`

### How to Use the Signature

Outlook's signature editor does not support custom HTML properly.
Gmail web is the primary client for sending branded emails.

#### Daily use: compose in Gmail web

1. Open Gmail web → click **Compose**
2. In the "From" dropdown, select `dkulish@recs.studio`
3. The Option D signature is auto-appended

#### Gmail "Send mail as" setup (already completed)

1. Gmail → Settings → Accounts → "Send mail as" → added `dkulish@recs.studio`
2. SMTP settings: server `smtp.resend.com`, port `465` (SSL), username `resend`, password = Resend API key
3. Verified via confirmation email (arrived via ImprovMX)

#### Signature setup (already completed)

The signature was set using a clipboard-copy helper page (`website/gmail_signature_d.html`).
Open in Chrome → click "Copy Signature to Clipboard" → paste into Gmail signature editor.

**Note:** The Gmail API cannot update signatures for non-primary sendAs addresses on personal
Gmail accounts (requires Google Workspace). The clipboard-copy approach is the only reliable method.

#### Resend API (for outreach / programmatic emails)

```python
import resend

resend.api_key = "re_YOUR_API_KEY"

html = open("website/email_signature.html").read()  # or build body + signature

resend.Emails.send({
    "from": "Dmytro Kulish <dkulish@recs.studio>",
    "to": ["recipient@example.com"],
    "subject": "Your subject",
    "html": html,
})
```

### Font

The signature uses **Inter** from Google Fonts. It renders natively in Apple Mail, iOS Mail,
and Outlook.com (web). Gmail web and Outlook desktop fall back to their default sans-serif.

### Updating the Logo

```bash
gsutil cp static/images/recs_logo.png gs://recs-studio-public/logo/recs_logo.png
```

## Make.com Webhook (deprecated)

A Make.com scenario was set up during initial configuration to forward Resend webhooks to Gmail.
This is **no longer needed** since ImprovMX handles forwarding natively.
The scenario can be disabled/deleted in Make.com.
