import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_nobinance')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

# Remove Binance, make CoinGecko primary
old = '''        "### KNOWN-WORKING APIs (use these; do NOT invent others)\\n"
        "  Bitcoin price:  https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT\\n"
        "                  returns {\\\"symbol\\\":\\\"BTCUSDT\\\",\\\"price\\\":\\\"97500.00\\\"} - use parseFloat(data.price)\\n"
        "  Crypto prices:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n"
        "                  returns {\\\"bitcoin\\\":{\\\"usd\\\":97500}} - use data.bitcoin.usd\\n"'''

new = '''        "### KNOWN-WORKING APIs (use these; do NOT invent others)\\n"
        "  Bitcoin price:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n"
        "                  returns {\\\"bitcoin\\\":{\\\"usd\\\":97500}} - use data.bitcoin.usd\\n"
        "                  THIS IS THE ONLY RELIABLE BITCOIN API - use it always.\\n"'''

if old in code:
    code = code.replace(old, new, 1)
    print("[1] Removed Binance, made CoinGecko primary")
else:
    # Try regex to catch variations
    pattern = re.compile(
        r'"[^"]*Bitcoin price:[^"]*binance[^"]*"\s*\n\s*"[^"]*returns[^"]*BTCUSDT[^"]*"\s*\n\s*"[^"]*Crypto prices:[^"]*coingecko[^"]*"\s*\n\s*"[^"]*returns[^"]*bitcoin[^"]*"',
        re.DOTALL
    )
    if pattern.search(code):
        code = pattern.sub(
            '"  Bitcoin price:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n"\n'
            '        "                  returns {bitcoin:{usd:97500}} - use data.bitcoin.usd\\n"\n'
            '        "                  THIS IS THE ONLY RELIABLE BITCOIN API - use it always.\\n"',
            code, count=1
        )
        print("[1] Removed Binance via regex")
    else:
        print("[1] FAIL - could not match Binance block")
        print("    Search server.py for: api.binance.com")
        exit(1)

# Add Binance to deprecated section
old_dep = '''        "DEPRECATED URLs - NEVER emit these, they are dead:\\n"
        "  - api.coindesk.com        (DNS no longer resolves since late 2024)\\n"'''

new_dep = '''        "DEPRECATED URLs - NEVER emit these:\\n"
        "  - api.coindesk.com        (DNS no longer resolves since late 2024)\\n"
        "  - api.binance.com         (returns HTTP 451 from Vercel US East region)\\n"'''

if old_dep in code:
    code = code.replace(old_dep, new_dep, 1)
    print("[2] Added Binance to deprecated list")
else:
    print("[2] SKIP - deprecation section not matched")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\nCompiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_nobinance', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

print("\nPATCH COMPLETE")
print()
print("Next:")
print("  git add server.py")
print("  git commit -m 'Remove Binance (HTTP 451 from Vercel), CoinGecko only'")
print("  git push origin main")