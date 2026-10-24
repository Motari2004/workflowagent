# -*- coding: utf-8 -*-
import os, shutil, sys, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'
if not os.path.exists(SERVER):
    print("FAIL: missing server.py"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v17')
print("Backed up")

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# ============================================================
# Add full request body dump to tool_zernio
# ============================================================
print("\n[1] Adding payload dump to tool_zernio...")

# Find the requests.post call inside tool_zernio
# Match: the "try:" before requests.post, insert a dump BEFORE the post
old_post = '''    try:
        r = requests.post(
            "https://zernio.com/api/v1/posts",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )'''

new_post = '''    print("[zernio] ===== FULL PAYLOAD =====")
    print("[zernio] keys: " + str(list(payload.keys())))
    for k, v in payload.items():
        print("[zernio]   " + k + " = " + repr(v)[:300])
    print("[zernio] =========================")

    try:
        r = requests.post(
            "https://zernio.com/api/v1/posts",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        print("[zernio] RESPONSE " + str(r.status_code) + ": " + r.text[:500])'''

if old_post in server:
    server = server.replace(old_post, new_post, 1)
    print("  OK: payload dump added")
else:
    print("  FAIL: requests.post pattern not matched")
    sys.exit(1)

# ============================================================
# Also dump what media_urls arrives as
# ============================================================
print("\n[2] Adding media_urls source diagnostic...")

old_media = '''    media_urls = (extra or {}).get("media_urls") or []'''

if old_media in server:
    new_media = '''    print("[zernio] === ENTRY POINT ===")
    print("[zernio] extra type: " + str(type(extra)))
    print("[zernio] extra: " + repr(extra)[:500])
    print("[zernio] extra.media_urls: " + repr((extra or {}).get("media_urls")))
    
    media_urls = (extra or {}).get("media_urls") or []'''
    server = server.replace(old_media, new_media, 1)
    print("  OK: entry-point diagnostic added")
else:
    print("  SKIP: media_urls line not matched")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_v17', SERVER)
    print("  Restored from backup")
    sys.exit(1)

print()
print("=" * 55)
print("PATCH COMPLETE")
print("=" * 55)
print()
print("Next:")
print("  1. taskkill /F /IM python.exe")
print("  2. python server.py")
print("  3. In browser: http://localhost:10000")
print("  4. Hard refresh (Ctrl+Shift+R)")
print("  5. Execute the workflow")
print("  6. Paste ALL [zernio] lines from the terminal")