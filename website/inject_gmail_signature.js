// Inject Option D signature into Gmail's signature editor.
//
// Steps:
//   1. Gmail → Settings → General → Signature section
//   2. Create a new signature (or select existing) for dkulish@recs.studio
//   3. Click INTO the signature editor box so it's focused
//   4. Open Chrome DevTools: Cmd+Option+J
//   5. Paste this entire script into the Console tab and press Enter
//   6. Scroll down and click "Save Changes"

const signatureHTML = `<table cellpadding="0" cellspacing="0" border="0" style="border:2px solid #1f2937; border-radius:16px; padding:20px 24px; font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; width:100%; max-width:520px;"><tr><td style="vertical-align:middle; padding-right:24px; width:88px; text-align:center;"><img src="https://storage.googleapis.com/recs-studio-public/logo/recs_logo.png" alt="Recs Studio" width="64" height="55" style="display:block; margin:0 auto; border:0; width:64px; height:auto;"><div style="font-size:10px; font-weight:700; color:#374151; margin-top:4px; white-space:nowrap;">Recs Studio</div></td><td style="vertical-align:middle; border-left:1px solid #e5e7eb; padding-left:20px;"><div style="font-size:18px; font-weight:700; color:#1e3a8a; line-height:1.3;">Dmytro Kulish</div><div style="font-size:13px; font-weight:500; color:#374151; line-height:1.4; margin-top:3px;">Founder</div><div style="font-size:13px; color:#6b7280; line-height:1.4; margin-top:3px;"><a href="mailto:dkulish@recs.studio" style="color:#6b7280; text-decoration:none;">dkulish@recs.studio</a>&nbsp;·&nbsp;<a href="https://www.recs.studio" style="color:#6b7280; text-decoration:none;">www.recs.studio</a></div></td></tr></table>`;

// Find all contenteditable divs in the signature area
const editors = document.querySelectorAll('div[contenteditable="true"]');

if (editors.length === 0) {
    console.error('No signature editor found. Make sure you are on Gmail Settings → General → Signature section.');
} else {
    // Use the last contenteditable div (Gmail's signature editor is typically the last one)
    // If multiple exist, try to find the one in the signature section
    let editor = editors[editors.length - 1];

    // Try to find the signature-specific editor (inside the signature settings area)
    for (const el of editors) {
        if (el.closest('[aria-label*="ignature"]') || el.closest('.dam')) {
            editor = el;
            break;
        }
    }

    editor.innerHTML = signatureHTML;
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    console.log('Signature injected. Scroll down and click "Save Changes".');
}
