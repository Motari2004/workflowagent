import os, shutil

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'
if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_knownapis')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

# Insert known APIs + deprecation warnings before "### TOOLS"
marker = '        "### TOOLS\\n"'

injection = '''        "### KNOWN-WORKING APIs (use these, not deprecated ones)\\n"
        "  Bitcoin price:  https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT\\n"
        "                  → returns {\\\"symbol\\\":\\\"BTCUSDT\\\",\\\"price\\\":\\\"97500.00\\\"}\\n"
        "                  → in JS: parseFloat(data.price)\\n"
        "  Crypto prices:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n"
        "                  → returns {\\\"bitcoin\\\":{\\\"usd\\\":97500}}\\n"
        "                  → in JS: data.bitcoin.usd\\n"
        "  Remote jobs:    https://remotive.com/api/remote-jobs\\n"
        "                  → returns {\\\"jobs\\\":[...]}\\n"
        "                  → in JS: data.jobs\\n"
        "  Weather:        https://wttr.in/CITY?format=j1\\n"
        "                  → in JS: data.current_condition[0].temp_C\\n"
        "  GitHub issues:  https://api.github.com/repos/OWNER/REPO/issues?state=open&per_page=5\\n"
        "                  → returns an ARRAY → in JS: Array.isArray(data) ? data : []\\n"
        "  RSS example:    https://news.ycombinator.com/rss\\n"
        "                  → returns XML → data will be NULL, use input with RegExp\\n\\n"

        "DEPRECATED — do NOT use these under any circumstances:\\n"
        "  ❌ api.coindesk.com           (shut down late 2024 — DNS no longer resolves)\\n"
        "  ❌ remotive.io                (migrated to remotive.com in 2022)\\n"
        "  ❌ api.cryptocompare.com      (requires paid key now)\\n"
        "  ❌ any URL containing 'coindesk' or 'cryptocompare' — DO NOT emit them\\n\\n"

        "### TOOLS\\n"'''

if 'KNOWN-WORKING APIs' not in code:
    if marker in code:
        code = code.replace(marker, injection, 1)
        print("[1] Inserted known-working APIs section")
    else:
        print("[1] FAIL — could not find ### TOOLS marker")
        exit(1)
else:
    print("[1] Already patched")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("Compiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_knownapis', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

print("\nPATCH COMPLETE")