# -*- coding: utf-8 -*-
import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'
if not os.path.exists(HTML):
    print("FAIL: missing index.html"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_v28')
print("Backed up")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# Find the tool/integration case in buildPayload
old_case = re.search(
    r"case 'tool/integration':\s*\{[\s\S]*?break;\s*\}",
    html
)

if not old_case:
    print("FAIL: buildPayload tool case not found")
    sys.exit(1)

new_case = '''case 'tool/integration': {
                function stripTemplates(str) {
                    if (typeof str !== 'string') return str;
                    return str.replace(/\\$\\{[^}]*\\}/g, '').replace(/\\{\\{[^}]*\\}\\}/g, '').trim();
                }

                // Bulletproof media URL parser.
                // SPECIAL CASE: if the value is exactly "FROM_PREVIOUS" (or the
                // array ["FROM_PREVIOUS"]), pass it through untouched. The server
                // resolves it against the previous node's JSON output.
                function parseMediaUrls(raw) {
                    // Detect FROM_PREVIOUS early
                    if (raw === 'FROM_PREVIOUS') return ['FROM_PREVIOUS'];
                    if (Array.isArray(raw) && raw.length === 1 && raw[0] === 'FROM_PREVIOUS') {
                        return ['FROM_PREVIOUS'];
                    }
                    
                    var result = [];

                    function pushUrl(u) {
                        if (typeof u !== 'string') return;
                        var s = stripTemplates(u);
                        if (!s) return;
                        if (s.startsWith('http://') || s.startsWith('https://')) {
                            result.push(s);
                        }
                    }

                    function walk(val, depth) {
                        if (depth > 5) return;
                        if (val === null || val === undefined) return;
                        if (val === 'FROM_PREVIOUS') {
                            result.push('FROM_PREVIOUS');
                            return;
                        }
                        if (Array.isArray(val)) {
                            for (var i = 0; i < val.length; i++) walk(val[i], depth + 1);
                            return;
                        }
                        if (typeof val !== 'string') return;
                        var s = stripTemplates(val);
                        if (!s) return;
                        var trimmed = s.trim();
                        if (trimmed === 'FROM_PREVIOUS') {
                            result.push('FROM_PREVIOUS');
                            return;
                        }
                        if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                            try {
                                var parsed = JSON.parse(trimmed);
                                walk(parsed, depth + 1);
                                return;
                            } catch (_) {}
                        }
                        if (trimmed.startsWith('"') && trimmed.endsWith('"') && trimmed.length > 2) {
                            try {
                                var inner = JSON.parse(trimmed);
                                walk(inner, depth + 1);
                                return;
                            } catch (_) {}
                        }
                        if (trimmed.indexOf(',') !== -1 || trimmed.indexOf('\\n') !== -1) {
                            var parts = trimmed.split(/[,\\n]+/);
                            for (var j = 0; j < parts.length; j++) pushUrl(parts[j]);
                            return;
                        }
                        pushUrl(trimmed);
                    }
                    walk(raw, 0);

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

html = html.replace(old_case.group(0), new_case, 1)
print("OK: buildPayload preserves FROM_PREVIOUS")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

fh = open(HTML, 'r', encoding='utf-8').read()
if 'preserves FROM_PREVIOUS' in fh or "raw === 'FROM_PREVIOUS'" in fh:
    print("\nPATCH COMPLETE")
    print("Next:")
    print("  git add public/index.html")
    print("  git commit -m 'buildPayload: preserve FROM_PREVIOUS placeholder'")
    print("  git push origin main")
    print()
    print("Then:")
    print("  Hard refresh browser (Ctrl+Shift+R)")
    print("  Reload workflow")
    print("  Execute")
else:
    print("\nFAIL: patch did not apply")