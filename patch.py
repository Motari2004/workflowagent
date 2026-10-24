# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')

if not os.path.exists(SERVER):
    print("FAIL: missing server.py"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v14')
print("Backed up")

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

sc = 0

# ============================================================
# PATCH 1: Fix the orphaned binary-save code block
# ============================================================
print("\n[1] Fixing orphaned image/audio block...")

old_binary = '''                        if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:
                            # Image/audio URL responses: return the URL, do NOT download bytes.
                            # Instagram/Zernio need URLs. Bytes-in-/tmp breaks on Vercel and
                            # tool_zernio only accepts URLs anyway.
                            current_memory = url
                            logs.append(f"HTTP {r.status_code}: image/audio -> using URL {url[:80]}")

                            current_memory = str(filepath.absolute())
                            logs.append(f"HTTP {r.status_code}: saved binary to {filename} ({len(r.content)} bytes)")
                        else:
                            full_text = r.text
                            preview = full_text[:250] + ('...' if len(full_text) > 250 else '')
                            current_memory = f"HTTP {r.status_code}: {full_text}"
                            logs.append(f"HTTP {r.status_code}: {preview}")'''

new_binary = '''                        if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:
                            # Return the URL instead of downloading bytes.
                            current_memory = url
                            logs.append(f"HTTP {r.status_code}: image/audio -> {url[:80]}")
                        else:
                            full_text = r.text
                            preview = full_text[:250] + ('...' if len(full_text) > 250 else '')
                            current_memory = f"HTTP {r.status_code}: {full_text}"
                            logs.append(f"HTTP {r.status_code}: {preview}")'''

if old_binary in server:
    server = server.replace(old_binary, new_binary, 1)
    sc += 1
    print("  OK: removed orphaned filepath/filebytes lines")
else:
    print("  SKIP: block pattern not matched (may already be clean)")

# ============================================================
# PATCH 2: Verify tool_zernio has platform + media support
# ============================================================
print("\n[2] Verifying tool_zernio platform+media...")

if 'media_urls' in server and 'valid_platforms' in server:
    print("  OK: tool_zernio already has platform+media support")
else:
    print("  WARN: tool_zernio may be missing platform/media - please check manually")

# ============================================================
# PATCH 3: Verify dispatcher passes media_urls
# ============================================================
print("\n[3] Verifying dispatcher passes media_urls...")

if 'tool_extra[\'media_urls\'] = node_data[\'media_urls\']' in server or \
   "tool_extra['media_urls'] = node_data['media_urls']" in server:
    print("  OK: dispatcher passes media_urls")
else:
    # Add it if missing
    old_disp = '''                    if node_data.get('platform'):
                        tool_extra['platform'] = node_data['platform']
                    result = handler(creds, msg, tool_extra)'''

    new_disp = '''                    if node_data.get('platform'):
                        tool_extra['platform'] = node_data['platform']
                    if node_data.get('media_urls'):
                        tool_extra['media_urls'] = node_data['media_urls']
                    if node_data.get('mediaUrls'):
                        tool_extra['media_urls'] = node_data['mediaUrls']
                    result = handler(creds, msg, tool_extra)'''

    if old_disp in server:
        server = server.replace(old_disp, new_disp, 1)
        sc += 1
        print("  OK: added media_urls passthrough to dispatcher")
    else:
        print("  SKIP: dispatcher pattern not matched")

# ============================================================
# Compile check
# ============================================================
print("\n[4] Compile check...")

try:
    compile(server, SERVER, 'exec')
    print("  [OK  ] server.py compiles")
except SyntaxError as e:
    print("  [FAIL] line {}: {}".format(e.lineno, e.msg))
    lines = server.splitlines()
    if e.lineno and e.lineno <= len(lines):
        print("  Offending line: {}".format(repr(lines[e.lineno - 1])))
    shutil.copy(SERVER + '.backup_v14', SERVER)
    print("  Restored from backup")
    sys.exit(1)

# Write
with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)
print("  OK: server.py written")

# ============================================================
# VERIFY
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fs = open(SERVER, 'r', encoding='utf-8').read()

checks = [
    ("no orphaned filepath line",  "current_memory = str(filepath.absolute())" not in fs),
    ("image/audio returns URL",    "image/audio ->" in fs),
    ("tool_zernio has platform",   "valid_platforms" in fs),
    ("tool_zernio has media",      "media_urls" in fs),
    ("dispatcher passes media",    "tool_extra['media_urls']" in fs or 'tool_extra["media_urls"]' in fs),
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
    print("  git commit -m 'Fix HTTP binary block + verify zernio media'")
    print("  git push origin main")
else:
    print("Review FAIL lines above. Backup: server.py.backup_v14")