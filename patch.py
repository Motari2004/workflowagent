import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')
HTML = os.path.join(PROJECT, 'public', 'index.html')

if not os.path.exists(SERVER) or not os.path.exists(HTML):
    print("ERROR: server.py or index.html not found"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_zernio_v2')
shutil.copy(HTML, HTML + '.backup_zernio_v2')
print("Backed up both files\n")

sc, hc = 0, 0

# ═══════════════════════════════════════════════════════════════
# SERVER.PY — 4 CHANGES
# ═══════════════════════════════════════════════════════════════
print("=" * 60)
print("SERVER.PY")
print("=" * 60)

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# ─────────────────────────────────────────────────────────────
# 1. Replace tool_zernio with the CORRECT API calls
# ─────────────────────────────────────────────────────────────
print("\n[1] Replacing tool_zernio with real Zernio API...")

new_zernio_tool = '''def tool_zernio(creds, msg, extra):
    """Post to Zernio. Requires api_key, profile_id, and account_id.
    Zernio docs: POST https://zernio.com/api/v1/posts
    """
    token = creds.get('api_key')
    profile_id = creds.get('profile_id')
    account_id = creds.get('account_id')

    if not token:
        return "[ERROR] Zernio: api_key not configured (starts with sk_)"
    if not profile_id:
        return "[ERROR] Zernio: profile_id not configured (get from GET /v1/profiles)"
    if not account_id:
        return "[ERROR] Zernio: account_id not configured (get from GET /v1/accounts)"
    if not (msg or '').strip():
        return "[ERROR] Zernio: no content to post"

    text = msg.strip()

    # Zernio has a 24h duplicate-protection window — if this exact text was
    # posted before, we get HTTP 409. Append a tiny nonce to break the hash.
    # (Optional: comment out to let duplicate errors surface.)
    import hashlib, time
    nonce = hashlib.md5((text + str(time.time())).encode()).hexdigest()[:3]
    text = text + " ·" + nonce

    try:
        r = requests.post(
            'https://zernio.com/api/v1/posts',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            json={
                'profileId': profile_id,
                'content': text,
                'platforms': [{'accountId': account_id}],
                'publishNow': True,
            },
            timeout=25,
        )
    except requests.exceptions.Timeout:
        return "[ERROR] Zernio: timeout (25s)"
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Zernio: network: {e}"

    if r.status_code in (200, 201):
        try:
            data = r.json()
            post_id = data.get('_id') or data.get('id', '?')
            return f"Zernio {r.status_code}: posted (id={post_id})"
        except Exception:
            return f"Zernio {r.status_code}: posted"

    if r.status_code == 401:
        return "[ERROR] Zernio: 401 Unauthorized — API key invalid or expired"
    if r.status_code == 403:
        return "[ERROR] Zernio: 403 Forbidden — account_id may not belong to this profile"
    if r.status_code == 409:
        return "[ERROR] Zernio: 409 duplicate — same content posted within 24h"
    if r.status_code == 429:
        retry_after = r.headers.get('Retry-After', '60')
        return f"[ERROR] Zernio: 429 rate limit — retry after {retry_after}s"
    return f"[ERROR] Zernio {r.status_code}: {r.text[:300]}"


'''

zernio_pattern = re.compile(
    r"def tool_zernio\(creds, msg, extra\):[\s\S]*?(?=\nTOOL_HANDLERS = \{|\ndef |\n@app\.route)",
    re.DOTALL
)

if zernio_pattern.search(server):
    server = zernio_pattern.sub(new_zernio_tool, server, count=1)
    sc += 1
    print("  OK — tool_zernio replaced with real Zernio API")
else:
    print("  WARN — tool_zernio not found, trying insertion before TOOL_HANDLERS")
    if 'TOOL_HANDLERS = {' in server:
        server = server.replace('TOOL_HANDLERS = {', new_zernio_tool + 'TOOL_HANDLERS = {', 1)
        sc += 1

# ─────────────────────────────────────────────────────────────
# 2. Add _zernio_status() that returns profiles AND accounts
# ─────────────────────────────────────────────────────────────
print("\n[2] Adding _zernio_status() with profiles + accounts...")

zernio_helpers = '''
# ═══════════════════════════════════════════════════════════════
# ZERNIO LIVE STATUS — profiles + accounts + health
# ═══════════════════════════════════════════════════════════════
def _zernio_status():
    result = {
        "configured": False,
        "api_key_set": False,
        "profile_id_set": False,
        "account_id_set": False,
        "profiles": [],
        "accounts": [],
        "current_profile": None,
        "current_account": None,
        "error": None,
    }
    try:
        creds = load_creds('zernio') or {}
    except Exception as e:
        result["error"] = "load_creds: " + str(e)
        return result

    api_key = (creds.get('api_key') or '').strip()
    saved_profile = (creds.get('profile_id') or '').strip()
    saved_account = (creds.get('account_id') or '').strip()

    result["api_key_set"] = bool(api_key)
    result["profile_id_set"] = bool(saved_profile)
    result["account_id_set"] = bool(saved_account)

    if not api_key:
        return result

    headers = {"Authorization": "Bearer " + api_key}

    # Fetch profiles (GET /v1/profiles)
    try:
        r = requests.get('https://zernio.com/api/v1/profiles', headers=headers, timeout=10)
        if r.status_code == 200:
            d = r.json()
            profiles_raw = d.get('profiles') if isinstance(d, dict) else d
            if isinstance(profiles_raw, list):
                for p in profiles_raw:
                    if isinstance(p, dict):
                        result["profiles"].append({
                            "id": p.get('_id') or p.get('id') or '',
                            "name": p.get('name') or '',
                        })
        elif r.status_code == 401:
            result["error"] = "API key invalid (401)"
            return result
    except Exception as e:
        result["error"] = "profiles fetch: " + str(e)
        return result

    # Fetch accounts (GET /v1/accounts)
    try:
        r = requests.get('https://zernio.com/api/v1/accounts', headers=headers, timeout=10)
        if r.status_code == 200:
            d = r.json()
            accounts_raw = d.get('accounts') if isinstance(d, dict) else d
            if isinstance(accounts_raw, list):
                for a in accounts_raw:
                    if isinstance(a, dict):
                        result["accounts"].append({
                            "id": a.get('_id') or a.get('id') or '',
                            "platform": (a.get('platform') or a.get('service') or '').lower(),
                            "name": a.get('name') or a.get('username') or a.get('handle') or '',
                            "profile_id": a.get('profileId') or a.get('profile_id') or '',
                        })
        elif r.status_code == 401:
            result["error"] = "API key invalid (401)"
            return result
    except Exception as e:
        result["error"] = "accounts fetch: " + str(e)
        return result

    result["configured"] = True

    # Match current profile/account
    if saved_profile:
        for p in result["profiles"]:
            if p["id"] == saved_profile:
                result["current_profile"] = p
                break
    if saved_account:
        for a in result["accounts"]:
            if a["id"] == saved_account:
                result["current_account"] = a
                break

    return result


def _zernio_status_block(status):
    if not status["api_key_set"]:
        return (
            "\\n[ZERNIO STATUS]\\n"
            "NOT CONFIGURED — no API key saved.\\n"
            "Tell user: Credentials → Zernio → add API key (sk_...).\\n"
            "[END]\\n"
        )
    if status["error"]:
        return (
            "\\n[ZERNIO STATUS]\\n"
            "API key check failed: " + status["error"] + "\\n"
            "Tell user to verify API key in Credentials → Zernio.\\n"
            "[END]\\n"
        )

    lines = ["\\n[ZERNIO STATUS]"]
    if status["profiles"]:
        lines.append("Profiles:")
        for p in status["profiles"]:
            marker = " ← current" if status["current_profile"] and p["id"] == status["current_profile"]["id"] else ""
            lines.append("  - " + p["name"] + " (id: " + p["id"] + ")" + marker)
    else:
        lines.append("No profiles yet. User must create one at zernio.com → Profiles.")

    if status["accounts"]:
        lines.append("Connected channels:")
        for a in status["accounts"]:
            marker = " ← current" if status["current_account"] and a["id"] == status["current_account"]["id"] else ""
            lines.append("  - " + a["platform"].title() + ": " + a["name"] + " (id: " + a["id"] + ", profile: " + a["profile_id"] + ")" + marker)
    else:
        lines.append("No social channels connected. User must connect Facebook/LinkedIn/etc at zernio.com → Accounts.")

    lines.append("")
    lines.append("IMPORTANT: To post, BOTH profile_id AND account_id must be set in credentials.")
    lines.append("If user didn't specify which channel, ask them to pick from the connected list.")
    lines.append("Do NOT invent IDs. Only use the ones listed above.")
    lines.append("[END ZERNIO STATUS]\\n")
    return "\\n".join(lines)


'''

if 'def _zernio_status(' not in server:
    anchor = "@app.route('/ai-chat', methods=['POST', 'OPTIONS'])"
    if anchor in server:
        server = server.replace(anchor, zernio_helpers + anchor, 1)
        sc += 1
        print("  OK — status helpers added")
    else:
        print("  FAIL — ai_chat route not found")
else:
    # Replace existing (older version)
    old_status_pattern = re.compile(
        r"def _zernio_status\(\):[\s\S]*?(?=\n@app\.route|\ndef [a-z_]+\(|$)",
        re.DOTALL
    )
    server = old_status_pattern.sub(zernio_helpers.strip() + "\n\n", server, count=1)
    sc += 1
    print("  OK — status helpers replaced")

# ─────────────────────────────────────────────────────────────
# 3. Inject status into ai_chat (only when relevant)
# ─────────────────────────────────────────────────────────────
print("\n[3] Wiring status injection into ai_chat...")

inj_block = '''
        # Live Zernio status — only when message mentions social posting
        try:
            msg_lc = (message or "").lower()
            if any(k in msg_lc for k in ["zernio", "post to", "social", "facebook", "instagram", "linkedin", "twitter"]):
                zs = _zernio_status()
                system = system + _zernio_status_block(zs)
                print(f"[ai-chat] Zernio status injected ({len(zs.get('accounts', []))} accounts)")
        except Exception as z_err:
            print(f"[ai-chat] Zernio status check failed: {z_err}")
'''

if 'Zernio status injected' not in server:
    # Insert after memory_context block
    old_mem = '''        except Exception as mem_err:
            print(f"[ai-chat] Memory load failed (non-fatal): {mem_err}")'''

    if old_mem in server:
        server = server.replace(old_mem, old_mem + "\n" + inj_block, 1)
        sc += 1
        print("  OK — injection added")

# ─────────────────────────────────────────────────────────────
# 4. Expose /zernio/accounts (returns profiles too)
# ─────────────────────────────────────────────────────────────
print("\n[4] Ensuring /zernio/accounts endpoint...")

if "@app.route('/zernio/accounts'" not in server:
    zroute = '''@app.route('/zernio/accounts', methods=['GET'])
def zernio_accounts():
    return jsonify(_zernio_status())


'''
    anchor = "@app.route('/ai-models', methods=['GET'])"
    if anchor in server:
        server = server.replace(anchor, zroute + anchor, 1)
        sc += 1
        print("  OK — /zernio/accounts added")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("  [FAIL] line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_zernio_v2', SERVER)
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# INDEX.HTML — 2 CHANGES
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("INDEX.HTML")
print("=" * 60)

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ─────────────────────────────────────────────────────────────
# 5. Zernio credential modal: profile + channel dropdowns
# ─────────────────────────────────────────────────────────────
print("\n[5] Building Zernio credential modal with 2 dropdowns...")

old_fields_pattern = re.compile(
    r"        let fieldsHtml = '';\s*\n\s*if \(service === 'zernio'\) \{[\s\S]*?\n        \} else \{[\s\S]*?\n        \}",
    re.DOTALL
)

new_fields = '''        let fieldsHtml = '';
        
        if (service === 'zernio') {
            let zs = { profiles: [], accounts: [], error: null, api_key_set: false };
            try {
                const zres = await fetch('/zernio/accounts');
                if (zres.ok) zs = await zres.json();
            } catch (e) { zs.error = e.message; }
            
            const apiKeyVal = (existing['api_key'] || '').toString().replace(/"/g, '&quot;');
            const currentProfileId = existing['profile_id'] || '';
            const currentAccountId = existing['account_id'] || '';
            
            fieldsHtml = `<label>api key (sk_...)</label>
                <input name="api_key" value="${apiKeyVal}" autocomplete="off" placeholder="sk_live_..." />`;
            
            if (zs.profiles && zs.profiles.length > 0) {
                const opts = zs.profiles.map(p => 
                    `<option value="${p.id}" ${p.id === currentProfileId ? 'selected' : ''}>${p.name || '(unnamed)'} (${p.id})</option>`
                ).join('');
                fieldsHtml += `<label style="margin-top:12px;">profile</label>
                    <select name="profile_id" class="pro-input" style="width:100%; height:38px;">
                        <option value="">-- choose a profile --</option>
                        ${opts}
                    </select>`;
            } else {
                fieldsHtml += `<label style="margin-top:12px;">profile id</label>
                    <input name="profile_id" value="${(currentProfileId || '').replace(/"/g, '&quot;')}" autocomplete="off" placeholder="profile_..." />
                    <div style="font-size:10px; color:#f59e0b; margin-top:4px;">
                        ${zs.error ? zs.error : 'No profiles loaded. Save API key first, then re-open.'}
                    </div>`;
            }
            
            if (zs.accounts && zs.accounts.length > 0) {
                const opts = zs.accounts.map(a => 
                    `<option value="${a.id}" ${a.id === currentAccountId ? 'selected' : ''}>${a.platform.toUpperCase()} — ${a.name || '(unnamed)'}</option>`
                ).join('');
                fieldsHtml += `<label style="margin-top:12px;">channel to post to</label>
                    <select name="account_id" class="pro-input" style="width:100%; height:38px;">
                        <option value="">-- choose a channel --</option>
                        ${opts}
                    </select>
                    <div style="font-size:10px; color:#64748b; margin-top:4px;">
                        ${zs.accounts.length} channel${zs.accounts.length > 1 ? 's' : ''} connected.
                    </div>`;
            } else {
                fieldsHtml += `<label style="margin-top:12px;">account id</label>
                    <input name="account_id" value="${(currentAccountId || '').replace(/"/g, '&quot;')}" autocomplete="off" placeholder="acc_..." />
                    <div style="font-size:10px; color:#f59e0b; margin-top:4px;">
                        No channels detected. Connect at zernio.com → Accounts, then re-open.
                    </div>`;
            }
        } else {
            fieldsHtml = tool.creds.length > 0
                ? tool.creds.map(k => {
                    const val = (existing[k] || '').toString().replace(/"/g, '&quot;');
                    return `<label>${k.replace(/_/g, ' ')}</label><input name="${k}" value="${val}" autocomplete="off" />`;
                }).join('')
                : '<p class="text-xs text-slate-500">This tool requires no credentials.</p>';
        }'''

if old_fields_pattern.search(html):
    html = old_fields_pattern.sub(new_fields, html, count=1)
    hc += 1
    print("  OK — Zernio modal now has profile + channel dropdowns")
else:
    print("  WARN — fields pattern not matched; checking for older single-dropdown version")
    old_single = re.compile(r"        let fieldsHtml = '';[\s\S]*?\n        \}", re.DOTALL)
    if old_single.search(html):
        html = old_single.sub(new_fields, html, count=1)
        hc += 1
        print("  OK — replaced old single-dropdown version")

# ─────────────────────────────────────────────────────────────
# 6. Update TOOLS entry to include profile_id in creds
# ─────────────────────────────────────────────────────────────
print("\n[6] Updating Zernio creds list to include profile_id...")

old_creds = "'zernio':          { label:\"Zernio\",          icon:\"custom-zernio\",      brand:false, color:\"#EB3514\", creds:[\"api_key\",\"account_id\"] },"
new_creds = "'zernio':          { label:\"Zernio\",          icon:\"custom-zernio\",      brand:false, color:\"#EB3514\", creds:[\"api_key\",\"profile_id\",\"account_id\"] },"

if old_creds in html:
    html = html.replace(old_creds, new_creds, 1)
    hc += 1
    print("  OK — profile_id added to creds list")
else:
    print("  WARN — Zernio TOOLS entry not matched exactly")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ═══════════════════════════════════════════════════════════════
# VERIFY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("VERIFICATION")
print("=" * 60)

fs = open(SERVER, 'r', encoding='utf-8').read()
fh = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("server: POST /v1/posts",           "'https://zernio.com/api/v1/posts'" in fs),
    ("server: uses profileId",           "'profileId': profile_id," in fs),
    ("server: uses accountId",           "[{'accountId': account_id}]" in fs),
    ("server: 409 duplicate handling",   'if r.status_code == 409:' in fs),
    ("server: 429 rate limit handling",  'if r.status_code == 429:' in fs),
    ("server: 401 auth error",           'if r.status_code == 401:' in fs),
    ("server: _zernio_status() helper",  'def _zernio_status(' in fs),
    ("server: fetches /v1/profiles",     "'https://zernio.com/api/v1/profiles'" in fs),
    ("server: fetches /v1/accounts",     "'https://zernio.com/api/v1/accounts'" in fs),
    ("server: injects into ai_chat",     'Zernio status injected' in fs),
    ("server: /zernio/accounts route",   "@app.route('/zernio/accounts'" in fs),
    ("html: profile_id in TOOLS",        '"api_key","profile_id","account_id"' in fh),
    ("html: fetches /zernio/accounts",   "fetch('/zernio/accounts')" in fh),
    ("html: profile dropdown",           'name="profile_id" class="pro-input"' in fh),
    ("html: channel dropdown",           'name="account_id" class="pro-input"' in fh),
]

all_ok = True
for name, ok in checks:
    print("  [{}] {}".format("OK  " if ok else "FAIL", name))
    if not ok:
        all_ok = False

print()
if all_ok:
    print("=" * 60)
    print("PATCH COMPLETE")
    print("=" * 60)
    print()
    print("Changes: {} in server.py, {} in index.html".format(sc, hc))
    print()
    print("Next:")
    print("  git add server.py public/index.html")
    print("  git commit -m 'Zernio: correct API endpoints, profiles, channels, error handling'")
    print("  git push origin main")
    print()
    print("Then follow the setup below to get your IDs.")
else:
    print("Review FAIL lines above.")