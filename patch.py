import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_clean')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

# Find the whole block from "### KNOWN-WORKING APIs" to "### TOOLS"
# and replace with a clean ASCII version
pattern = re.compile(
    r'\s*"### KNOWN-WORKING APIs[\s\S]*?"### TOOLS\\n"',
    re.DOTALL
)

clean_block = '''        "### KNOWN-WORKING APIs (use these; do NOT invent others)\\n"
        "  Bitcoin price:  https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT\\n"
        "                  returns {\\\"symbol\\\":\\\"BTCUSDT\\\",\\\"price\\\":\\\"97500.00\\\"} - use parseFloat(data.price)\\n"
        "  Crypto prices:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n"
        "                  returns {\\\"bitcoin\\\":{\\\"usd\\\":97500}} - use data.bitcoin.usd\\n"
        "  Remote jobs:    https://remotive.com/api/remote-jobs\\n"
        "                  returns {\\\"jobs\\\":[...]} - use data.jobs\\n"
        "  Weather:        https://wttr.in/CITY?format=j1\\n"
        "                  use data.current_condition[0].temp_C\\n"
        "  GitHub issues:  https://api.github.com/repos/OWNER/REPO/issues?state=open&per_page=5\\n"
        "                  returns an ARRAY - use Array.isArray(data) ? data : []\\n"
        "  RSS example:    https://news.ycombinator.com/rss\\n"
        "                  returns XML - data will be NULL, use input with RegExp\\n\\n"

        "DEPRECATED URLs - NEVER emit these, they are dead:\\n"
        "  - api.coindesk.com        (DNS no longer resolves since late 2024)\\n"
        "  - remotive.io             (use remotive.com instead)\\n"
        "  - api.cryptocompare.com   (requires paid key, blocked)\\n\\n"

        "If the user asks for Bitcoin price, default to Binance:\\n"
        "  https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT\\n\\n"

        "### TOOLS\\n"'''

if pattern.search(code):
    code = pattern.sub(clean_block, code, count=1)
    print("[1] Replaced KNOWN-WORKING APIs block with clean ASCII version")
else:
    print("[1] FAIL — could not match KNOWN-WORKING APIs block")
    print("    Searching for markers...")
    if "### KNOWN-WORKING APIs" in code:
        print("    Found start marker — checking end marker...")
    if "### TOOLS" in code:
        print("    Found ### TOOLS")
    exit(1)

# Also clean up the "Response shape" arrow line in the research + delivery block
old_response = '''        "Response shape: {\\\"status\\\":\\\"success\\\", \\\"response\\\":\\\"<inner-json-string>\\\"}\\n"
        "  → The Code node's `data` variable is auto-flattened to the inner payload,\\n"
        "    so use `data.jobs`, `data.status`, NOT `data.response.jobs`.\\n\\n"'''

new_response = '''        "Response shape: {\\\"status\\\":\\\"success\\\", \\\"response\\\":\\\"<inner-json-string>\\\"}\\n"
        "  The Code node's `data` variable is auto-flattened to the inner payload,\\n"
        "  so use `data.jobs`, `data.status`, NOT `data.response.jobs`.\\n\\n"'''

if old_response in code:
    code = code.replace(old_response, new_response, 1)
    print("[2] Cleaned up the 'Response shape' arrow")
else:
    print("[2] SKIP — Response shape block not matched (may already be ASCII)")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

# Compile check
try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\nCompiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_clean', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

# Verify the API section is pure ASCII
with open(SERVER, 'r', encoding='utf-8') as f:
    final = f.read()

api_start = final.find('### KNOWN-WORKING APIs')
api_end = final.find('### TOOLS', api_start)
if api_start != -1 and api_end != -1:
    api_section = final[api_start:api_end]
    bad = [(i, c) for i, c in enumerate(api_section) if ord(c) > 127]
    if bad:
        print(f"\n[!] Non-ASCII found in API section at {len(bad)} positions:")
        for pos, ch in bad[:5]:
            context = api_section[max(0,pos-20):pos+20]
            print(f"    {repr(ch)} (U+{ord(ch):04X}): ...{context}...")
    else:
        print("\n[OK] API section is pure ASCII")
else:
    print("\n[!] Could not locate API section for verification")

print("\nPATCH COMPLETE")
print()
print("Next:")
print("  git add server.py")
print("  git commit -m 'Clean ASCII prompt for Gemini'")
print("  git push origin main")