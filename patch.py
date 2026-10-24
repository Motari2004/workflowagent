import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_ai_nudge')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("File: {} chars".format(len(html)))
changes = 0

# ═══════════════════════════════════════════════════════════════
# Replace the collapsed header rules with vertical-centering-safe versions
# ═══════════════════════════════════════════════════════════════
print("[1] Removing previous collapsed-header rules if any...")

# Remove the whole "#aiPanel.collapsed #aiHeader {...} ... #aiPanel.collapsed #aiHeader #aiClearBtn {...}" block
pattern = re.compile(
    r"\s*/\* Collapsed: header fills the panel and centers all content \*/[\s\S]*?(?=#aiPanel\.collapsed #aiBody|/\*[^*]*\*/|#aiBody)",
    re.DOTALL
)
if pattern.search(html):
    html = pattern.sub("", html, count=1)
    print("  OK — old collapsed header rules removed")

print("\n[2] Adding refined centering rules...")

# Anchor: right after the #aiPanel.collapsed block
anchor = re.compile(
    r"(#aiPanel\.collapsed \{[\s\S]*?\}\s*)",
    re.DOTALL
)

new_rules = '''

        /* ── Collapsed AI panel: force-vertical-center everything ── */
        #aiPanel.collapsed {
            height: 44px;
            min-height: 44px;
            max-height: 44px;
        }
        #aiPanel.collapsed #aiHeader {
            height: 44px;
            min-height: 44px;
            padding: 0 10px 0 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            line-height: 1;
            overflow: hidden;
        }
        #aiPanel.collapsed #aiHeader .ai-title {
            align-items: center;
            gap: 8px;
            line-height: 1;
            height: 100%;
        }
        #aiPanel.collapsed #aiHeader .ai-title-text {
            align-items: center;
            line-height: 1;
            height: 100%;
        }
        #aiPanel.collapsed #aiHeader .ai-title-main {
            font-size: 12px;
            line-height: 1;
            display: flex;
            align-items: center;
            height: 100%;
        }
        #aiPanel.collapsed #aiHeader .ai-icon-badge {
            width: 24px;
            height: 24px;
            margin: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        #aiPanel.collapsed #aiHeader .ai-icon-badge i {
            font-size: 11px;
            line-height: 1;
            display: block;
        }
        #aiPanel.collapsed #aiHeader .ai-header-actions {
            align-items: center;
            height: 100%;
            gap: 6px;
        }
        #aiPanel.collapsed #aiHeader #aiModelSelector {
            height: 22px;
            padding: 0 18px 0 6px;
            font-size: 9px;
            line-height: 22px;
            background-position: right 5px center;
        }
        #aiPanel.collapsed #aiHeader #aiClearBtn {
            width: 22px;
            height: 22px;
            padding: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        #aiPanel.collapsed #aiHeader #aiClearBtn i {
            font-size: 10px;
            line-height: 1;
        }
        /* Hide the accent bar in collapsed state to avoid it shifting padding */
        #aiPanel.collapsed .ai-header-accent {
            display: none;
        }
        #aiPanel.collapsed #aiBody,
        #aiPanel.collapsed #aiInputRow,
        #aiPanel.collapsed #aiQuickActions {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
        }
'''

m = anchor.search(html)
if m:
    # Insert after the #aiPanel.collapsed { ... } block
    insert_pos = m.end()
    html = html[:insert_pos] + new_rules + html[insert_pos:]
    changes += 1
    print("  OK — new centering rules inserted")
else:
    print("  FAIL — could not locate #aiPanel.collapsed block")
    sys.exit(1)

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
print("\n[3] Verifying...")

final = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("44px collapsed height",         'height: 44px;\n            min-height: 44px;\n            max-height: 44px;' in final),
    ("header align-items center",     '#aiPanel.collapsed #aiHeader {' in final and 'align-items: center' in final),
    ("header line-height 1",          'line-height: 1;' in final),
    ("title height 100%",             '.ai-title-main {\n            font-size: 12px;\n            line-height: 1;\n            display: flex;\n            align-items: center;\n            height: 100%;' in final),
    ("icon badge 24x24",              '#aiPanel.collapsed #aiHeader .ai-icon-badge {\n            width: 24px;' in final),
    ("selector height 22px",          '#aiPanel.collapsed #aiHeader #aiModelSelector {\n            height: 22px;' in final),
    ("accent bar hidden",             '#aiPanel.collapsed .ai-header-accent {\n            display: none;' in final),
    ("body hidden with important",    'display: none !important;' in final),
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
    print("  git add public/index.html")
    print("  git commit -m 'AI panel: vertically center collapsed header content'")
    print("  git push origin main")
else:
    print("Review FAIL lines above")
    print("Backup: index.html.backup_ai_nudge")