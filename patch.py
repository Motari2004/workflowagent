import os, shutil

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_aiprompt')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

# ── Exact old block from your file ──
old_block = '''        "### BUILD WORKFLOWS\\n"
        "Format: list of {type, data} nodes\\n"
        "Nodes: trigger/webhook, action/http, logic/code, tool/integration, output/console\\n\\n"
        "For research + delivery:\\n"
        "  url: 'http://127.0.0.1:10000/api/remote_chat'\\n"
        "  method: 'POST'\\n"
        "  body: JSON string with message/session_id/voice\\n"
        "  headers: JSON string with Content-Type\\n"
        "Response field: data.response\\n\\n"

        "### CODE NODES\\n"
        "Check for [ERROR], extract JSON with regex, then JSON.parse\\n\\n"

        "### TOOLS\\n"
        "tool/integration message field MUST be empty string\\n"
        "email/discord/slack/sheets -> tool/integration\\n"
        "APIs -> action/http"'''

new_block = '''        "### BUILD WORKFLOWS\\n"
        "Format: list of {type, data} nodes\\n"
        "Nodes: trigger/webhook, action/http, logic/code, tool/integration, output/console\\n\\n"

        "For research + delivery:\\n"
        "  url: '/api/remote_chat'\\n"
        "  method: 'POST'\\n"
        "  body: JSON string with message/session_id/voice\\n"
        "  headers: JSON string with Content-Type\\n"
        "Response shape: {\\\"status\\\":\\\"success\\\", \\\"response\\\":\\\"<inner-json-string>\\\"}\\n"
        "  → The Code node's `data` variable is auto-flattened to the inner payload,\\n"
        "    so use `data.jobs`, `data.status`, NOT `data.response.jobs`.\\n\\n"

        "### CODE NODES (JavaScript)\\n"
        "Every JS Code node runs in a sandbox with THREE variables:\\n"
        "  - input:  STRING — raw text from the previous node (may start with 'HTTP 200: ')\\n"
        "  - data:   OBJECT|null — input auto-parsed as JSON. If input looked like\\n"
        "            {status, response}, the runtime recursively parses `.response`.\\n"
        "            So `data` always ends up as the INNER payload (e.g. {jobs:[...]}).\\n"
        "  - output: FUNCTION — call output(value) to pass a result to the next node.\\n\\n"

        "HARD RULES for JS Code nodes:\\n"
        "  1. NO require(), fs, path, process, Buffer, or any Node.js builtin.\\n"
        "     Allowed globals: JSON, Math, Date, String, Array, Object, RegExp,\\n"
        "                     Promise, console.log (goes to stderr).\\n"
        "  2. NO `return` at top level — use `output(result)` instead.\\n"
        "  3. `data` may be null if input isn't JSON — always guard with:\\n"
        "     if (!data) { output('[ERROR] no JSON'); } else { ... }\\n"
        "  4. EVERY code node MUST end with output(...).\\n"
        "  5. Do NOT use `data.response.jobs` — use `data.jobs` (already flattened).\\n\\n"

        "CANONICAL EXAMPLE — extract jobs from Remotive and format for email:\\n"
        "```javascript\\n"
        "if (!data || !data.jobs) {\\n"
        "  output('[ERROR] No jobs in response');\\n"
        "} else {\\n"
        "  const top3 = data.jobs.slice(0, 3);\\n"
        "  const lines = top3.map(function(j) {\\n"
        "    return '• ' + (j.title || 'Unknown') + ' – ' + (j.company_name || 'Unknown') + '\\\\n' +\\n"
        "           '  Location: ' + (j.candidate_required_location || 'Unknown') + '\\\\n' +\\n"
        "           '  URL: ' + (j.url || '');\\n"
        "  });\\n"
        "  output(lines.join('\\\\n\\\\n'));\\n"
        "}\\n"
        "```\\n\\n"

        "When the previous node outputs JSON via HTTP request, `input` looks like\\n"
        "'HTTP 200: {...}' and `data` is the parsed object. You do NOT need to parse.\\n\\n"

        "### TOOLS\\n"
        "tool/integration message field MUST be empty string \\\"\\\" — the tool node\\n"
        "automatically uses the previous node's output as its message.\\n"
        "email/discord/slack/sheets -> tool/integration\\n"
        "APIs -> action/http"'''

if old_block in code:
    code = code.replace(old_block, new_block, 1)
    print("[1] Replaced BUILD WORKFLOWS + CODE NODES + TOOLS prompt block")
else:
    print("[1] FAIL — could not match the exact block")
    print("    The block may already be patched, or whitespace differs.")
    print("    Checking for partial matches...")
    if "### CODE NODES" in code:
        print("    Found '### CODE NODES' — but preceding lines don't match exactly")
    if "Response field: data.response" in code:
        print("    Found 'Response field: data.response' — old prompt still present")
    exit(1)

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

# Compile check
print("\nCompiling...")
try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("Compiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_aiprompt', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

# Verify
final = open(SERVER, 'r', encoding='utf-8').read()
checks = [
    ("input/data/output documented",  "input:  STRING" in final),
    ("output() rule present",         "call output(value)" in final),
    ("No return rule",                "NO `return` at top level" in final),
    ("No require rule",               "NO require(), fs, path" in final),
    ("Canonical example",             "data.jobs.slice(0, 3)" in final),
    ("URL hint uses relative path",   "url: '/api/remote_chat'" in final),
    ("Old data.response hint gone",   "Response field: data.response" not in final),
    ("Old CODE NODES section gone",   "Check for [ERROR], extract JSON with regex" not in final),
]
print("\nVERIFICATION:")
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("=" * 55)
    print("PROMPT PATCH COMPLETE")
    print("=" * 55)
    print()
    print("The AI will now generate working JS Code nodes that use:")
    print("  input  (string)")
    print("  data   (auto-parsed object)")
    print("  output(value)")
    print()
    print("No more `data is not defined`, `return outside function`, or")
    print("`require is not defined` errors from AI-generated code.")
    print()
    print("Next:")
    print("  git add server.py")
    print("  git commit -m 'Update AI prompt with JS Code node contract'")
    print("  git push origin main")
else:
    print("Some checks failed — review above")