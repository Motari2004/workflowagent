import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')
HTML = os.path.join(PROJECT, 'public', 'index.html')

if not os.path.exists(SERVER) or not os.path.exists(HTML):
    print("ERROR: files missing"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_buffchat')
shutil.copy(HTML, HTML + '.backup_buffchat')
print("Backed up both\n")

sc, hc = 0, 0

# ═══════════════════════════════════════════════════════════════
# SERVER.PY
# ═══════════════════════════════════════════════════════════════
print("=" * 60)
print("SERVER.PY")
print("=" * 60)

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# ─────────────────────────────────────────────────────────────
# 1. Replace tool_buffer with proper GraphQL implementation
# ─────────────────────────────────────────────────────────────
print("\n[1] Rewriting tool_buffer with GraphQL...")

new_buffer = '''def tool_buffer(creds, msg, extra):
    """Post to Buffer via GraphQL API.
    Requires: api_key, organization_id, channel_id
    Buffer docs: https://developers.buffer.com/
    """
    api_key = creds.get('api_key')
    org_id = creds.get('organization_id')
    channel_id = creds.get('channel_id')

    if not api_key:
        return "[ERROR] Buffer: api_key not configured (get from publish.buffer.com/settings/api)"
    if not channel_id:
        return "[ERROR] Buffer: channel_id not configured (use /buffer/channels to list)"
    if not (msg or '').strip():
        return "[ERROR] Buffer: no content to post"

    text = msg.strip()
    if len(text) > 280:
        text = text[:277] + '...'

    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post {
            id
            text
            status
          }
        }
        ... on MutationError {
          message
          code
        }
      }
    }
    """

    variables = {
        "input": {
            "channelId": channel_id,
            "text": text,
            "schedulingType": "automatic",
            "mode": "addToQueue",
        }
    }

    try:
        r = requests.post(
            'https://api.buffer.com',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={"query": mutation, "variables": variables},
            timeout=20,
        )
    except requests.exceptions.Timeout:
        return "[ERROR] Buffer: timeout (20s)"
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Buffer: network: {e}"

    if r.status_code == 401:
        return "[ERROR] Buffer: 401 Unauthorized — check API key"
    if r.status_code >= 500:
        return f"[ERROR] Buffer: server {r.status_code}"

    if r.status_code != 200:
        return f"[ERROR] Buffer {r.status_code}: {r.text[:300]}"

    try:
        data = r.json()
    except Exception:
        return f"[ERROR] Buffer: non-JSON response: {r.text[:200]}"

    # GraphQL always returns 200 — errors are in the body
    if 'errors' in data and data['errors']:
        err_msg = data['errors'][0].get('message', 'unknown')
        return f"[ERROR] Buffer GraphQL: {err_msg[:200]}"

    result = (data.get('data') or {}).get('createPost') or {}
    
    # Success case
    if 'post' in result:
        post = result['post']
        return f"Buffer 200: queued (id={post.get('id','?')}, status={post.get('status','?')})"

    # MutationError case
    if 'message' in result:
        return f"[ERROR] Buffer: {result['message']}"

    return f"[ERROR] Buffer: unexpected response shape: {str(result)[:200]}"


'''

buffer_pattern = re.compile(
    r"def tool_buffer\(creds, msg, extra\):[\s\S]*?(?=\nTOOL_HANDLERS = \{|\ndef tool_zernio)",
    re.DOTALL
)
if buffer_pattern.search(server):
    server = buffer_pattern.sub(new_buffer, server, count=1)
    sc += 1
    print("  OK — tool_buffer rewritten with GraphQL")

# ─────────────────────────────────────────────────────────────
# 2. Add Buffer live status helper + route
# ─────────────────────────────────────────────────────────────
print("\n[2] Adding Buffer discovery helpers...")

buffer_helpers = '''
# ═══════════════════════════════════════════════════════════════
# BUFFER LIVE STATUS — GraphQL query for orgs and channels
# ═══════════════════════════════════════════════════════════════
def _buffer_status():
    result = {
        "configured": False,
        "api_key_set": False,
        "org_id_set": False,
        "channel_id_set": False,
        "organizations": [],
        "channels": [],
        "current_org": None,
        "current_channel": None,
        "error": None,
    }
    try:
        creds = load_creds('buffer') or {}
    except Exception as e:
        result["error"] = "load_creds: " + str(e)
        return result

    api_key = (creds.get('api_key') or '').strip()
    saved_org = (creds.get('organization_id') or '').strip()
    saved_channel = (creds.get('channel_id') or '').strip()

    result["api_key_set"] = bool(api_key)
    result["org_id_set"] = bool(saved_org)
    result["channel_id_set"] = bool(saved_channel)

    if not api_key:
        return result

    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    # Step 1: list organizations
    try:
        r = requests.post(
            'https://api.buffer.com',
            headers=headers,
            json={"query": "query { account { organizations { id name } } }"},
            timeout=10,
        )
    except Exception as e:
        result["error"] = "network: " + str(e)
        return result

    if r.status_code == 401:
        result["error"] = "API key invalid (401)"
        return result
    if r.status_code != 200:
        result["error"] = f"HTTP {r.status_code}"
        return result

    try:
        data = r.json()
        orgs = data.get('data', {}).get('account', {}).get('organizations') or []
        for o in orgs:
            result["organizations"].append({
                "id": o.get('id', ''),
                "name": o.get('name', ''),
            })
    except Exception as e:
        result["error"] = "parse orgs: " + str(e)
        return result

    # Step 2: if we have an org, list channels
    target_org = saved_org
    if not target_org and result["organizations"]:
        target_org = result["organizations"][0]["id"]

    if target_org:
        try:
            r = requests.post(
                'https://api.buffer.com',
                headers=headers,
                json={
                    "query": "query GetChannels($orgId: String!) { channels(input: { organizationId: $orgId }) { id name service } }",
                    "variables": {"orgId": target_org},
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                chans = data.get('data', {}).get('channels') or []
                for c in chans:
                    result["channels"].append({
                        "id": c.get('id', ''),
                        "name": c.get('name', ''),
                        "service": (c.get('service') or '').lower(),
                    })
        except Exception as e:
            result["error"] = "channels fetch: " + str(e)
            return result

    result["configured"] = True

    # Match current
    if saved_org:
        for o in result["organizations"]:
            if o["id"] == saved_org:
                result["current_org"] = o
                break
    if saved_channel:
        for c in result["channels"]:
            if c["id"] == saved_channel:
                result["current_channel"] = c
                break

    return result


def _buffer_status_block(status):
    if not status["api_key_set"]:
        return (
            "\\n[BUFFER STATUS]\\n"
            "NOT CONFIGURED — no API key. Get one at publish.buffer.com/settings/api\\n"
            "Tell user to configure Credentials → Buffer.\\n[END]\\n"
        )
    if status["error"]:
        return (
            "\\n[BUFFER STATUS]\\n"
            "API check failed: " + status["error"] + "\\n"
            "Tell user to check API key in Credentials → Buffer.\\n[END]\\n"
        )

    lines = ["\\n[BUFFER STATUS]"]
    if status["organizations"]:
        lines.append("Organizations:")
        for o in status["organizations"]:
            marker = " ← current" if status["current_org"] and o["id"] == status["current_org"]["id"] else ""
            lines.append("  - " + o["name"] + " (id: " + o["id"] + ")" + marker)
    else:
        lines.append("No organizations found.")

    if status["channels"]:
        lines.append("Channels:")
        for c in status["channels"]:
            marker = " ← current" if status["current_channel"] and c["id"] == status["current_channel"]["id"] else ""
            lines.append("  - " + c["service"].title() + ": " + c["name"] + " (id: " + c["id"] + ")" + marker)
    else:
        lines.append("No channels connected. User must connect social accounts at publish.buffer.com.")

    lines.append("")
    lines.append("To post to Buffer, both organization_id and channel_id must be set.")
    lines.append("Do NOT invent channel IDs. Only use the ones above.")
    lines.append("[END BUFFER STATUS]\\n")
    return "\\n".join(lines)


'''

if 'def _buffer_status(' not in server:
    anchor = "@app.route('/zernio/accounts', methods=['GET'])"
    if anchor in server:
        server = server.replace(anchor, buffer_helpers + anchor, 1)
        sc += 1
        print("  OK — buffer status helpers added")
    else:
        anchor2 = "@app.route('/ai-chat', methods=['POST', 'OPTIONS'])"
        server = server.replace(anchor2, buffer_helpers + anchor2, 1)
        sc += 1
        print("  OK — buffer helpers added (alt anchor)")

# Add route
if "@app.route('/buffer/channels'" not in server:
    zroute = '''@app.route('/buffer/channels', methods=['GET'])
def buffer_channels():
    return jsonify(_buffer_status())


'''
    anchor = "@app.route('/zernio/accounts', methods=['GET'])"
    if anchor in server:
        server = server.replace(anchor, zroute + anchor, 1)
        sc += 1
        print("  OK — /buffer/channels route added")

# ─────────────────────────────────────────────────────────────
# 3. Add Buffer status injection alongside Zernio
# ─────────────────────────────────────────────────────────────
print("\n[3] Wiring Buffer status injection...")

buffer_inject = '''
        # Live Buffer status
        try:
            msg_lc2 = (message or "").lower()
            if any(k in msg_lc2 for k in ["buffer", "post to social", "queue"]):
                bs = _buffer_status()
                system = system + _buffer_status_block(bs)
                print(f"[ai-chat] Buffer status injected ({len(bs.get('channels', []))} channels)")
        except Exception as b_err:
            print(f"[ai-chat] Buffer status check failed: {b_err}")
'''

if 'Buffer status injected' not in server:
    anchor = 'print(f"[ai-chat] Zernio status injected'
    if anchor in server:
        idx = server.find(anchor)
        line_end = server.find('\n', idx)
        server = server[:line_end+1] + buffer_inject + server[line_end+1:]
        sc += 1
        print("  OK — buffer injection added")

# ─────────────────────────────────────────────────────────────
# 4. Add CONVERSATION PROTOCOL to the prompt
# ─────────────────────────────────────────────────────────────
print("\n[4] Adding conversation protocol to prompt...")

convo_block = '''        "### 🗣 CONVERSATION PROTOCOL — READ FIRST 🗣\\n"
        "You are having a CONVERSATION with a human. Not dumping JSON.\\n\\n"

        "MANDATORY FLOW for every workflow request:\\n"
        "  1. ACKNOWLEDGE — one short sentence showing you understood\\n"
        "  2. CLARIFY — if anything is ambiguous, ask up to 2 focused questions\\n"
        "     (target channel, content source, data source, delivery method)\\n"
        "  3. CONFIRM — state what you're about to build in plain English\\n"
        "  4. BUILD — output the JSON workflow inside a ```json block\\n"
        "  5. EXPLAIN — 1-2 sentences: what it does, what user must configure\\n\\n"

        "RULES:\\n"
        "  - NEVER output JSON as the first response. Always talk first.\\n"
        "  - If the request is clear and you have all info → still ACK + CONFIRM,\\n"
        "    then build in the SAME message.\\n"
        "  - If missing info → ASK, do NOT build. Wait for the reply.\\n"
        "  - If the user says 'yes' / 'ok' / 'go' / 'build it' → NOW build.\\n"
        "  - After building, offer: 'Want me to load it, adjust it, or explain it?'\\n"
        "  - For greetings or questions → just answer. NEVER dump JSON for a greeting.\\n\\n"

        "BAD (do NOT do this):\\n"
        "  User: 'post a quote to zernio'\\n"
        "  AI: [JSON array immediately]\\n\\n"

        "GOOD:\\n"
        "  User: 'post a quote to zernio'\\n"
        "  AI: 'Happy to. Two quick things: which Zernio channel, and should I fetch\\n"
        "       a random quote or use one you provide?'\\n"
        "  User: 'Facebook, random'\\n"
        "  AI: 'Got it — fetching a random quote, posting to Facebook via Zernio.\\n"
        "       Here's the workflow:' [JSON]\\n"
        "       'You'll need Zernio credentials (api_key + profile_id + account_id)\\n"
        "        already configured in Credentials. Want me to load it?'\\n\\n"

'''

if 'CONVERSATION PROTOCOL' not in server:
    # Insert right after the "You are the Workflow Pro Architect" line
    old_open = '''        "You are the Workflow Pro Architect. Concise, execution-focused.\\n\\n"'''
    if old_open in server:
        server = server.replace(old_open, old_open + "\n" + convo_block, 1)
        sc += 1
        print("  OK — conversation protocol added")
    else:
        print("  WARN — could not find prompt opening")

# ─────────────────────────────────────────────────────────────
# 5. Update tool/integration schema to include buffer
# ─────────────────────────────────────────────────────────────
print("\n[5] Ensuring buffer is in the schema...")

old_schema = '''        "                       buffer, zernio.\\n"'''
new_schema = '''        "                       buffer, zernio.\\n"
        "                     ← Buffer needs: api_key + organization_id + channel_id\\n"
        "                     ← Zernio needs: api_key + profile_id + account_id\\n"'''

if old_schema in server and 'Buffer needs: api_key' not in server:
    server = server.replace(old_schema, new_schema, 1)
    sc += 1
    print("  OK — schema mentions buffer credentials")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print(f"  [FAIL] line {e.lineno}: {e.msg}")
    shutil.copy(SERVER + '.backup_buffchat', SERVER)
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# INDEX.HTML
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("INDEX.HTML")
print("=" * 60)

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ─────────────────────────────────────────────────────────────
# 6. Update Buffer TOOLS creds to include org id
# ─────────────────────────────────────────────────────────────
print("\n[6] Updating Buffer TOOLS entry...")

old_buf = "'buffer':          { label:\"Buffer\",          icon:\"fa-buffer\",          brand:true,  color:\"#168EEA\", creds:[\"api_key\",\"channel_id\"] },"
new_buf = "'buffer':          { label:\"Buffer\",          icon:\"fa-buffer\",          brand:true,  color:\"#168EEA\", creds:[\"api_key\",\"organization_id\",\"channel_id\"] },"

if old_buf in html:
    html = html.replace(old_buf, new_buf, 1)
    hc += 1
    print("  OK — Buffer creds updated")
else:
    print("  WARN — Buffer TOOLS entry not matched")

# ─────────────────────────────────────────────────────────────
# 7. Add Buffer dropdowns in credential modal
# ─────────────────────────────────────────────────────────────
print("\n[7] Adding Buffer credential dropdowns...")

old_submit = '''        if (service === 'zernio') {'''
new_submit = '''        if (service === 'buffer') {
            // Buffer: fetch orgs + channels, show dropdowns
            let bs = { organizations: [], channels: [], error: null, api_key_set: false };
            try {
                const bres = await fetch('/buffer/channels');
                if (bres.ok) bs = await bres.json();
            } catch (e) { bs.error = e.message; }
            
            const apiKeyVal = (existing['api_key'] || '').toString().replace(/"/g, '&quot;');
            const currentOrgId = existing['organization_id'] || '';
            const currentChannelId = existing['channel_id'] || '';
            
            fieldsHtml = `<label>api key</label>
                <input name="api_key" value="${apiKeyVal}" autocomplete="off" placeholder="Bearer token from publish.buffer.com/settings/api" />`;
            
            if (bs.organizations && bs.organizations.length > 0) {
                const opts = bs.organizations.map(o => 
                    `<option value="${o.id}" ${o.id === currentOrgId ? 'selected' : ''}>${o.name || '(unnamed)'}</option>`
                ).join('');
                fieldsHtml += `<label style="margin-top:12px;">organization</label>
                    <select name="organization_id" class="pro-input" style="width:100%; height:38px;">
                        <option value="">-- choose an organization --</option>
                        ${opts}
                    </select>`;
            } else {
                fieldsHtml += `<label style="margin-top:12px;">organization id</label>
                    <input name="organization_id" value="${(currentOrgId || '').replace(/"/g, '&quot;')}" autocomplete="off" />
                    <div style="font-size:10px; color:#f59e0b; margin-top:4px;">
                        ${bs.error ? bs.error : 'Save API key first, then re-open to load organizations.'}
                    </div>`;
            }
            
            if (bs.channels && bs.channels.length > 0) {
                const opts = bs.channels.map(c => 
                    `<option value="${c.id}" ${c.id === currentChannelId ? 'selected' : ''}>${c.service.toUpperCase()} — ${c.name}</option>`
                ).join('');
                fieldsHtml += `<label style="margin-top:12px;">channel to post to</label>
                    <select name="channel_id" class="pro-input" style="width:100%; height:38px;">
                        <option value="">-- choose a channel --</option>
                        ${opts}
                    </select>`;
            } else {
                fieldsHtml += `<label style="margin-top:12px;">channel id</label>
                    <input name="channel_id" value="${(currentChannelId || '').replace(/"/g, '&quot;')}" autocomplete="off" />`;
            }
        } else if (service === 'zernio') {'''

if 'service === \'buffer\'' not in html:
    if old_submit in html:
        html = html.replace(old_submit, new_submit, 1)
        hc += 1
        print("  OK — buffer modal added")

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
    ("server: buffer GraphQL POST",     "'https://api.buffer.com'" in fs),
    ("server: buffer uses channelId",   '"channelId": channel_id' in fs),
    ("server: buffer parses mutationError", "if 'message' in result:" in fs),
    ("server: buffer 401 handling",     "if r.status_code == 401:" in fs),
    ("server: _buffer_status()",        "def _buffer_status(" in fs),
    ("server: fetches orgs",            "organizations { id name }" in fs),
    ("server: fetches channels",        "channels(input: { organizationId" in fs),
    ("server: /buffer/channels",        "@app.route('/buffer/channels'" in fs),
    ("server: buffer injection",        "Buffer status injected" in fs),
    ("server: CONVERSATION PROTOCOL",   "CONVERSATION PROTOCOL" in fs),
    ("server: 'NEVER output JSON first'","NEVER output JSON as the first response" in fs),
    ("server: good/bad examples",       "BAD (do NOT do this)" in fs),
    ("html: buffer in TOOLS",           '"api_key","organization_id","channel_id"' in fh),
    ("html: buffer modal",              "service === 'buffer'" in fh),
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
    print(f"\nChanges: {sc} in server.py, {hc} in index.html\n")
    print("Next:")
    print("  git add server.py public/index.html")
    print("  git commit -m 'Buffer GraphQL + conversational AI prompt'")
    print("  git push origin main")
else:
    print("Review FAIL lines.")