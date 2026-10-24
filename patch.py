import os, shutil, sys

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: index.html not found")
    sys.exit(1)

backup = HTML + '.backup_biggericons'
shutil.copy(HTML, backup)
print(f"Backed up to {backup}\n")

with open(HTML, 'r', encoding='utf-8') as f:
    original = f.read()

print(f"File: {len(original)} chars")
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Increase .tool-icon container size: 28px -> 36px
# ═══════════════════════════════════════════════════════════════
print("\n[1] Increasing .tool-icon container (28px -> 36px)...")

old_css = '''.tool-icon {
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
            background: rgba(148, 163, 184, 0.06);
            border: 1px solid rgba(148, 163, 184, 0.08);
            flex-shrink: 0;
            transition: all 0.15s ease;
        }'''

new_css = '''.tool-icon {
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            background: rgba(148, 163, 184, 0.06);
            border: 1px solid rgba(148, 163, 184, 0.08);
            flex-shrink: 0;
            transition: all 0.15s ease;
        }'''

if old_css in original:
    original = original.replace(old_css, new_css, 1)
    changes += 1
    print("  OK - .tool-icon 28x28 -> 36x36")
else:
    print("  SKIP - .tool-icon block not matched (may already be modified)")

# Also increase the icon font size inside .tool-icon for FA icons
old_fa = '''.tool-icon i {
            font-size: 14px;
            color: var(--tool-color, #94a3b8);
            opacity: 0.9;
            transition: opacity 0.15s ease;
        }'''

new_fa = '''.tool-icon i {
            font-size: 18px;
            color: var(--tool-color, #94a3b8);
            opacity: 0.9;
            transition: opacity 0.15s ease;
        }'''

if old_fa in original:
    original = original.replace(old_fa, new_fa, 1)
    changes += 1
    print("  OK - .tool-icon i 14px -> 18px")
else:
    print("  SKIP - .tool-icon i block not matched")

# ═══════════════════════════════════════════════════════════════
# 2. Increase SVG size in credentials panel: 14 -> 20
# ═══════════════════════════════════════════════════════════════
print("\n[2] Increasing credentials panel SVG size (14 -> 20)...")

# The credentials list calls: getToolIconHtml(key, 14)
old_call = '${getToolIconHtml(key, 14)}'
new_call = '${getToolIconHtml(key, 20)}'

count = original.count(old_call)
if count > 0:
    original = original.replace(old_call, new_call)
    changes += count
    print(f"  OK - bumped {count} call(s) from 14 to 20")
else:
    print("  SKIP - no '${getToolIconHtml(key, 14)}' calls found")

# ═══════════════════════════════════════════════════════════════
# 3. Increase edit credentials modal header icon: 16 -> 22
# ═══════════════════════════════════════════════════════════════
print("\n[3] Increasing edit modal header icon (16 -> 22)...")

old_modal = '${getToolIconHtml(service, 16)}'
new_modal = '${getToolIconHtml(service, 22)}'

count = original.count(old_modal)
if count > 0:
    original = original.replace(old_modal, new_modal)
    changes += count
    print(f"  OK - bumped {count} modal call(s) from 16 to 22")
else:
    print("  SKIP - no '${getToolIconHtml(service, 16)}' calls found")

# ═══════════════════════════════════════════════════════════════
# 4. Also bump the tool label size for better proportion
# ═══════════════════════════════════════════════════════════════
print("\n[4] Increasing tool label size for balance...")

# In credentials panel, the label is 'text-xs' (12px). Bump to text-sm (14px).
old_label = '<span class="text-xs font-bold text-slate-200 flex-1">${tool.label}</span>'
new_label = '<span class="text-sm font-bold text-slate-200 flex-1">${tool.label}</span>'

if old_label in original:
    original = original.replace(old_label, new_label, 1)
    changes += 1
    print("  OK - label text-xs -> text-sm (12px -> 14px)")
else:
    print("  SKIP - label pattern not matched")

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
print("\n[5] Verifying...")

# Size sanity
size_diff = len(original) - len(backup) if os.path.exists(backup) else 0
if abs(size_diff) > 5000:
    print(f"  ERROR: suspicious size change ({size_diff} chars)")
    print("  Aborting")
    sys.exit(1)

checks = [
    ("tool-icon is 36px",        'width: 36px;\n            height: 36px' in original),
    ("tool-icon i is 18px",       'font-size: 18px;' in original),
    ("credentials icon 20px",     '${getToolIconHtml(key, 20)}' in original),
    ("modal icon 22px",            '${getToolIconHtml(service, 22)}' in original),
    ("label text-sm",              'text-sm font-bold text-slate-200' in original),
    ("getToolIconHtml intact",     'function getToolIconHtml' in original),
    ("custom-gmail-envelope",      'custom-gmail-envelope' in original),
    ("custom-zernio",              'custom-zernio' in original),
    ("TOOLS object intact",        'const TOOLS = {' in original),
]

all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

if not all_ok:
    print("\n  VERIFICATION FAILED — no changes written")
    print(f"  Backup at {backup}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
print("\n[6] Writing...")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(original)

print(f"  OK - wrote {len(original)} chars")
print(f"  {changes} change(s) applied")

print("\n" + "=" * 55)
print("PATCH COMPLETE")
print("=" * 55)
print()
print("Next:")
print("  git add public/index.html")
print("  git commit -m 'Increase tool icon sizes: 28px -> 36px containers, larger SVGs'")
print("  git push origin main")
print()
print("Then hard-refresh: Ctrl+Shift+R")