# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')
HTML = os.path.join(PROJECT, 'public', 'index.html')

for f in [SERVER, HTML]:
    if not os.path.exists(f):
        print("FAIL: missing " + f); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v7')
shutil.copy(HTML, HTML + '.backup_v7')
print("Backed up")

sc = 0
hc = 0

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# ============================================================
# PATCH 1: tool_zernio accepts media_urls
# ============================================================
print("\n[1] Adding media_urls support to tool_zernio...")

old_zernio = re.search(
    r'def tool_zernio\(creds, msg, extra\):[\s\S]*?return "\[ERROR\] Zernio " \+ str\(r\.status_code\) \+ ": " \+ r\.text\[:300\]',
    server
)

if not old_zernio:
    print("  FAIL: tool_zernio not found (may not be patched yet)")
    sys.exit(1)

# New zernio with media support
zernio_lines = [
    'def tool_zernio(creds, msg, extra):',
    '    """Post to Zernio. Requires api_key (sk_...) and account_id.',
    '    platform: instagram | facebook | tiktok | twitter | linkedin | threads | etc.',
    '    media_urls: list of image/video URLs (REQUIRED for Instagram).',
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
    '    # Media URLs - required for Instagram, optional elsewhere',
    '    media_urls = (extra or {}).get("media_urls") or []',
    '    if isinstance(media_urls, str):',
    '        media_urls = [media_urls]',
    '    media_urls = [u for u in media_urls if u and u.strip()]',
    '',
    '    if platform == "instagram" and not media_urls:',
    '        return "[ERROR] Zernio: Instagram requires at least one image or video URL (media_urls)"',
    '',
    '    text = msg.strip()',
    '',
    '    payload = {',
    '        "content": text,',
    '        "publishNow": True,',
    '        "platform": platform,',
    '        "platforms": [{"accountId": account_id, "platform": platform}],',
    '    }',
    '    if media_urls:',
    '        payload["mediaUrls"] = media_urls',
    '        payload["media_urls"] = media_urls',
    '        payload["media"] = [{"url": u, "type": "image"} for u in media_urls]',
    '',
    '    try:',
    '        r = requests.post(',
    '            "https://zernio.com/api/v1/posts",',
    '            headers={',
    '                "Authorization": "Bearer " + token,',
    '                "Content-Type": "application/json",',
    '            },',
    '            json=payload,',
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
    '            media_note = " with " + str(len(media_urls)) + " media" if media_urls else ""',
    '            return "Zernio " + str(r.status_code) + ": posted to " + platform + media_note + " (id=" + str(post_id) + ")"',
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
print("  OK: tool_zernio now accepts media_urls")

# ============================================================
# PATCH 2: pass media_urls through tool dispatcher
# ============================================================
print("\n[2] Passing media_urls from node_data...")

# Find the current dispatcher (already patched in v5)
old_call = '''                    tool_extra = {}
                    if node_data.get('extra'):
                        tool_extra.update(node_data['extra'])
                    if node_data.get('config'):
                        tool_extra.update(node_data['config'])
                    if node_data.get('platform'):
                        tool_extra['platform'] = node_data['platform']
                    result = handler(creds, msg, tool_extra)'''

new_call = '''                    tool_extra = {}
                    if node_data.get('extra'):
                        tool_extra.update(node_data['extra'])
                    if node_data.get('config'):
                        tool_extra.update(node_data['config'])
                    if node_data.get('platform'):
                        tool_extra['platform'] = node_data['platform']
                    if node_data.get('media_urls'):
                        tool_extra['media_urls'] = node_data['media_urls']
                    if node_data.get('mediaUrls'):
                        tool_extra['media_urls'] = node_data['mediaUrls']
                    result = handler(creds, msg, tool_extra)'''

if old_call in server:
    server = server.replace(old_call, new_call, 1)
    sc += 1
    print("  OK: dispatcher passes media_urls")
else:
    print("  SKIP: dispatcher pattern not found")

# ============================================================
# PATCH 3: replace system prompt with anti-repetition version
# ============================================================
print("\n[3] Replacing system prompt (anti-repetition)...")

# Match the ENTIRE system = data.get('system') or (...) block
prompt_pat = re.compile(
    r"system\s*=\s*data\.get\(['\"]system['\"]\)\s*or\s*\([\s\S]*?\n\s*\)\s*\n\s*\n\s*if not message",
    re.DOTALL
)

m = prompt_pat.search(server)
if not m:
    print("  FAIL: system prompt block not matched")
    print("  Trying alternate pattern...")
    # Match from "### 🗣 CONVERSATION PROTOCOL" to the closing `)` before `if not message`
    alt = re.search(
        r'system\s*=\s*data\.get\([^)]+\)\s*or\s*\(\s*"You are the Workflow Pro Architect[\s\S]*?"\s*\)\s*\n\s*\n\s*if not message',
        server
    )
    if alt:
        m = alt
        print("  Found with alternate pattern")
    else:
        print("  FAIL: no pattern matched")
        sys.exit(1)

# Write as lines to avoid escape issues
prompt_new = [
    'system = data.get(\'system\') or (',
    '        "You are a workflow builder for WorkflowPro automation tool. "',
    '        "Your PRIMARY job is to produce working workflow JSON quickly. "',
    '        "Users get frustrated by repeated questions. "',
    '        "When in doubt, BUILD."',
    '        "\\n\\n"',
    '',
    '        "### CONVERSATION MEMORY - READ BEFORE RESPONDING ###"',
    '        "\\n"',
    '        "The full chat history is in the `contents` array. Read EVERY turn "',
    '        "before responding. If the user already answered a question, "',
    '        "DO NOT ask it again.\\n\\n"',
    '',
    '        "### BUILD-OR-ASK DECISION TREE ###"',
    '        "\\n"',
    '        "TRIGGER TO BUILD IMMEDIATELY (no clarifying questions):"',
    '        "  - User said: yes / ok / build / go / do it / just build / proceed"',
    '        "  - User already answered the last question you asked"',
    '        "  - User said: do whatever / your call / you decide / fine as you wish"',
    '        "  - You have enough info to make reasonable defaults"',
    '        "\\n"',
    '        "TRIGGER TO ASK: Only when genuinely blocked - e.g. you have ZERO "',
    '        "information about what the user wants. If you can infer a sensible "',
    '        "default, BUILD.\\n\\n"',
    '',
    '        "### ASK AT MOST ONE QUESTION PER TURN ###"',
    '        "\\n"',
    '        "If you must ask, ask ONE question. Not two, not three. "',
    '        "If you find yourself writing a numbered list of questions, "',
    '        "STOP and just build with defaults.\\n\\n"',
    '',
    '        "### NEVER REPEAT A QUESTION YOU ALREADY ASKED ###"',
    '        "\\n"',
    '        "Before asking anything, scan the history. If your last message "',
    '        "was a question that the user already answered, DO NOT ASK IT AGAIN. "',
    '        "Just use their answer and build.\\n\\n"',
    '',
    '        "### ZERNIO / INSTAGRAM / SOCIAL POSTING ###"',
    '        "\\n"',
    '        "Zernio is a valid tool that posts to: instagram, facebook, tiktok, "',
    '        "twitter, linkedin, threads, youtube, reddit, telegram, etc.\\n"',
    '        "NEVER say you don\'t have Zernio - you do.\\n"',
    '        "NEVER say you don\'t have Instagram - Zernio handles it.\\n\\n"',
    '        "Zernio tool node shape:"',
    '        "\\n"',
    '        "  {type:\'tool/integration\', data:{"',
    '        "    service:\'zernio\',"',
    '        "    message:\'\',"',
    '        "    platform:\'instagram\',"',
    '        "    media_urls:[\'https://image-url.jpg\']"',
    '        "  }}"',
    '        "\\n\\n"',
    '        "INSTAGRAM REQUIRES MEDIA (image or video). No exceptions.\\n"',
    '        "If platform=instagram, media_urls MUST contain at least one image URL.\\n"',
    '        "For other platforms (facebook, twitter, etc.), media_urls is optional.\\n\\n"',
    '',
    '        "### FREE IMAGE SOURCES FOR INSTAGRAM ###"',
    '        "\\n"',
    '        "- https://picsum.photos/1024/1024  returns redirect to random image\\n"',
    '        "- https://source.unsplash.com/random/1024x1024  (deprecated, may not work)\\n"',
    '        "- https://picsum.photos/seed/{RANDOM}/1024  deterministic by seed\\n"',
    '        "- https://loremflickr.com/1024/1024/{keyword}  random by keyword\\n\\n"',
    '        "For a random quote + random image workflow, use:"',
    '        "\\n"',
    '        "  HTTP node 1: GET https://type.fit/api/quotes   (returns array)\\n"',
    '        "  HTTP node 2: GET https://picsum.photos/1024/1024  (returns image URL)\\n"',
    '        "  Code node: extract quote + image URL\\n"',
    '        "  Zernio node: platform=instagram, media_urls=[image]\\n\\n"',
    '',
    '        "### NODE SCHEMAS ###"',
    '        "\\n"',
    '        "trigger/webhook     {type:\'trigger/webhook\', data:{}}\\n"',
    '        "action/http         {type:\'action/http\', data:{url:\'\', method:\'GET\'}}\\n"',
    '        "logic/code          {type:\'logic/code\', data:{lang:\'javascript\', code:\'\'}}\\n"',
    '        "tool/integration    {type:\'tool/integration\', data:{service:\'\', message:\'\'}}\\n"',
    '        "output/console      {type:\'output/console\', data:{}}\\n\\n"',
    '',
    '        "### CODE NODE VARIABLES ###"',
    '        "\\n"',
    '        "  input  - raw string from previous node\\n"',
    '        "  data   - auto-parsed JSON (null if parse failed)\\n"',
    '        "  output - call output(value) to pass to next node\\n\\n"',
    '        "ALWAYS guard: if (!data) { output(\'[ERROR] ...\'); } else { ... }\\n"',
    '        "Use backticks for templates: `text ${data.x}`\\n"',
    '        "NEVER use ${...} outside backticks - syntax error.\\n\\n"',
    '',
    '        "### KNOWN-WORKING QUOTE APIS ###"',
    '        "\\n"',
    '        "  https://type.fit/api/quotes           returns [{text, author}, ...]\\n"',
    '        "  https://dummyjson.com/quotes/random    returns {id, quote, author}\\n"',
    '        "  https://zenquotes.io/api/random        returns [{q, a}]\\n\\n"',
    '        "DO NOT use api.quotable.io - TLS cert expired.\\n\\n"',
    '',
    '        "### KNOWN-WORKING IMAGE APIS ###"',
    '        "\\n"',
    '        "  https://picsum.photos/1024/1024        302 redirect to random image\\n"',
    '        "  https://picsum.photos/seed/{id}/1024    deterministic image\\n"',
    '        "  https://loremflickr.com/1024/1024       random image from Flickr\\n\\n"',
    '',
    '        "### OUTPUT FORMAT ###"',
    '        "\\n"',
    '        "When building: output JSON array inside ```json block.\\n"',
    '        "When answering: plain text, no JSON.\\n"',
    '        "Keep responses SHORT. Users want workflows, not essays.\\n"',
    '    )',
    '',
    '    if not message',
]

new_prompt_block = '\n'.join(prompt_new)
server = server[:m.start()] + new_prompt_block + server[m.end():]
sc += 1
print("  OK: system prompt replaced (anti-repetition)")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    print("  Context: {}".format(repr(open(SERVER, encoding='utf-8').read().splitlines()[e.lineno-1] if e.lineno else '')))
    shutil.copy(SERVER + '.backup_v7', SERVER)
    print("  Restored from backup")
    sys.exit(1)

# ============================================================
# INDEX.HTML - add media_urls field to Tool node
# ============================================================
print("\n" + "=" * 55)
print("INDEX.HTML")
print("=" * 55)

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ---------- PATCH 4: NodeTool gets media_urls field ----------
print("\n[4] Adding Media URLs field to Tool node...")

old_nt = re.search(
    r'function NodeTool\(\) \{[\s\S]*?applyNodeTheme\(this, NODE_THEME\.tool\);[^\}]*\}',
    html
)

if old_nt and 'media_urls' not in old_nt.group(0):
    new_nt = '''function NodeTool() {
    this.properties = { service:"discord", message:"", platform:"instagram", media_urls:"" };
    this.addInput("in","string"); this.addOutput("out","string");
    const names = Object.keys(TOOLS);
    this.addWidget("combo","Service","discord", v => this.properties.service = v, { values:names });
    this.addWidget("text","Message (opt)","", v => this.properties.message = v);
    this.platformWidget = this.addWidget("combo","Platform","instagram", v => this.properties.platform = v, {
        values: ["instagram","facebook","tiktok","twitter","linkedin","threads","pinterest","youtube","reddit","bluesky","telegram","snapchat","whatsapp","discord","slack"]
    });
    this.mediaWidget = this.addWidget("text","Media URL (opt)","", v => this.properties.media_urls = v);
    this.title = "Tool";
    applyNodeTheme(this, NODE_THEME.tool);
}'''
    html = html.replace(old_nt.group(0), new_nt, 1)
    hc += 1
    print("  OK: Media URL field added")
else:
    print("  SKIP: already has media_urls or NodeTool not found")

# ---------- PATCH 5: onConfigure restores media_urls ----------
print("\n[5] onConfigure media_urls restore...")

if 'this.properties.media_urls = info.properties.media_urls' not in html:
    pm = re.search(
        r'(NodeTool\.prototype\.onConfigure\s*=\s*function\(info\)\s*\{[\s\S]*?if\s*\(typeof info\.properties\.platform\s*===\s*["\']string["\']\)\s*this\.properties\.platform\s*=\s*info\.properties\.platform;)',
        html
    )
    if pm:
        old = pm.group(1)
        new = old + '\n        if (typeof info.properties.media_urls === "string") this.properties.media_urls = info.properties.media_urls;'
        html = html.replace(old, new, 1)
        hc += 1
        print("  OK: media_urls restore in onConfigure")

if 'w.name === "Media URL (opt)"' not in html:
    wm = re.search(
        r'(else if\s*\(w\.name\s*===\s*"Platform"\)\s*w\.value\s*=\s*this\.properties\.platform\s*\|\|\s*"instagram";)',
        html
    )
    if wm:
        old = wm.group(1)
        new = old + '\n            else if (w.name === "Media URL (opt)") w.value = this.properties.media_urls || "";'
        html = html.replace(old, new, 1)
        hc += 1
        print("  OK: media_urls widget sync")

# ---------- PATCH 6: buildPayload includes media_urls ----------
print("\n[6] buildPayload media_urls...")

old_bp = re.search(
    r"case 'tool/integration': payload\.push\(\{type:'tool', data:\{service:d\.service\|\|'http-custom', message:d\.message\|\|'', platform:d\.platform\|\|'instagram'\}\}\);\s*break;",
    html
)

if old_bp:
    new_bp = '''case 'tool/integration': {
                const mediaStr = (d.media_urls || '').trim();
                const mediaList = mediaStr ? mediaStr.split(/[,\\n]+/).map(s => s.trim()).filter(Boolean) : [];
                payload.push({type:'tool', data:{
                    service: d.service||'http-custom',
                    message: d.message||'',
                    platform: d.platform||'instagram',
                    media_urls: mediaList
                }});
                break;
            }'''
    html = html.replace(old_bp.group(0), new_bp, 1)
    hc += 1
    print("  OK: buildPayload includes media_urls array")
else:
    print("  SKIP: buildPayload pattern not matched")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ============================================================
# VERIFY
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fs = open(SERVER, 'r', encoding='utf-8').read()
fh = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("server: zernio accepts media",   "media_urls" in fs and "Instagram requires" in fs),
    ("server: dispatcher passes media","tool_extra['media_urls']" in fs),
    ("server: new anti-ask prompt",    "NEVER REPEAT A QUESTION" in fs),
    ("server: instagram media rule",   "INSTAGRAM REQUIRES MEDIA" in fs),
    ("server: picsum suggested",       "picsum.photos" in fs),
    ("html: media_urls widget",        'mediaWidget' in fh),
    ("html: media_urls buildPayload",  "media_urls: mediaList" in fh),
    ("html: media_urls onConfigure",   "this.properties.media_urls = info.properties.media_urls" in fh),
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
    print("  git commit -m 'Zernio media support + anti-repetition prompt'")
    print("  git push origin main")
else:
    print("Review FAIL lines. Backups: *.backup_v7")