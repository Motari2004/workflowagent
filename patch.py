# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')

if not os.path.exists(SERVER):
    print("FAIL: missing " + SERVER); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v10')
print("Backed up")

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

sc = 0

# ============================================================
# PATCH 1: For image/audio responses, return original URL (no bytes)
# ============================================================
print("\n[1] Image/audio responses return URL, not bytes...")

# Match the current binary save block. Two variants possible:
# 1. Post-patch8 (_IS_SERVERLESS present)
# 2. Original (write_bytes directly)
# Use a broad regex that catches the whole `if 'audio/' in content_type ...` branch
pat = re.compile(
    r"(if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:\n)([\s\S]*?)(\n\s{20,28}(?:else:|except |current_memory))",
)

m = pat.search(server)
if not m:
    print("  FAIL: binary block not found")
    sys.exit(1)

# Show what we found
print("  Found block ({} chars):".format(len(m.group(0))))
print("  First 200 chars: " + repr(m.group(0)[:200]))

# Replace everything inside the `if` block with a one-liner that returns the URL
new_inner = """                            # Image/audio URL responses: return the URL, do NOT download bytes.
                            # Instagram/Zernio need URLs. Bytes-in-/tmp breaks on Vercel and
                            # tool_zernio only accepts URLs anyway.
                            current_memory = url
                            logs.append(f"HTTP {r.status_code}: image/audio -> using URL {url[:80]}")
"""

# Preserve the closing token (m.group(3)) so the else/except/current_memory below still lines up
server = server[:m.start()] + m.group(1) + new_inner + m.group(3) + server[m.end():]
sc += 1
print("  OK: image/audio responses now return URL")

# ============================================================
# PATCH 2: For GET requests, capture redirect Location (safer version)
# ============================================================
print("\n[2] Adding GET redirect capture (safer)...")

# Only modify the `requests.request(...)` call — nothing else
old_req = '                        r = requests.request(method, url, **kwargs)'
new_req = '''                        # GET: capture redirect location instead of following
                        if method == 'GET':
                            kwargs["allow_redirects"] = False
                        r = requests.request(method, url, **kwargs)
                        if method == 'GET' and r.status_code in (301, 302, 303, 307, 308):
                            _loc = r.headers.get('Location', '')
                            if _loc:
                                current_memory = _loc
                                logs.append(f"HTTP {r.status_code}: redirect -> {_loc[:80]}")
                                continue'''

if old_req in server and 'redirect ->' not in server:
    server = server.replace(old_req, new_req, 1)
    sc += 1
    print("  OK: GET redirects captured")
else:
    if 'redirect ->' in server:
        print("  SKIP: redirect capture already present")
    else:
        print("  FAIL: requests.request line not found")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    # Show the offending lines
    lines = open(SERVER, encoding='utf-8').read().splitlines()
    if e.lineno and e.lineno <= len(lines):
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        print("  Context:")
        for i in range(start, end):
            marker = " >>> " if i == e.lineno - 1 else "     "
            print("  {}L{:4d}: {}".format(marker, i + 1, lines[i]))
    shutil.copy(SERVER + '.backup_v10', SERVER)
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
    ("image/audio returns URL",   "image/audio -> using URL" in fs),
    ("GET redirects captured",    "GET and r.status_code in (301, 302" in fs or "redirect ->" in fs),
    ("no write_bytes for images", "filepath.write_bytes(r.content)" not in fs),
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
    print("  git commit -m 'HTTP: URLs not bytes for image/audio'")
    print("  git push origin main")
else:
    print("Review FAIL lines. Backup: server.py.backup_v10")