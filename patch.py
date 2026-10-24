# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
HTML = os.path.join(PROJECT, 'public', 'index.html')

if not os.path.exists(HTML):
    print("FAIL: missing " + HTML); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_v13')
print("Backed up")

hc = 0

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ============================================================
# PATCH 1: Add template sanitizer + hook into NodeTool.onConfigure
# ============================================================
print("\n[1] Adding template sanitizer to NodeTool...")

# First, check what NodeTool.onConfigure looks like now
existing_oc = re.search(
    r'NodeTool\.prototype\.onConfigure\s*=\s*function\(info\)\s*\{[\s\S]*?\n\};',
    html
)

if not existing_oc:
    print("  FAIL: NodeTool.onConfigure not found")
    sys.exit(1)

# Replace the whole onConfigure with a version that sanitizes
new_oc = '''NodeTool.prototype.onConfigure = function(info) {
    // Clean any template syntax that a saved workflow might contain
    function stripTemplates(str) {
        if (typeof str !== 'string') return str;
        // Remove ${...} and {{...}} patterns - these aren't supported
        return str.replace(/\\$\\{[^}]*\\}/g, '').replace(/\\{\\{[^}]*\\}\\}/g, '').trim();
    }
    
    if (info && info.properties) {
        if (typeof info.properties.service === "string") this.properties.service = info.properties.service;
        if (typeof info.properties.message === "string") this.properties.message = stripTemplates(info.properties.message);
        if (typeof info.properties.platform === "string") this.properties.platform = info.properties.platform;
        if (typeof info.properties.media_urls === "string") this.properties.media_urls = stripTemplates(info.properties.media_urls);
    }
    
    // Sync widgets from cleaned properties
    if (this.widgets) {
        for (var i = 0; i < this.widgets.length; i++) {
            var w = this.widgets[i];
            if (w.name === "Service") w.value = this.properties.service || "discord";
            else if (w.name === "Message (opt)") w.value = this.properties.message || "";
            else if (w.name === "Platform") w.value = this.properties.platform || "instagram";
            else if (w.name === "Media URL (opt)") w.value = this.properties.media_urls || "";
        }
    }
};'''

html = html.replace(existing_oc.group(0), new_oc, 1)
hc += 1
print("  OK: onConfigure sanitizes templates")

# ============================================================
# PATCH 2: Add onWidgetChanged to strip templates while typing
# ============================================================
print("\n[2] Adding onWidgetChanged to strip templates on typing...")

# Find NodeTool.onConfigure (which we just replaced) and add onWidgetChanged after it
# Look for the closing of onConfigure
oc_end_pattern = re.compile(
    r'(NodeTool\.prototype\.onConfigure\s*=\s*function\(info\)\s*\{[\s\S]*?\n\};)',
    re.DOTALL
)

m = oc_end_pattern.search(html)
if m:
    widget_changed = m.group(1) + '''

NodeTool.prototype.onWidgetChanged = function(name, value, widget) {
    // Strip template syntax as soon as the user types or pastes
    function stripTemplates(str) {
        if (typeof str !== 'string') return str;
        return str.replace(/\\$\\{[^}]*\\}/g, '').replace(/\\{\\{[^}]*\\}\\}/g, '').trim();
    }
    
    if (name === "Message (opt)") {
        var cleaned = stripTemplates(value);
        if (cleaned !== value) {
            this.properties.message = cleaned;
            if (widget) widget.value = cleaned;
            if (this.graph && this.graph.canvas) this.graph.canvas.setDirty(true, true);
            if (typeof toast === 'function') toast('Template syntax not supported - removed', 'warn', 2000);
        }
    } else if (name === "Media URL (opt)") {
        var cleaned = stripTemplates(value);
        if (cleaned !== value) {
            this.properties.media_urls = cleaned;
            if (widget) widget.value = cleaned;
            if (this.graph && this.graph.canvas) this.graph.canvas.setDirty(true, true);
            if (typeof toast === 'function') toast('Template syntax not supported - removed', 'warn', 2000);
        }
    }
    // Call parent if exists
    if (LGraphNode.prototype.onWidgetChanged) {
        return LGraphNode.prototype.onWidgetChanged.apply(this, arguments);
    }
};'''
    html = html.replace(m.group(1), widget_changed, 1)
    hc += 1
    print("  OK: onWidgetChanged strips templates on typing")
else:
    print("  FAIL: could not find onConfigure closing bracket")
    sys.exit(1)

# ============================================================
# PATCH 3: buildPayload strips templates before sending
# ============================================================
print("\n[3] Stripping templates in buildPayload...")

old_bp = re.search(
    r"case 'tool/integration':\s*\{[\s\S]*?break;\s*\}",
    html
)

if not old_bp:
    print("  FAIL: buildPayload tool case not found")
    sys.exit(1)

new_bp = '''case 'tool/integration': {
                function stripT(str) {
                    if (typeof str !== 'string') return str;
                    return str.replace(/\\$\\{[^}]*\\}/g, '').replace(/\\{\\{[^}]*\\}\\}/g, '').trim();
                }
                const mediaStr = stripT(d.media_urls || '').trim();
                const mediaList = mediaStr ? mediaStr.split(/[,\\n]+/).map(s => stripT(s.trim())).filter(Boolean) : [];
                payload.push({type:'tool', data:{
                    service: d.service||'http-custom',
                    message: stripT(d.message || ''),
                    platform: d.platform||'instagram',
                    media_urls: mediaList
                }});
                break;
            }'''

html = html.replace(old_bp.group(0), new_bp, 1)
hc += 1
print("  OK: buildPayload strips templates")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ============================================================
# VERIFY
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fh = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("onConfigure strips templates",       "stripTemplates(info.properties.message)" in fh or "stripTemplates(info.properties.media_urls)" in fh),
    ("onWidgetChanged exists",             "NodeTool.prototype.onWidgetChanged" in fh),
    ("buildPayload strips message",        "message: stripT(d.message || '')" in fh),
    ("buildPayload strips media_urls",     "map(s => stripT(s.trim()))" in fh),
    ("template removal regex present",     "replace(/\\\\$\\\\{[^}]*\\\\}/g, '')" in fh),
]

ok = True
for name, passed in checks:
    print("  [{}] {}".format("OK  " if passed else "FAIL", name))
    if not passed: ok = False

print()
if ok:
    print("=" * 55)
    print("PATCH COMPLETE")
    print("=" * 55)
    print("html: {} changes".format(hc))
    print()
    print("Next:")
    print("  git add public/index.html")
    print("  git commit -m 'Tool node: strip {{...}} and ${...} templates everywhere'")
    print("  git push origin main")
else:
    print("Review FAIL lines. Backup: index.html.backup_v13")