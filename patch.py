import os, shutil

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_jsdata')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

# The EXACT old template block as it appears in your server.py
old_template = '''    template = r"""
const fs = require('fs');
const _input = fs.readFileSync(process.argv[2], 'utf-8');
let _output = _input;
function output(val) { _output = typeof val === 'string' ? val : JSON.stringify(val); }
const input = _input;
(async () => {
    try {
""" + user_code + r"""
        process.stdout.write(String(_output));
    } catch (err) {
        process.stderr.write("ERROR: " + (err && err.stack ? err.stack : String(err)));
        process.exit(1);
    }
})();
"""'''

new_template = '''    template = r"""
const fs = require('fs');
const _input = fs.readFileSync(process.argv[2], 'utf-8');
let _output = _input;
function output(val) { _output = typeof val === 'string' ? val : JSON.stringify(val); }

// Auto-parse `input` into `data` so JS Code nodes can use either style.
let _jsonText = _input;
if (typeof _jsonText === 'string' && _jsonText.startsWith('HTTP ')) {
    const _ci = _jsonText.indexOf(':');
    if (_ci > 0) _jsonText = _jsonText.slice(_ci + 1).trim();
}
let data = null;
try {
    data = JSON.parse(_jsonText);
    if (data && typeof data.response === 'string') {
        try { data = JSON.parse(data.response); } catch (_) {}
    }
} catch (_) { data = null; }

const input = _input;
(async () => {
    try {
""" + user_code + r"""
        process.stdout.write(String(_output));
    } catch (err) {
        process.stderr.write("ERROR: " + (err && err.stack ? err.stack : String(err)));
        process.exit(1);
    }
})();
"""'''

if old_template in code:
    code = code.replace(old_template, new_template, 1)
    print("[1] Replaced template — `data` is now auto-parsed")
elif 'let data = null;' in code and 'JSON.parse(_jsonText)' in code:
    print("[1] Already patched — no change")
else:
    print("[1] FAIL — could not find exact template block")
    print("    The block may have been modified. Trying regex fallback...")

    import re
    pattern = re.compile(
        r"    template = r\"\"\"\s*\n"
        r"const fs = require\('fs'\);.*?"
        r"const input = _input;",
        re.DOTALL
    )
    match = pattern.search(code)
    if match:
        code = code[:match.start()] + new_template.split('""" + user_code')[0] + '"""' + code[match.end() - len('const input = _input;'):]
        print("[1] Regex fallback applied")
    else:
        print("[1] Regex also failed — aborting")
        print("    Search server.py for: template = r\"\"\"")
        exit(1)

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\nCompiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_jsdata', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

# Verify
final = open(SERVER, 'r', encoding='utf-8').read()
checks = [
    ("data auto-parsed",       "let data = null;" in final),
    ("HTTP prefix handling",   "_jsonText.startsWith('HTTP ')" in final),
    ("response re-parsed",     "JSON.parse(data.response)" in final),
    ("input still available",  "const input = _input;" in final),
    ("output() function",      "function output(val)" in final),
]
print("\nVERIFICATION:")
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("PATCH COMPLETE")
    print()
    print("Next:")
    print("  git add server.py")
    print("  git commit -m 'Auto-parse data in JS wrapper'")
    print("  git push origin main")