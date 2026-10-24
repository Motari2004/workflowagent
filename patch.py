# -*- coding: utf-8 -*-
import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'
if not os.path.exists(HTML):
    print("FAIL: missing index.html"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_v22')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ============================================================
# Replace the tool/integration case in buildPayload
# ============================================================
print("[1] Replacing buildPayload tool case...")

# Match the entire case block regardless of current shape
pattern = re.compile(
    r"case 'tool/integration':\s*\{[\s\S]*?break;\s*\}",
    re.DOTALL
)

m = pattern.search(html)
if not m:
    print("FAIL: buildPayload tool case not found")
    sys.exit(1)

old_block = m.group(0)
print("  Found existing block ({} chars)".format(len(old_block)))

new_block = '''case 'tool/integration': {
                function stripTemplates(str) {
                    if (typeof str !== 'string') return str;
                    return str.replace(/\\$\\{[^}]*\\}/g, '').replace(/\\{\\{[^}]*\\}\\}/g, '').trim();
                }

                // Bulletproof media URL parser.
                // Accepts:
                //   - Bare URL: "https://a.com/x.jpg"
                //   - Array: ["https://a.com/x.jpg"]
                //   - JSON array string: '["https://a.com/x.jpg"]'
                //   - Comma-separated: "https://a.com/x.jpg, https://b.com/y.jpg"
                //   - Newline-separated
                //   - Nested JSON array strings inside arrays
                //   - Template syntax: "${...}" (stripped)
                // Returns: array of clean, valid URLs.
                function parseMediaUrls(raw) {
                    var result = [];
                    
                    function pushUrl(u) {
                        if (typeof u !== 'string') return;
                        var s = stripTemplates(u);
                        if (!s) return;
                        // Must look like a URL
                        if (s.startsWith('http://') || s.startsWith('https://')) {
                            result.push(s);
                        }
                    }
                    
                    function walk(val, depth) {
                        if (depth > 5) return;  // safety against deeply nested
                        if (val === null || val === undefined) return;
                        
                        if (Array.isArray(val)) {
                            for (var i = 0; i < val.length; i++) walk(val[i], depth + 1);
                            return;
                        }
                        
                        if (typeof val !== 'string') return;
                        
                        var s = stripTemplates(val);
                        if (!s) return;
                        
                        // Try JSON parse if it looks like an array
                        var trimmed = s.trim();
                        if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                            try {
                                var parsed = JSON.parse(trimmed);
                                walk(parsed, depth + 1);
                                return;
                            } catch (_) { /* fall through */ }
                        }
                        
                        // Try JSON parse if it looks like a single JSON string "\"...\""
                        if (trimmed.startsWith('"') && trimmed.endsWith('"') && trimmed.length > 2) {
                            try {
                                var inner = JSON.parse(trimmed);
                                walk(inner, depth + 1);
                                return;
                            } catch (_) { /* fall through */ }
                        }
                        
                        // Comma or newline separated?
                        if (trimmed.indexOf(',') !== -1 || trimmed.indexOf('\\n') !== -1) {
                            var parts = trimmed.split(/[,\\n]+/);
                            for (var j = 0; j < parts.length; j++) pushUrl(parts[j]);
                            return;
                        }
                        
                        // Bare URL
                        pushUrl(trimmed);
                    }
                    
                    walk(raw, 0);
                    
                    // Dedupe while preserving order
                    var seen = {};
                    var deduped = [];
                    for (var k = 0; k < result.length; k++) {
                        if (!seen[result[k]]) {
                            seen[result[k]] = true;
                            deduped.push(result[k]);
                        }
                    }
                    return deduped;
                }

                const mediaList = parseMediaUrls(d.media_urls);
                const cleanMessage = stripTemplates(d.message || '');
                // If message somehow ended up as a JSON array string, blank it
                const messageFinal = (cleanMessage.startsWith('[') && cleanMessage.endsWith(']'))
                    ? ''
                    : cleanMessage;

                payload.push({type:'tool', data:{
                    service: d.service || 'http-custom',
                    message: messageFinal,
                    platform: d.platform || 'instagram',
                    media_urls: mediaList
                }});
                break;
            }'''

html = html.replace(old_block, new_block, 1)
print("  OK: buildPayload tool case replaced with bulletproof parser")

# ============================================================
# Also update NodeTool.onConfigure to auto-clean the widget on load
# ============================================================
print("\n[2] Adding auto-clean to NodeTool.onConfigure...")

old_oc = re.search(
    r'NodeTool\.prototype\.onConfigure\s*=\s*function\(info\)\s*\{[\s\S]*?\n\};',
    html
)

if old_oc:
    new_oc = '''NodeTool.prototype.onConfigure = function(info) {
    // Clean any template syntax AND brackets that a saved workflow might contain
    function clean(str) {
        if (typeof str !== 'string') return str;
        // Strip templates
        var s = str.replace(/\\$\\{[^}]*\\}/g, '').replace(/\\{\\{[^}]*\\}\\}/g, '').trim();
        // Unwrap JSON array string: ["https://..."] -> https://...
        if (s.startsWith('[') && s.endsWith(']')) {
            try {
                var parsed = JSON.parse(s);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    s = String(parsed[0]).trim();
                } else {
                    s = '';
                }
            } catch (_) {
                // Not valid JSON — try naive strip
                s = s.replace(/^\\[\\s*"?/, '').replace(/"?\\s*\\]$/, '').trim();
            }
        }
        // Strip surrounding quotes
        if (s.startsWith('"') && s.endsWith('"') && s.length > 2) {
            s = s.slice(1, -1).trim();
        }
        return s;
    }
    
    if (info && info.properties) {
        if (typeof info.properties.service === "string") this.properties.service = info.properties.service;
        if (typeof info.properties.message === "string") this.properties.message = clean(info.properties.message);
        if (typeof info.properties.platform === "string") this.properties.platform = info.properties.platform;
        if (typeof info.properties.media_urls === "string") this.properties.media_urls = clean(info.properties.media_urls);
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
    html = html.replace(old_oc.group(0), new_oc, 1)
    print("  OK: onConfigure cleans brackets on load")
else:
    print("  SKIP: onConfigure not found")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ============================================================
# Verify
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fh = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("parseMediaUrls function present",  "function parseMediaUrls(raw)" in fh),
    ("handles JSON array strings",       "JSON.parse(trimmed)" in fh),
    ("handles comma separated",          "trimmed.split(/[,\\\\n]+/)" in fh or "trimmed.split(/[,\\n]+/)" in fh),
    ("handles nested arrays",            "walk(parsed, depth + 1)" in fh),
    ("dedupes results",                  "if (!seen[result[k]])" in fh),
    ("onConfigure cleans brackets",      "Unwrap JSON array string" in fh),
    ("filters to valid URLs only",       "s.startsWith('http://') || s.startsWith('https://')" in fh),
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
    print("\nNext:")
    print("  git add public/index.html")
    print("  git commit -m 'buildPayload: bulletproof media URL parsing'")
    print("  git push origin main")
    print()
    print("Then:")
    print("  1. Hard refresh browser (Ctrl+Shift+R)")
    print("  2. Reload the workflow")
    print("  3. Execute — should work even with brackets in the widget")
else:
    print("Review FAIL lines. Backup: index.html.backup_v22")