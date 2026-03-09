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

**Gmail API limitation:** The Gmail API cannot update signatures for non-primary sendAs
addresses on personal Gmail accounts (requires Google Workspace domain-wide delegation).
The clipboard-copy approach is the only reliable method.

**GCP setup for Gmail API (completed, for reference):**
- Gmail API enabled in project `b2b-recs`
- OAuth consent screen configured (External, test user: `kulish.dmytro@gmail.com`)
- OAuth client: Desktop app "set-gmail-signature" (credentials in `.gcp/gmail_oauth_client.json`)
- Script `website/set_gmail_signature.py` can read sendAs config but cannot write signatures for non-primary addresses

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
