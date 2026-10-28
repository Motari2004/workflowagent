#!/usr/bin/env python3
"""Fix the brace bug in syncWidgetsFromProperties."""
import re, sys
from pathlib import Path

INDEX = Path("public/index.html")

CORRECTED = r'''function syncWidgetsFromProperties(gr) {
    if (!gr || !gr._nodes) return;
    gr._nodes.forEach(function(node) {
        if (!node.widgets || !node.properties) return;
        for (var i = 0; i < node.widgets.length; i++) {
            var w = node.widgets[i];
            if (!w || !w.name) continue;
            var wName = w.name;
            if (typeof node.properties[wName] === "string") {
                w.value = node.properties[wName];
                continue;
            }
            var snake = wName.toLowerCase().replace(/[^a-z0-9]/g, "_");
            if (typeof node.properties[snake] === "string") {
                w.value = node.properties[snake];
                continue;
            }
            var simple = wName.toLowerCase().replace(/\s*\([^)]*\)/g, "").replace(/[^a-z0-9]/g, "_");
            if (typeof node.properties[simple] === "string") {
                w.value = node.properties[simple];
            }
        }
        if (node.type === "tool/integration" && typeof node.updateVisibility === "function") {
            node.updateVisibility();
        }
    });
}'''

PATTERN = re.compile(
    r"function\s+syncWidgetsFromProperties\s*\(gr\)\s*\{[\s\S]*?\n\}\s*\n(?=\s*//\s*=+\s*\n//\s*AI WORKFLOW LOADER)",
    re.DOTALL,
)

def main():
    if not INDEX.exists():
        print(f"[!] Not found: {INDEX}", file=sys.stderr); return 1
    html = INDEX.read_text(encoding="utf-8")
    
    # Idempotent check: if already fixed
    if "Re-apply tool widget visibility after load (OUTSIDE the widget loop)" in html:
        print("[=] Already fixed."); return 0
    
    new_html, n = PATTERN.subn(lambda m: CORRECTED + "\n", html, count=1)
    if n == 0:
        print("[!] Could not locate syncWidgetsFromProperties block.", file=sys.stderr); return 2
    
    backup = INDEX.with_suffix(".html.bak2")
    if not backup.exists():
        backup.write_text(html, encoding="utf-8")
        print(f"[+] Backup: {backup}")
    
    INDEX.write_text(new_html, encoding="utf-8")
    print(f"[✓] Fixed syncWidgetsFromProperties ({len(new_html)-len(html):+d} bytes)")
    return 0

if __name__ == "__main__":
    sys.exit(main())