import os, shutil, re

HTML_PATH = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML_PATH):
    print("Not found: " + HTML_PATH); exit(1)

shutil.copy(HTML_PATH, HTML_PATH + '.backup_no_online')
print("Backed up\n")

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html = f.read()

print("File: " + str(len(html)) + " chars\n")
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Remove the <span class="ai-status">...</span> block
# ═══════════════════════════════════════════════════════════════
print("[1] Removing status pill HTML...")

status_pattern = re.compile(
    r'\s*<span class="ai-status">\s*'
    r'<span class="ai-dot"></span>\s*'
    r'<span class="ai-status-label">[^<]*</span>\s*'
    r'</span>',
    re.DOTALL
)

if status_pattern.search(html):
    html = status_pattern.sub('', html, count=1)
    changes += 1
    print("  OK - status pill removed")
else:
    print("  SKIP - status pill not found")

# ═══════════════════════════════════════════════════════════════
# 2. Remove the .ai-status CSS rules
# ═══════════════════════════════════════════════════════════════
print("\n[2] Removing status pill CSS...")

status_css_pattern = re.compile(
    r'\s*\.ai-status\s*\{[^}]*\}\s*'
    r'\.ai-status\s+\.ai-dot\s*\{[^}]*\}\s*'
    r'\.ai-status-label\s*\{[^}]*\}',
    re.DOTALL
)

if status_css_pattern.search(html):
    html = status_css_pattern.sub('', html, count=1)
    changes += 1
    print("  OK - status pill CSS removed")
else:
    print("  SKIP - status CSS not found")

# ═══════════════════════════════════════════════════════════════
# 3. Adjust title wrapper — no longer needs flex-direction column
#    (keeps it consistent so "AI Assistant" is vertically centered)
# ═══════════════════════════════════════════════════════════════
print("\n[3] Tightening title text wrapper...")

old_wrapper = '''.ai-title-text {
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
        }'''
new_wrapper = '''.ai-title-text {
            display: flex;
            align-items: center;
            min-width: 0;
        }'''

if old_wrapper in html:
    html = html.replace(old_wrapper, new_wrapper, 1)
    changes += 1
    print("  OK - title wrapper simplified")
else:
    print("  SKIP - wrapper rule not matched (layout still fine)")

# ═══════════════════════════════════════════════════════════════
# 4. Adjust collapsed height back (46 -> 42 is enough without the pill)
# ═══════════════════════════════════════════════════════════════
print("\n[4] Adjusting collapsed height...")

old_height = '''#aiPanel.collapsed {
            height: 46px;
        }'''
new_height = '''#aiPanel.collapsed {
            height: 42px;
        }'''

if old_height in html:
    html = html.replace(old_height, new_height, 1)
    changes += 1
    print("  OK - collapsed height 46px -> 42px")
else:
    print("  SKIP - collapsed height not 46px (fine)")

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print("\n" + "=" * 55)
print("Wrote " + str(len(html)) + " chars — " + str(changes) + " change(s)")
print("=" * 55)

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    final = f.read()

print("\nVERIFICATION:")
checks = [
    ("Status pill HTML gone",      'class="ai-status"' not in final),
    ("Status label gone",          'ai-status-label' not in final),
    ("Status CSS gone",            '.ai-status {' not in final),
    ("Title still present",        'class="ai-title-main"' in final),
    ("Icon badge still present",   'class="ai-icon-badge"' in final),
    ("Model selector still there", 'id="aiModelSelector"' in final),
    ("Clear button still there",   'id="aiClearBtn"' in final),
]
all_ok = True
for name, ok in checks:
    print("  [" + ("OK  " if ok else "FAIL") + "] " + name)
    if not ok:
        all_ok = False

print()
if all_ok and changes > 0:
    print("PATCH COMPLETE")
elif changes == 0:
    print("NOTHING CHANGED — already patched, or markup differs")
else:
    print("PARTIAL — review FAIL lines")

print()
print("Hard refresh: Ctrl+Shift+R")
print()
print("The header should now read just:")
print("  [robot icon]  AI Assistant        [Gemini ▼]  [🗑]")