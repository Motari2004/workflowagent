import os, shutil

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_schema')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

old_schema = '''        "### BUILD WORKFLOWS\\n"
        "Format: list of {type, data} nodes\\n"
        "Nodes: trigger/webhook, action/http, logic/code, tool/integration, output/console\\n\\n"'''

new_schema = '''        "### BUILD WORKFLOWS\\n"
        "Format: a JSON array of nodes. Each node is {type: string, data: OBJECT}.\\n"
        "`data` is ALWAYS an object with named keys — NEVER a raw string.\\n\\n"

        "Node schemas (exact key names):\\n"
        "  trigger/webhook    data: {}                             (no keys)\\n"
        "  action/http        data: {url: string, method: string, body?: string, headers?: object}\\n"
        "  logic/code         data: {code: string, lang: \\\"javascript\\\"}\\n"
        "                     ← data.code contains the JS source as a STRING,\\n"
        "                       data.lang is the language, usually \\\"javascript\\\".\\n"
        "  tool/integration   data: {service: string, message: string}\\n"
        "                     ← service = one of: gmail-smtp, discord, slack, telegram,\\n"
        "                       notion, google-sheets, twilio-sms, webhook, http-custom.\\n"
        "                       message = \\\"\\\" (empty — auto-inherits previous output).\\n"
        "  output/console     data: {}                             (no keys)\\n\\n"

        "WRONG examples (do NOT emit):\\n"
        "  {\\\"type\\\": \\\"logic/code\\\", \\\"data\\\": \\\"...JS string...\\\"}             ← data must be object, not string\\n"
        "  {\\\"type\\\": \\\"tool/integration\\\", \\\"data\\\": {\\\"integration\\\": \\\"email\\\", ...}}  ← must use `service`, not `integration`\\n"
        "  {\\\"type\\\": \\\"tool/integration\\\", \\\"data\\\": {\\\"to\\\": \\\"...\\\", \\\"subject\\\": \\\"...\\\"}}    ← only `service` and `message` allowed\\n\\n"

        "CORRECT example for a Code node:\\n"
        "  {\\\"type\\\": \\\"logic/code\\\",\\n"
        "   \\\"data\\\": {\\n"
        "     \\\"lang\\\": \\\"javascript\\\",\\n"
        "     \\\"code\\\": \\\"if (!data || !data.jobs) { output('[ERROR] no jobs'); } else { output(data.jobs.slice(0,3).map(function(j){return j.title;}).join('\\\\\\\\n')); }\\\"\\n"
        "   }}\\n\\n"

        "CORRECT example for an email tool node (gmail-smtp):\\n"
        "  {\\\"type\\\": \\\"tool/integration\\\",\\n"
        "   \\\"data\\\": {\\\"service\\\": \\\"gmail-smtp\\\", \\\"message\\\": \\\"\\\"}}\\n\\n"'''

if old_schema in code:
    code = code.replace(old_schema, new_schema, 1)
    print("[1] Node schema documentation expanded")
else:
    print("[1] FAIL — could not match BUILD WORKFLOWS section")
    print("    Search server.py for: ### BUILD WORKFLOWS")
    exit(1)

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("Compiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_schema', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

final = open(SERVER, 'r', encoding='utf-8').read()
checks = [
    ("logic/code schema documented",   'logic/code         data: {code: string' in final),
    ("tool/integration schema",        'tool/integration   data: {service: string' in final),
    ("Wrong example: string data",     'data\\\": \\\"...JS string...' in final),
    ("Wrong example: integration key", 'must use `service`, not `integration`' in final),
    ("Correct code node example",      '\\\"lang\\\": \\\"javascript\\\"' in final),
]
print("\nVERIFICATION:")
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("PROMPT SCHEMA PATCH COMPLETE")
    print()
    print("Next: git add server.py")
    print("      git commit -m 'Document exact node schema for AI'")
    print("      git push origin main")