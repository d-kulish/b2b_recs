# Corporate Email Setup: dkulish@recs.studio

## Overview

The `dkulish@recs.studio` business email is built from three independent services,
each handling a specific part of the email pipeline:

| Function   | Service    | Role                                      |
|------------|------------|-------------------------------------------|
| Sending    | Resend     | SMTP relay for outgoing email             |
| Receiving  | ImprovMX   | MX forwarding to Gmail                    |
| Inbox/UI   | Outlook    | Desktop email client (reads Gmail via IMAP)|

## Architecture

```
Outgoing:
  Outlook (compose) → Resend SMTP → recipient
                       (dkulish@recs.studio)

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

### 4. Gmail (backend inbox storage)

- **Role:** invisible backend — stores incoming mail forwarded by ImprovMX
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

Outlook's signature editor does not support custom HTML properly — copy-pasting from a browser
loses styling (rounded corners, fonts, spacing). Two approaches that work:

#### Option A: Gmail "Send mail as" (recommended for daily use)

1. In Gmail → Settings → Accounts → "Send mail as" → Add another email
2. Enter `dkulish@recs.studio`
3. SMTP settings: server `smtp.resend.com`, port `465` (SSL), username `resend`, password = Resend API key
4. Confirm via verification email (arrives back to Gmail via ImprovMX)
5. In Gmail → Settings → General → Signature → create new signature
6. Paste the Option D signature block from `website/email_signature.html` (select in browser, Cmd+C, paste into Gmail signature editor — Gmail preserves HTML styling correctly)
7. Assign it as default for the `dkulish@recs.studio` identity

#### Option B: Resend API (for outreach / programmatic emails)

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
