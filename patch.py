import os, shutil, sys, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_zernio_prompt')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

print("File: {} chars".format(len(code)))
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Update the TOOL SCHEMA line to include buffer and zernio
# ═══════════════════════════════════════════════════════════════
print("[1] Adding buffer + zernio to the tool schema...")

old_schema = '''        "  tool/integration   data: {service: string, message: string}\\n"
        "                     ← service = one of: gmail-smtp, discord, slack, telegram,\\n"
        "                       notion, google-sheets, twilio-sms, webhook, http-custom.\\n"
        "                       message = \\"\\" (empty — auto-inherits previous output).\\n"'''

new_schema = '''        "  tool/integration   data: {service: string, message: string}\\n"
        "                     ← service = one of: gmail-smtp, discord, slack, telegram,\\n"
        "                       notion, google-sheets, twilio-sms, webhook, http-custom,\\n"
        "                       buffer, zernio.\\n"
        "                       message = \\"\\" (empty — auto-inherits previous output).\\n"'''

if old_schema in code:
    code = code.replace(old_schema, new_schema, 1)
    changes += 1
    print("  OK — tool schema now lists buffer and zernio")
else:
    print("  WARN — schema pattern not matched, trying regex")
    pattern = re.compile(
        r'"  tool/integration   data: \{service: string, message: string\}\\n"[\s\S]*?"                       message = \\\\"\\\\" \(empty — auto-inherits previous output\)\.\\n"',
        re.DOTALL
    )
    if pattern.search(code):
        code = pattern.sub(new_schema.strip(), code, count=1)
        changes += 1
        print("  OK — schema updated (regex)")
    else:
        print("  FAIL — could not find tool schema")

# ═══════════════════════════════════════════════════════════════
# 2. Add an explicit note about social posting tools
# ═══════════════════════════════════════════════════════════════
print("\n[2] Adding social-posting tool note to prompt...")

social_note = '''        "### SOCIAL POSTING TOOLS\\n"
        "If the user says 'post to Facebook' or 'post to Zernio' or 'post to social media':\\n"
        "  → Use tool/integration with service='zernio'. Zernio handles Facebook, LinkedIn,\\n"
        "    Instagram, and other social platforms via a single API.\\n"
        "  → The workflow needs a source for the content first (HTTP fetch, Code node that\\n"
        "    generates/selects text, or research via /api/remote_chat).\\n"
        "  → Set message=\\"\\" so the previous node's output becomes the post body.\\n\\n"
        "If the user says 'post to Buffer':\\n"
        "  → Use tool/integration with service='buffer'. Buffer also posts to social platforms.\\n\\n"
        "These ARE valid tools. Do NOT say 'I don't have Facebook / Zernio / Buffer integration'.\\n"
        "They are in TOOL_HANDLERS and the backend will execute them.\\n\\n"

        "### TOOLS\\n"'''

old_tools_marker = '''        "### TOOLS\\n"'''

if '### SOCIAL POSTING TOOLS' not in code:
    if old_tools_marker in code:
        code = code.replace(old_tools_marker, social_note, 1)
        changes += 1
        print("  OK — social posting note added before ### TOOLS")
    else:
        print("  WARN — could not find '### TOOLS' marker")

# ═══════════════════════════════════════════════════════════════
# 3. Fix the rule that makes the AI think only listed services exist
# ═══════════════════════════════════════════════════════════════
print("\n[3] Adding explicit 'do not refuse social tools' rule...")

refuse_rule = '''        "RULES FOR TOOL NODES:\\n"
        "  - If the user asks for a tool that exists in the list above, USE IT. Do NOT refuse.\\n"
        "  - Do NOT say 'I do not have X integration' for any tool in the list.\\n"
        "  - zernio IS a valid tool. buffer IS a valid tool.\\n"
        "  - If the user says 'post to Facebook', use service='zernio' (Zernio posts to Facebook).\\n"
        "  - If you are unsure about credentials, still build the workflow — the user\\n"
        "    configures credentials in the Credentials panel separately.\\n\\n"

        "### TOOLS\\n"'''

if 'RULES FOR TOOL NODES' not in code:
    if old_tools_marker in code:
        code = code.replace(old_tools_marker, refuse_rule, 1)
        changes += 1
        print("  OK — 'do not refuse' rule added")
    else:
        print("  WARN — could not find '### TOOLS' marker")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
print("\n[4] Verifying...")

final = open(SERVER, 'r', encoding='utf-8').read()

checks = [
    ("schema lists buffer",           "buffer, zernio." in final),
    ("schema lists zernio",           "zernio" in final),
    ("social posting section exists", "### SOCIAL POSTING TOOLS" in final),
    ("zernio → Facebook mapping",     "Zernio handles Facebook" in final),
    ("do not refuse rule",            "RULES FOR TOOL NODES" in final),
    ("no hallucinated refusal",       "Do NOT say 'I do not have X integration'" in final),
    ("TOOL_HANDLERS has zernio",      "'zernio':          tool_zernio," in final),
    ("tool_zernio defined",           "def tool_zernio(" in final),
]

all_ok = True
for name, ok in checks:
    print("  [{}] {}".format("OK  " if ok else "FAIL", name))
    if not ok:
        all_ok = False

print()
if all_ok:
    print("=" * 55)
    print("PATCH COMPLETE")
    print("=" * 55)
    print("\nNext:")
    print("  git add server.py")
    print("  git commit -m 'AI prompt: include buffer and zernio in tool list'")
    print("  git push origin main")
else:
    print("Review FAIL lines above")
    print("Backup: server.py.backup_zernio_prompt")