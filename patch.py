import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_bufmodal2')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("File: {} chars\n".format(len(html)))

# ═══════════════════════════════════════════════════════════════
# Locate the current openEditCredsModal function
# ═══════════════════════════════════════════════════════════════
print("[1] Locating openEditCredsModal...")

# Match from "async function openEditCredsModal(service) {" to the closing "}"
# of that function — we stop at the line that starts with "}" at column 0
# and is followed by a blank line or another function/statement.
pattern = re.compile(
    r"async function openEditCredsModal\(service\) \{[\s\S]*?\n\}",
    re.DOTALL
)

match = pattern.search(html)
if not match:
    print("  FAIL — could not locate openEditCredsModal")
    sys.exit(1)

old_block = match.group(0)
print("  OK — found function ({} chars)".format(len(old_block)))

# ═══════════════════════════════════════════════════════════════
# Replace with buffer-aware version
# ═══════════════════════════════════════════════════════════════
print("\n[2] Replacing with buffer-aware version...")

new_block = '''async function openEditCredsModal(service) {
    try {
        const tool = TOOLS[service];
        if (!tool) { toast("Unknown tool: " + service, 'error'); return; }

        // Fetch existing credentials (safe — 404 returns empty object)
        let existing = {};
        try {
            const r = await fetch(`/credentials/${service}`);
            if (r.ok) existing = await r.json();
        } catch (_) { /* not configured yet — that's fine */ }

        // Remove any prior modal
        document.querySelectorAll('.modal-overlay').forEach(m => m.remove());

        let fieldsHtml;

        if (service === 'buffer') {
            // ── Buffer: live org/channel dropdowns ──
            let bs = { organizations: [], channels: [], error: null, api_key_set: false };
            try {
                const bres = await fetch('/buffer/channels');
                if (bres.ok) bs = await bres.json();
            } catch (e) { bs.error = e.message; }

            const apiKeyVal = (existing['api_key'] || '').toString().replace(/"/g, '&quot;');
            const currentOrgId = existing['organization_id'] || '';
            const currentChannelId = existing['channel_id'] || '';

            fieldsHtml = `<label>api key</label>
                <input name="api_key" value="${apiKeyVal}" autocomplete="off" placeholder="from publish.buffer.com/settings/api" />`;

            if (bs.organizations && bs.organizations.length > 0) {
                const opts = bs.organizations.map(o =>
                    `<option value="${o.id}" ${o.id === currentOrgId ? 'selected' : ''}>${o.name || '(unnamed)'}</option>`
                ).join('');
                fieldsHtml += `<label style="margin-top:12px;">organization</label>
                    <select name="organization_id" class="pro-input" style="width:100%; height:38px;">
                        <option value="">-- choose organization --</option>
                        ${opts}
                    </select>`;
            } else {
                fieldsHtml += `<label style="margin-top:12px;">organization id</label>
                    <input name="organization_id" value="${(currentOrgId || '').replace(/"/g, '&quot;')}" autocomplete="off" />`;
                if (bs.error) {
                    fieldsHtml += `<div style="font-size:10px; color:#f59e0b; margin-top:4px;">${bs.error}</div>`;
                } else if (!bs.api_key_set) {
                    fieldsHtml += `<div style="font-size:10px; color:#94a3b8; margin-top:4px;">Save API key first, then re-open to load organizations.</div>`;
                }
            }

            if (bs.channels && bs.channels.length > 0) {
                const opts = bs.channels.map(c =>
                    `<option value="${c.id}" ${c.id === currentChannelId ? 'selected' : ''}>${c.service.toUpperCase()} — ${c.name}</option>`
                ).join('');
                fieldsHtml += `<label style="margin-top:12px;">channel to post to</label>
                    <select name="channel_id" class="pro-input" style="width:100%; height:38px;">
                        <option value="">-- choose channel --</option>
                        ${opts}
                    </select>`;
            } else {
                fieldsHtml += `<label style="margin-top:12px;">channel id</label>
                    <input name="channel_id" value="${(currentChannelId || '').replace(/"/g, '&quot;')}" autocomplete="off" />`;
            }
        } else {
            // ── Generic: one input per credential key ──
            fieldsHtml = tool.creds.length > 0
                ? tool.creds.map(k => {
                    const val = (existing[k] || '').toString().replace(/"/g, '&quot;');
                    return `<label>${k.replace(/_/g, ' ')}</label><input name="${k}" value="${val}" autocomplete="off" />`;
                }).join('')
                : '<p class="text-xs text-slate-500">This tool requires no credentials.</p>';
        }

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

        overlay.innerHTML = `
            <div class="modal">
                <h2>${getToolIconHtml(service, 16).replace('<i ', '<i class="mr-2" ')}${tool.label} Credentials</h2>
                <form id="credsForm">
                    ${fieldsHtml}
                    <div class="modal-buttons">
                        <button type="button" class="modal-btn secondary" id="cancelCreds">Cancel</button>
                        <button type="submit" class="modal-btn primary">Save</button>
                    </div>
                </form>
            </div>`;
        document.body.appendChild(overlay);

        document.getElementById('cancelCreds').addEventListener('click', () => overlay.remove());

        document.getElementById('credsForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const creds = {};
            tool.creds.forEach(k => { creds[k] = form.elements[k].value; });
            try {
                const res = await fetch(`/credentials/${service}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(creds),
                });
                if (res.ok) {
                    toast(`${tool.label} saved`, 'success');
                    overlay.remove();
                    setTimeout(openCredentialsPanel, 100);
                } else {
                    toast('Save failed: ' + res.status, 'error');
                }
            } catch (err) {
                toast('Save error: ' + err.message, 'error');
            }
        });
    } catch (e) {
        console.error("openEditCredsModal failed:", e);
        toast("Failed to open editor: " + e.message, 'error', 4000);
    }
}'''

html = html.replace(old_block, new_block, 1)
print("  OK — openEditCredsModal replaced with buffer-aware version")

# ═══════════════════════════════════════════════════════════════
# Write + verify
# ═══════════════════════════════════════════════════════════════
with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print("\nWrote {} chars".format(len(html)))

final = open(HTML, 'r', encoding='utf-8').read()

print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

checks = [
    ("buffer branch exists",        "if (service === 'buffer')" in final),
    ("fetches /buffer/channels",    "fetch('/buffer/channels')" in final),
    ("org dropdown",                'name="organization_id" class="pro-input"' in final),
    ("channel dropdown",            'name="channel_id" class="pro-input"' in final),
    ("generic ternary preserved",   "tool.creds.length > 0" in final),
    ("one openEditCredsModal",      final.count("async function openEditCredsModal(service)") == 1),
    ("save handler intact",         "method: 'PUT'" in final or 'method: "PUT"' in final),
]

all_ok = True
for name, ok in checks:
    print("  [{}] {}".format("OK  " if ok else "FAIL", name))
    if not ok: all_ok = False

print()
if all_ok:
    print("=" * 55)
    print("PATCH COMPLETE")
    print("=" * 55)
    print("\nNext:")
    print("  git add public/index.html")
    print("  git commit -m 'Buffer: replace openEditCredsModal with buffer-aware version'")
    print("  git push origin main")
else:
    print("Review FAIL lines. Backup: index.html.backup_bufmodal2")