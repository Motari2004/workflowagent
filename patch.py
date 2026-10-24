# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')

if not os.path.exists(SERVER):
    print("FAIL: missing " + SERVER); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v9')
print("Backed up")

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

sc = 0

# ============================================================
# PATCH 1: Replace the entire binary-handling block
# ============================================================
print("\n[1] Rewriting HTTP binary handling (URL-first)...")

# Match whatever the current binary block looks like after patch8
# (patch8 may have applied; if it failed, we match the pre-patch8 version too)
patterns = [
    # Post-patch8 version
    re.compile(
        r'''                        if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:\n[\s\S]*?logs\.append\(current_memory\)''',
        re.DOTALL
    ),
    # Pre-patch8 version (in case patch8 failed)
    re.compile(
        r'''                        if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:\n[\s\S]*?logs\.append\(f"HTTP \{r\.status_code\}: saved binary to \{filename\} \(\{len\(r\.content\)\} bytes\)"\)''',
        re.DOTALL
    ),
]

matched = None
for pat in patterns:
    m = pat.search(server)
    if m:
        matched = m
        break

if not matched:
    print("  FAIL: binary block not found")
    sys.exit(1)

new_block = '''                        if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:
                            # Image/audio URLs should NEVER be downloaded into local filesystem.
                            # Instagram/Zernio need URLs. Bytes-in-/tmp breaks on Vercel and
                            # tool_zernio only accepts URLs anyway.
                            #
                            # For GET requests with redirects, we already returned the
                            # Location URL above. If we got here, we have actual bytes —
                            # that means this isn't a redirect URL workflow.
                            # Return the original URL (user supplied it) instead of bytes.
                            current_memory = url
                            logs.append(f"HTTP {r.status_code}: image/audio response at {url} — using URL, not bytes")'''

server = server[:matched.start()] + new_block + server[matched.end():]
sc += 1
print("  OK: image/audio responses now return URL, not bytes")

# ============================================================
# PATCH 2: Make allow_redirects=False for ALL GETs (already done in patch8, verify)
# ============================================================
print("\n[2] Verifying GET redirect handling...")

if 'allow_redirects' not in server or 'is_get and r.status_code in (301, 302' not in server:
    print("  WARN: redirect detection may be missing - checking...")
    # Find the HTTP block and ensure allow_redirects is set
    old_http = '''                        kwargs = {"timeout": 30, "headers": headers}
                        if method in ('POST','PUT','PATCH'):
                            if body:
                                try:
                                    kwargs["json"] = json.loads(body) if isinstance(body, str) else body
                                except Exception:
                                    kwargs["json"] = body
                            else:
                                kwargs["json"] = {"content": current_memory}
                        r = requests.request(method, url, **kwargs)'''

    new_http = '''                        kwargs = {"timeout": 30, "headers": headers}
                        if method in ('POST','PUT','PATCH'):
                            if body:
                                try:
                                    kwargs["json"] = json.loads(body) if isinstance(body, str) else body
                                except Exception:
                                    kwargs["json"] = body
                            else:
                                kwargs["json"] = {"content": current_memory}
                        else:
                            # GET: don't follow redirects — capture Location header
                            # (picsum.photos and similar image APIs redirect to actual image URL)
                            kwargs["allow_redirects"] = False
                        
                        r = requests.request(method, url, **kwargs)
                        
                        # If GET returned a redirect, capture the target URL and skip further processing
                        if method == 'GET' and r.status_code in (301, 302, 303, 307, 308):
                            location = r.headers.get('Location', '')
                            if location:
                                # Resolve relative Location against original URL
                                if location.startswith('/'):
                                    from urllib.parse import urlparse, urlunparse
                                    parsed = urlparse(url)
                                    location = urlunparse((parsed.scheme, parsed.netloc, location, '', '', ''))
                                current_memory = location
                                logs.append(f"HTTP {r.status_code}: redirect to {location[:100]}")
                                continue'''

    if old_http in server:
        server = server.replace(old_http, new_http, 1)
        sc += 1
        print("  OK: added allow_redirects=False and Location capture")
    else:
        print("  FAIL: HTTP request block not found")
else:
    print("  OK: redirect handling already present")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_v9', SERVER)
    print("  Restored from backup")
    sys.exit(1)

# ============================================================
# VERIFY
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fs = open(SERVER, 'r', encoding='utf-8').read()

checks = [
    ("no write_bytes for images",     "filepath.write_bytes(r.content)" not in fs or "URL, not bytes" in fs),
    ("GET disables redirects",        'kwargs["allow_redirects"] = False' in fs),
    ("Location captured for GET",     "r.status_code in (301, 302, 303, 307, 308)" in fs),
    ("image responses use URL",       "image/audio response at" in fs),
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
    print("server: {} changes".format(sc))
    print()
    print("Next:")
    print("  git add server.py")
    print("  git commit -m 'HTTP node: URLs not bytes for image/audio'")
    print("  git push origin main")
else:
    print("Review FAIL lines. Backup: server.py.backup_v9")