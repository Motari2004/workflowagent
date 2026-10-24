# -*- coding: utf-8 -*-
import os, shutil, sys, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'
if not os.path.exists(SERVER):
    print("FAIL: missing server.py"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v15')
print("Backed up")

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# Add diagnostic print at the start of tool_zernio after msg check
# Find: "text = msg.strip()" inside tool_zernio
old = '''    if platform == "instagram" and not media_urls:
        return "[ERROR] Zernio: Instagram requires at least one image or video URL (media_urls)"

    text = msg.strip()'''

new = '''    # ===== DIAGNOSTIC =====
    print("[zernio-diag] platform=" + str(platform))
    print("[zernio-diag] media_urls RAW = " + repr(media_urls))
    print("[zernio-diag] extra keys = " + str(list((extra or {}).keys())))
    print("[zernio-diag] creds keys = " + str(list((creds or {}).keys())))
    # ======================

    if platform == "instagram" and not media_urls:
        return "[ERROR] Zernio: Instagram requires at least one image or video URL (media_urls)"

    text = msg.strip()'''

if old in server:
    server = server.replace(old, new, 1)
    print("OK: diagnostic added to tool_zernio")
elif '[zernio-diag]' in server:
    print("SKIP: diagnostic already present")
else:
    print("FAIL: could not find the return line in tool_zernio")
    print("Trying alternate pattern...")
    # Alternate: any media_urls validation
    alt = re.search(r'(if platform == "instagram" and not media_urls:\s*\n\s*return.*?\n)', server)
    if alt:
        new_alt = new
        server = server.replace(alt.group(0), new_alt, 1)
        print("OK: diagnostic added (alternate)")
    else:
        print("FAIL: giving up")
        shutil.copy(SERVER + '.backup_v15', SERVER)
        sys.exit(1)

# Also add dispatcher diagnostic
old_disp = '''                    msg = raw_msg or current_memory'''
new_disp = '''                    msg = raw_msg or current_memory
                    # ===== DIAGNOSTIC =====
                    print("[dispatcher-diag] service=" + str(service))
                    print("[dispatcher-diag] node_data keys = " + str(list(node_data.keys())))
                    print("[dispatcher-diag] node_data.media_urls = " + repr(node_data.get('media_urls')))
                    print("[dispatcher-diag] node_data.mediaUrls = " + repr(node_data.get('mediaUrls')))
                    # ======================'''

if '[dispatcher-diag]' not in server:
    if old_disp in server:
        server = server.replace(old_disp, new_disp, 1)
        print("OK: dispatcher diagnostic added")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("OK: server.py compiles")
except SyntaxError as e:
    print("FAIL: line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_v15', SERVER)
    sys.exit(1)

print("\nNext:")
print("  1. taskkill /F /IM python.exe  (if local)")
print("  2. python server.py")
print("  3. Execute the workflow again")
print("  4. Read the terminal output for [dispatcher-diag] and [zernio-diag] lines")
print("  5. Paste those lines back here")