import os, shutil, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("Not found:", HTML); exit(1)

shutil.copy(HTML, HTML + '.backup_urls')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("File:", len(html), "chars\n")

# Count how many localhost refs exist
before = html.count('http://localhost:10000')
print(f"Found {before} hardcoded localhost URLs\n")

# Replace localhost:10000 with relative paths
# Two passes to handle both `http://localhost:10000/` and `http://localhost:10000`
html = html.replace('http://localhost:10000/', '/')
html = html.replace('http://localhost:10000', '')

# Fix any accidental double slashes like `//run` (should be `/run`)
html = re.sub(r"'(?<!:)//([a-z])", r"'/\1", html)   # '//run' -> '/run'
html = re.sub(r'"(?<!:)//([a-z])', r'"/\1', html)   # "//run" -> "/run"

# Also replace template-literal forms
html = html.replace('`http://localhost:10000/', '`/')
html = html.replace('`http://localhost:10000', '`')

# Handle ws:// forms (there aren't any, but just in case)
html = html.replace("'ws://localhost:10000", "((location.protocol==='https:')?'wss://':'ws://') + location.host")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Wrote {len(html)} chars")

# Verification
with open(HTML, 'r', encoding='utf-8') as f:
    final = f.read()

after = final.count('localhost:10000')
print()
print("=" * 55)
print(f"Remaining localhost:10000 refs: {after}")
print("=" * 55)

# Show remaining if any
if after > 0:
    print("\nRemaining occurrences (context):")
    for m in re.finditer(r'.{0,40}localhost:10000.{0,40}', final):
        print(f"  ...{m.group(0)}...")

# Show sample of new fetch calls
print("\nSample of fetch calls now:")
for m in re.finditer(r"fetch\(['\"`]([^'\"`]+)", final):
    print(f"  {m.group(1)}")
    if m.start() > 8000:  # just show a few
        break