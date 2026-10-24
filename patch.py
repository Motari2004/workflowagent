import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_ollama_revert')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    original = f.read()

print("File: {} chars".format(len(original)))
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Revert TOOLS entry: custom-ollama -> fa-brain
# ═══════════════════════════════════════════════════════════════
print("\n[1] Reverting Ollama TOOLS entry...")

# Match whatever the current entry looks like
ollama_pattern = re.compile(r"'ollama':\s*\{[^}]*\},")
new_entry = "'ollama':          { label:\"Ollama Cloud\",      icon:\"fa-brain\",           brand:false, color:\"#7C3AED\", creds:[\"api_key\",\"host\",\"model\"] },"

if ollama_pattern.search(original):
    original = ollama_pattern.sub(new_entry, original, count=1)
    changes += 1
    print("  OK — Ollama entry restored to fa-brain, purple color")
else:
    print("  FAIL — Ollama entry not found")

# ═══════════════════════════════════════════════════════════════
# 2. Remove the custom-ollama SVG branch from getToolIconHtml
# ═══════════════════════════════════════════════════════════════
print("\n[2] Removing custom-ollama SVG branch...")

ollama_svg_pattern = re.compile(
    r"\s*// Custom Ollama brand mark[^\n]*\n\s*if \(tool\.icon === 'custom-ollama'\) \{[\s\S]*?\n    \}\n",
    re.DOTALL
)

if ollama_svg_pattern.search(original):
    original = ollama_svg_pattern.sub("", original, count=1)
    changes += 1
    print("  OK — custom-ollama SVG branch removed")
else:
    print("  SKIP — no custom-ollama SVG branch found (already clean)")

# ═══════════════════════════════════════════════════════════════
# 3. Fix any double commas (safety net)
# ═══════════════════════════════════════════════════════════════
print("\n[3] Fixing double commas...")

double_comma_count = original.count('},,')
if double_comma_count > 0:
    original = original.replace('},,', '},')
    changes += double_comma_count
    print("  OK — fixed {} double comma(s)".format(double_comma_count))
else:
    print("  OK — no double commas")

# ═══════════════════════════════════════════════════════════════
# 4. Verify
# ═══════════════════════════════════════════════════════════════
print("\n[4] Verifying...")

checks = [
    ("Ollama uses fa-brain",          'icon:"fa-brain"' in original),
    ("Ollama color is #7C3AED",       '#7C3AED' in original),
    ("No custom-ollama in SVG",       "tool.icon === 'custom-ollama'" not in original),
    ("No double commas",              '},,' not in original),
    ("OpenAI still custom-openai",    'icon:"custom-openai"' in original),
    ("RSS still custom-rss",          'icon:"custom-rss"' in original),
    ("Twilio still custom-twilio",    'icon:"custom-twilio"' in original),
    ("Gmail still custom-gmail-envelope", 'icon:"custom-gmail-envelope"' in original),
    ("getToolIconHtml intact",        'function getToolIconHtml' in original),
    ("TOOLS object intact",           'const TOOLS = {' in original),
]

all_ok = True
for name, ok in checks:
    print("  [{}] {}".format("OK  " if ok else "FAIL", name))
    if not ok:
        all_ok = False

if not all_ok:
    print("\n  VERIFICATION FAILED — no changes written")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 5. Write
# ═══════════════════════════════════════════════════════════════
print("\n[5] Writing...")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(original)

print("  OK — wrote {} chars".format(len(original)))
print("  {} change(s) applied".format(changes))

print("\n" + "=" * 55)
print("PATCH COMPLETE")
print("=" * 55)
print()
print("Next:")
print("  git add public/index.html")
print("  git commit -m 'Revert Ollama to original fa-brain icon'")
print("  git push origin main")