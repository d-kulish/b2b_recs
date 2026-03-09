"""
Set Gmail signature for dkulish@recs.studio via Gmail API.

Prerequisites:
    1. OAuth consent screen configured in GCP project b2b-recs
    2. Desktop OAuth client JSON saved as website/.gmail_oauth_client.json

Usage:
    python website/set_gmail_signature.py
"""

import json
import sys
from pathlib import Path

import requests
from google_auth_oauthlib.flow import InstalledAppFlow

SEND_AS_EMAIL = "dkulish@recs.studio"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.settings.sharing",
]

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SIGNATURE_FILE = SCRIPT_DIR / "email_signature.html"
CLIENT_SECRET_FILE = PROJECT_ROOT / ".gcp" / "gmail_oauth_client.json"
TOKEN_FILE = PROJECT_ROOT / ".gcp" / "gmail_token.json"

START_MARKER = "<!-- ===== SIGNATURE D \u2014 copy from here ===== -->"
END_MARKER = "<!-- ===== END SIGNATURE D ===== -->"


def extract_signature_html() -> str:
    """Extract Option D signature block from email_signature.html."""
    content = SIGNATURE_FILE.read_text()
    start = content.find(START_MARKER)
    end = content.find(END_MARKER)
    if start == -1 or end == -1:
        print(f"ERROR: Could not find signature markers in {SIGNATURE_FILE}")
        sys.exit(1)
    html = content[start + len(START_MARKER) : end].strip()
    print(f"Extracted signature HTML ({len(html)} chars)")
    return html


def get_credentials():
    """Authenticate via OAuth2 installed-app flow. Caches token for reuse."""
    if not CLIENT_SECRET_FILE.exists():
        print(f"ERROR: OAuth client credentials not found at {CLIENT_SECRET_FILE}")
        print("Download from: https://console.cloud.google.com/apis/credentials?project=b2b-recs")
        sys.exit(1)

    # Try cached token first
    if TOKEN_FILE.exists():
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds.valid:
            print("Using cached credentials.")
            return creds
        if creds.expired and creds.refresh_token:
            import google.auth.transport.requests

            creds.refresh(google.auth.transport.requests.Request())
            TOKEN_FILE.write_text(creds.to_json())
            print("Refreshed cached credentials.")
            return creds

    # Full OAuth flow — opens browser
    print("Opening browser for Google sign-in...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    # Cache for next time
    TOKEN_FILE.write_text(creds.to_json())
    print("Authenticated and token cached.")
    return creds


def get_current_send_as(credentials) -> dict:
    """Fetch current sendAs config to verify access."""
    resp = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs/{SEND_AS_EMAIL}",
        headers={"Authorization": f"Bearer {credentials.token}"},
    )
    if resp.status_code == 404:
        print(f"ERROR: '{SEND_AS_EMAIL}' is not configured as a Send-As address in Gmail.")
        print("Complete Gmail 'Send mail as' setup first (see mail.md, Option A steps 1-4).")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"ERROR: Gmail API returned {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp.json()


def set_signature(credentials, signature_html: str) -> dict:
    """PATCH the sendAs signature via Gmail API."""
    resp = requests.patch(
        f"https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs/{SEND_AS_EMAIL}",
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        },
        data=json.dumps({"signature": signature_html}),
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to update signature. Status {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp.json()


def main():
    print(f"Setting Gmail signature for {SEND_AS_EMAIL}\n")

    # 1. Extract signature HTML
    signature_html = extract_signature_html()

    # 2. Authenticate
    credentials = get_credentials()
    print()

    # 3. Verify sendAs exists
    print(f"Checking '{SEND_AS_EMAIL}' sendAs configuration...")
    current = get_current_send_as(credentials)
    print(f"  Display name: {current.get('displayName', '(not set)')}")
    current_sig = current.get("signature", "")
    print(f"  Current signature: {'(empty)' if not current_sig else f'{len(current_sig)} chars'}")
    print()

    # 4. Set the signature
    print("Updating signature...")
    result = set_signature(credentials, signature_html)
    print(f"  New signature: {len(result.get('signature', ''))} chars")
    print(f"\nDone. Signature for '{SEND_AS_EMAIL}' has been updated.")


if __name__ == "__main__":
    main()
