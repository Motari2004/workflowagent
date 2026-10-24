# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')
HTML = os.path.join(PROJECT, 'public', 'index.html')

for f in [SERVER, HTML]:
    if not os.path.exists(f):
        print("FAIL: missing " + f); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v5')
shutil.copy(HTML, HTML + '.backup_v5')
print("Backed up")

sc = 0
hc = 0

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# ============================================================
# PATCH 1: tool_zernio - add platform support
# ============================================================
print("\n[1] Patching tool_zernio...")

old_zernio = re.search(
    r'def tool_zernio\(creds, msg, extra\):[\s\S]*?return f"\[ERROR\] Zernio \{r\.status_code\}: \{r\.text\[:300\]\}"',
    server
)

if not old_zernio:
    print("  FAIL: tool_zernio not found")
    sys.exit(1)

# Build replacement as a list of lines to avoid triple-quote issues
zernio_lines = [
    'def tool_zernio(creds, msg, extra):',
    '    """Post to Zernio. Requires api_key (sk_...) and account_id.',
    '    platform comes from extra (node data) - defaults to instagram.',
    '    """',
    '    token = creds.get("api_key")',
    '    account_id = creds.get("account_id")',
    '',
    '    if not token:',
    '        return "[ERROR] Zernio: api_key not configured (starts with sk_)"',
    '    if not account_id:',
    '        return "[ERROR] Zernio: account_id not configured (get from GET /v1/accounts)"',
    '    if not (msg or "").strip():',
    '        return "[ERROR] Zernio: no content to post"',
    '',
    '    platform = (',
    '        (extra or {}).get("platform")',
    '        or creds.get("platform")',
    '        or "instagram"',
    '    )',
    '    platform = str(platform).strip().lower()',
    '',
    '    valid_platforms = {',
    '        "instagram", "facebook", "tiktok", "twitter", "linkedin",',
    '        "threads", "pinterest", "youtube", "reddit", "bluesky",',
    '        "telegram", "snapchat", "whatsapp", "discord", "slack",',
    '    }',
    '    if platform not in valid_platforms:',
    '        return (',
    '            "[ERROR] Zernio: invalid platform " + platform + ". "',
    '            "Must be one of: " + ", ".join(sorted(valid_platforms))',
    '        )',
    '',
    '    text = msg.strip()',
    '',
    '    try:',
    '        r = requests.post(',
    '            "https://zernio.com/api/v1/posts",',
    '            headers={',
    '                "Authorization": "Bearer " + token,',
    '                "Content-Type": "application/json",',
    '            },',
    '            json={',
    '                "content": text,',
    '                "publishNow": True,',
    '                "platform": platform,',
    '                "platforms": [{"accountId": account_id, "platform": platform}],',
    '            },',
    '            timeout=20,',
    '        )',
    '    except requests.exceptions.Timeout:',
    '        return "[ERROR] Zernio: timeout (20s)"',
    '    except requests.exceptions.RequestException as e:',
    '        return "[ERROR] Zernio: network: " + str(e)',
    '',
    '    if r.status_code in (200, 201):',
    '        try:',
    '            data = r.json()',
    '            post_id = data.get("_id") or data.get("id", "?")',
    '            return "Zernio " + str(r.status_code) + ": posted to " + platform + " (id=" + str(post_id) + ")"',
    '        except Exception:',
    '            return "Zernio " + str(r.status_code) + ": posted to " + platform',
    '',
    '    if r.status_code == 401:',
    '        return "[ERROR] Zernio: 401 Unauthorized - check API key"',
    '    if r.status_code == 409:',
    '        return "[ERROR] Zernio: 409 duplicate content (same content posted within 24h)"',
    '    return "[ERROR] Zernio " + str(r.status_code) + ": " + r.text[:300]',
]

new_zernio = '\n'.join(zernio_lines)

server = server.replace(old_zernio.group(0), new_zernio, 1)
sc += 1
print("  OK: tool_zernio now reads platform")

# ============================================================
# PATCH 2: pass platform/extra/config to handler
# ============================================================
print("\n[2] Passing platform to tool handler...")

old_call = '''                    msg = raw_msg or current_memory
                    result = handler(creds, msg, node_data.get('extra') or {})'''

new_call = '''                    msg = raw_msg or current_memory
                    tool_extra = {}
                    if node_data.get('extra'):
                        tool_extra.update(node_data['extra'])
                    if node_data.get('config'):
                        tool_extra.update(node_data['config'])
                    if node_data.get('platform'):
                        tool_extra['platform'] = node_data['platform']
                    result = handler(creds, msg, tool_extra)'''

if old_call in server:
    server = server.replace(old_call, new_call, 1)
    sc += 1
    print("  OK: extra config passed to handler")
else:
    print("  SKIP: handler call pattern not matched")

# ============================================================
# PATCH 3: duplicate-message guard
# ============================================================
print("\n[3] Duplicate-message guard...")

old_append = '''        contents.append({"role": "user", "parts": [{"text": message}]})
        
        # Route to provider'''

new_append = '''        # Only append current message if frontend didn't already include it
        already_included = False
        if contents:
            last = contents[-1]
            if last.get("role") == "user":
                parts = last.get("parts", [])
                if parts and parts[0].get("text", "").strip() == message.strip():
                    already_included = True
        if not already_included:
            contents.append({"role": "user", "parts": [{"text": message}]})
        
        # Route to provider'''

if old_append in server:
    server = server.replace(old_append, new_append, 1)
    sc += 1
    print("  OK: duplicate-message guard added")
else:
    print("  SKIP: append pattern not matched")

# ============================================================
# Compile check (server)
# ============================================================
print("\n[4] Compile check...")

try:
    compile(server, SERVER, 'exec')
    print("  [OK  ] server compiles")
except SyntaxError as e:
    print("  [FAIL] line {}: {}".format(e.lineno, e.msg))
    print("  Context: {}".format(repr(server.splitlines()[e.lineno - 1] if e.lineno else '')))
    print("  Restored from backup")
    shutil.copy(SERVER + '.backup_v5', SERVER)
    sys.exit(1)

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)
print("  OK: server.py written")

# ============================================================
# INDEX.HTML - platform widget
# ============================================================
print("\n" + "=" * 55)
print("INDEX.HTML")
print("=" * 55)

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# NodeTool with platform widget
print("\n[5] NodeTool platform widget...")

old_nt = re.search(
    r'function NodeTool\(\) \{[\s\S]*?applyNodeTheme\(this, NODE_THEME\.tool\);[^\}]*\}',
    html
)

if old_nt and 'platformWidget' not in old_nt.group(0):
    new_nt_lines = [
        'function NodeTool() {',
        '    this.properties = { service:"discord", message:"", platform:"instagram" };',
        '    this.addInput("in","string"); this.addOutput("out","string");',
        '    const names = Object.keys(TOOLS);',
        '    this.addWidget("combo","Service","discord", v => this.properties.service = v, { values:names });',
        '    this.addWidget("text","Message (opt)","", v => this.properties.message = v);',
        '    this.platformWidget = this.addWidget("combo","Platform","instagram", v => this.properties.platform = v, {',
        '        values: ["instagram","facebook","tiktok","twitter","linkedin","threads","pinterest","youtube","reddit","bluesky","telegram","snapchat","whatsapp","discord","slack"]',
        '    });',
        '    this.title = "Tool";',
        '    applyNodeTheme(this, NODE_THEME.tool);',
        '}',
    ]
    new_nt = '\n'.join(new_nt_lines)
    html = html.replace(old_nt.group(0), new_nt, 1)
    hc += 1
    print("  OK: platform widget added")
else:
    print("  SKIP: platform widget already present or NodeTool not found")

# onConfigure restore
print("\n[6] onConfigure platform restore...")

if 'this.properties.platform = info.properties.platform' not in html:
    pm = re.search(
        r'(NodeTool\.prototype\.onConfigure\s*=\s*function\(info\)\s*\{[\s\S]*?if\s*\(typeof info\.properties\.message\s*===\s*["\']string["\']\)\s*this\.properties\.message\s*=\s*info\.properties\.message;)',
        html
    )
    if pm:
        old = pm.group(1)
        new = old + '\n        if (typeof info.properties.platform === "string") this.properties.platform = info.properties.platform;'
        html = html.replace(old, new, 1)
        hc += 1
        print("  OK: platform restored in onConfigure")

if 'w.name === "Platform"' not in html:
    wm = re.search(
        r'(if\s*\(w\.name\s*===\s*"Message \(opt\)"\)\s*w\.value\s*=\s*this\.properties\.message\s*\|\|\s*"";)',
        html
    )
    if wm:
        old = wm.group(1)
        new = old + '\n            else if (w.name === "Platform") w.value = this.properties.platform || "instagram";'
        html = html.replace(old, new, 1)
        hc += 1
        print("  OK: platform in widget sync loop")

# buildPayload
print("\n[7] buildPayload platform...")

if 'platform: d.platform' not in html and 'platform:d.platform' not in html:
    bm = re.search(
        r"case 'tool/integration':\s*payload\.push\(\{type:'tool',\s*data:\{service:d\.service\|\|'http-custom',\s*message:d\.message\|\|''\}\}\);",
        html
    )
    if bm:
        old = bm.group(0)
        new = "case 'tool/integration': payload.push({type:'tool', data:{service:d.service||'http-custom', message:d.message||'', platform:d.platform||'instagram'}});"
        html = html.replace(old, new, 1)
        hc += 1
        print("  OK: buildPayload includes platform")
    else:
        print("  FAIL: buildPayload pattern not matched")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ============================================================
# Verify
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fs = open(SERVER, 'r', encoding='utf-8').read()
fh = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("server: tool_zernio reads platform", "valid_platforms" in fs),
    ("server: handler passes extra",       "tool_extra['platform']" in fs),
    ("server: dup guard",                  "already_included = False" in fs),
    ("html: platform widget",              'this.platformWidget' in fh),
    ("html: buildPayload platform",        "platform:d.platform" in fh or "platform: d.platform" in fh),
    ("html: onConfigure platform",         "this.properties.platform = info.properties.platform" in fh),
]

ok = True
for name, passed in checks:
    print("  [{}] {}".format("OK  " if passed else "FAIL", name))
    if not passed: ok = False

print()
if ok:
    print("=" * 55)
    print("PATCH COMPLETE")
    print("=" * 55)
    print("server: {} changes, html: {} changes".format(sc, hc))
    print()
    print("Next:")
    print("  git add server.py public/index.html")
    print("  git commit -m 'Zernio platform + dup guard'")
    print("  git push origin main")
else:
    print("Review FAIL lines. Backups: *.backup_v5")