import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found"); exit(1)

shutil.copy(SERVER, SERVER + '.backup_apis_final')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

new_block = '''        "### KNOWN-WORKING APIs (use these; do NOT invent others)\\n"
        "  Bitcoin price:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n"
        "                  returns {bitcoin:{usd:97500}}\\n"
        "                  use: data.bitcoin.usd\\n"
        "                  THIS IS THE ONLY reliable Bitcoin API from Vercel.\\n"
        "  Crypto prices:  https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd\\n"
        "                  returns {ethereum:{usd:3400}}\\n"
        "                  use: data.ethereum.usd\\n"
        "  Remote jobs:    https://remotive.com/api/remote-jobs\\n"
        "                  returns {jobs:[...]}\\n"
        "                  use: data.jobs\\n"
        "  Weather:        https://wttr.in/CITY?format=j1\\n"
        "                  use: data.current_condition[0].temp_C\\n"
        "  GitHub issues:  https://api.github.com/repos/OWNER/REPO/issues?state=open&per_page=5\\n"
        "                  returns an ARRAY\\n"
        "                  use: Array.isArray(data) ? data : []\\n"
        "  RSS example:    https://news.ycombinator.com/rss\\n"
        "                  returns XML - data will be NULL\\n"
        "                  use: input (raw string) with RegExp\\n"
        "  News:           https://newsapi.org/v2/top-headlines?country=us&apiKey=KEY\\n"
        "                  use: data.articles\\n\\n"

        "DEPRECATED URLs - NEVER emit these:\\n"
        "  - api.coindesk.com        (DNS dead since 2024)\\n"
        "  - api.binance.com         (HTTP 451 from Vercel US East)\\n"
        "  - remotive.io             (use remotive.com)\\n"
        "  - api.cryptocompare.com   (requires paid key)\\n\\n"

        "If the user asks for Bitcoin price, ALWAYS use CoinGecko:\\n"
        "  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\\n\\n"

        "### TOOLS\\n"'''

# Match from KNOWN-WORKING APIs through ### TOOLS
pattern = re.compile(
    r'\s*"### KNOWN-WORKING APIs[\s\S]*?"### TOOLS\\n"',
    re.DOTALL
)

if pattern.search(code):
    code = pattern.sub(new_block, code, count=1)
    print("[1] Replaced entire API block with ASCII version")
else:
    print("[1] FAIL — could not match block")
    print("    Search server.py for: ### KNOWN-WORKING APIs")
    exit(1)

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("Compiles OK")
except SyntaxError as e:
    shutil.copy(SERVER + '.backup_apis_final', SERVER)
    print(f"Syntax error line {e.lineno}: {e.msg} — restored")
    exit(1)

# Verify no Binance remains in the API section
final = open(SERVER, 'r', encoding='utf-8').read()
api_start = final.find('### KNOWN-WORKING APIs')
api_end = final.find('### TOOLS', api_start)
api_section = final[api_start:api_end]

checks = [
    ("CoinGecko primary",    'api.coingecko.com/api/v3/simple/price?ids=bitcoin' in api_section),
    ("Binance deprecated",   'api.binance.com         (HTTP 451' in api_section),
    ("No '→' arrows",        '→' not in api_section),
    ("No emoji",             not any(ord(c) > 127 for c in api_section)),
    ("Bitcoin-only rule",    'ALWAYS use CoinGecko' in api_section),
    ("### TOOLS preserved",  '### TOOLS' in final),
]
print("\nVERIFICATION:")
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

if all_ok:
    print("\nPATCH COMPLETE")
    print("Next:")
    print("  git add server.py")
    print("  git commit -m 'Final API prompt: CoinGecko only, Binance deprecated, ASCII'")
    print("  git push origin main")