# -*- coding: utf-8 -*-
import os, shutil, sys, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'
if not os.path.exists(SERVER):
    print("FAIL: missing server.py"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v23')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# Find the current tool node shape section in the system prompt
# This is inside ai_chat() — the big system = data.get('system') or (...)
print("[1] Finding prompt section to replace...")

# Match the ZERNIO / social posting section
old_section = re.search(
    r'"### ZERNIO / INSTAGRAM / SOCIAL POSTING ###"[\s\S]*?(?="### NODE SCHEMAS ###")',
    server
)

if not old_section:
    print("FAIL: could not find ZERNIO section in prompt")
    print("Trying alternate pattern...")
    # Try broader match
    old_section = re.search(
        r'### ZERNIO.*?(?=### NODE SCHEMAS)',
        server,
        re.DOTALL
    )

if not old_section:
    print("FAIL: giving up on finding the section")
    sys.exit(1)

print("  Found section ({} chars)".format(len(old_section.group(0))))

# New section: much more prescriptive, with concrete few-shot examples
new_section = '''"### ZERNIO / INSTAGRAM / SOCIAL POSTING ###"
        "\\n\\n"
        "Zernio is a valid tool that posts to: instagram, facebook, tiktok, "
        "twitter, linkedin, threads, youtube, reddit, telegram, etc.\\n"
        "NEVER say you don't have Zernio - you do.\\n"
        "NEVER say you don't have Instagram - Zernio handles it.\\n\\n"

        "### THE EXACT TOOL NODE SHAPE YOU MUST PRODUCE ###\\n"
        "\\n"
        "When the platform is instagram, the tool/integration node is EXACTLY this:\\n"
        "\\n"
        "  {\\n"
        "    \\"type\\": \\"tool/integration\\",\\n"
        "    \\"data\\": {\\n"
        "      \\"service\\": \\"zernio\\",\\n"
        "      \\"platform\\": \\"instagram\\",\\n"
        "      \\"message\\": \\"\\",\\n"
        "      \\"media_urls\\": [\\"https://picsum.photos/id/237/1024/1024\\"]\\n"
        "    }\\n"
        "  }\\n"
        "\\n"
        "Copy this shape verbatim. Change only the media URL if needed.\\n\\n"

        "### WHY THESE EXACT VALUES ###\\n"
        "\\n"
        "- \\"message\\": \\"\\" — empty string. The tool node AUTO-INHERITS the previous "
        "node's text output as the caption. Do not put a variable here. Do not put "
        "a template. Do not put text. Just empty string.\\n"
        "- \\"media_urls\\": [\\"...\\"] — array with one literal https URL. Instagram "
        "requires an image. Do not put ${...} or {{...}} in this field. Do not "
        "reference previous node output. The URL is a STATIC literal string.\\n"
        "- \\"platform\\": \\"instagram\\" — plain string, lowercase.\\n"
        "- \\"service\\": \\"zernio\\" — plain string, lowercase.\\n\\n"

        "### WRONG OUTPUT — DO NOT PRODUCE THESE ###\\n"
        "\\n"
        "WRONG #1 (template in message):\\n"
        "  {\\"type\\": \\"tool/integration\\", \\"data\\": {\\"service\\": \\"zernio\\", \\"platform\\": \\"instagram\\", "
        "\\"message\\": \\"${input.quote}\\", \\"media_urls\\": [\\"https://...\\"]}}\\n"
        "  Why wrong: \\"${input.quote}\\" is a literal 15-character string. It is NOT "
        "interpolated. Zernio receives the literal text ${input.quote} as the caption.\\n\\n"

        "WRONG #2 (template in media_urls):\\n"
        "  {\\"type\\": \\"tool/integration\\", \\"data\\": {\\"service\\": \\"zernio\\", \\"platform\\": \\"instagram\\", "
        "\\"message\\": \\"\\", \\"media_urls\\": [\\"${input.image}\\"]}}\\n"
        "  Why wrong: Zernio receives the literal text \\"${input.image}\\" as the image "
        "URL. That is not a URL. Zernio returns 400 Invalid media URL.\\n\\n"

        "WRONG #3 (message has a variable):\\n"
        "  {\\"type\\": \\"tool/integration\\", \\"data\\": {\\"service\\": \\"zernio\\", \\"platform\\": \\"instagram\\", "
        "\\"message\\": \\"{{data.quote}}\\", \\"media_urls\\": [\\"https://...\\"]}}\\n"
        "  Why wrong: no template engine exists. The literal text {{data.quote}} is "
        "sent to Zernio as the caption.\\n\\n"

        "WRONG #4 (media_urls is a string, not array):\\n"
        "  {\\"type\\": \\"tool/integration\\", \\"data\\": {\\"service\\": \\"zernio\\", \\"platform\\": \\"instagram\\", "
        "\\"message\\": \\"\\", \\"media_urls\\": \\"https://picsum.photos/id/237/1024\\"}}\\n"
        "  Why wrong: media_urls MUST be an array of strings, not a single string.\\n\\n"

        "WRONG #5 (media_urls has embedded quotes):\\n"
        "  {\\"type\\": \\"tool/integration\\", \\"data\\": {\\"service\\": \\"zernio\\", \\"platform\\": \\"instagram\\", "
        "\\"message\\": \\"\\", \\"media_urls\\": [\\"[\\\\\\"https://picsum.photos/id/237/1024\\\\\\"]\\"]}}\\n"
        "  Why wrong: the media_urls element contains literal brackets and quotes. "
        "Zernio sees \\"[\\\\\\"https://...\\\\\\"]\\" as the URL, which is not a valid URL.\\n\\n"

        "### CORRECT EXAMPLE 1 (post a random quote) ###\\n"
        "\\n"
        "User: \\"post a random quote to instagram\\"\\n"
        "You output (inside a ```json block):\\n"
        "  [\\n"
        "    {\\"type\\": \\"trigger/webhook\\", \\"data\\": {}},\\n"
        "    {\\"type\\": \\"action/http\\", \\"data\\": {\\"url\\": \\"https://type.fit/api/quotes\\", \\"method\\": \\"GET\\"}},\\n"
        "    {\\"type\\": \\"logic/code\\", \\"data\\": {\\"lang\\": \\"javascript\\", \\"code\\": \\"if (!data || !Array.isArray(data)) { output('[ERROR] No quotes'); } else { const r = data[Math.floor(Math.random() * data.length)]; output(r.text + ' — ' + r.author + ' #inspiration'); }\\"}},\\n"
        "    {\\"type\\": \\"tool/integration\\", \\"data\\": {\\"service\\": \\"zernio\\", \\"platform\\": \\"instagram\\", \\"message\\": \\"\\", \\"media_urls\\": [\\"https://picsum.photos/id/237/1024/1024\\"]}}\\n"
        "  ]\\n\\n"
        "Notice in node 4:\\n"
        "  - \\"message\\": \\"\\" is truly empty — no variable, no template\\n"
        "  - \\"media_urls\\": [\\"https://picsum.photos/id/237/1024/1024\\"] is a literal array\\n"
        "  - The Code node's output (the quote text) automatically flows to the tool node as the caption\\n\\n"

        "### HOW THE RUNTIME WORKS (why templates do not exist) ###\\n"
        "\\n"
        "Each node in the workflow receives the previous node's output as a plain string. "
        "The tool node either: (a) uses its own \\"message\\" field if non-empty, OR "
        "(b) inherits the previous node's output if \\"message\\" is empty.\\n"
        "There is NO template engine. ${...} and {{...}} are not evaluated. "
        "They are passed as literal text to the tool. This breaks Zernio, which "
        "expects valid text and valid URLs.\\n\\n"

        "### THE RULE ###\\n"
        "\\n"
        "For EVERY tool/integration node you produce:\\n"
        "  - \\"message\\" is either \\"\\" (empty) or a plain literal string with no {} or $\\n"
        "  - \\"media_urls\\" is either omitted, or an array of literal https URLs\\n"
        "  - NEVER write ${input.x}, ${data.x}, {{input.x}}, {{data.x}} in any field\\n"
        "  - If you feel tempted to reference previous node output, use \\"message\\": \\"\\" "
        "and let it inherit automatically\\n\\n"

        '''

server = server[:old_section.start()] + new_section + server[old_section.end():]
print("  OK: ZERNIO section replaced with few-shot examples")

# Also update the FREE IMAGE SOURCES section (which mentions deprecated unsplash)
print("\n[2] Updating image sources section...")

old_img = re.search(
    r'"### FREE IMAGE SOURCES FOR INSTAGRAM ###"[\s\S]*?(?="### NODE SCHEMAS ###")',
    server
)

if old_img:
    new_img = '''"### IMAGE URLS ###"
        "\\n"
        "USE ONLY THIS URL for Instagram media_urls:\\n"
        "  https://picsum.photos/id/237/1024/1024\\n"
        "\\n"
        "Other working picsum IDs (replace 237):\\n"
        "  1011, 1015, 1016, 1018, 1025, 1039, 1040, 1043, 1044, 1050\\n"
        "\\n"
        "Format examples (all valid, all literal, no templates):\\n"
        "  [\\"https://picsum.photos/id/237/1024/1024\\"]\\n"
        "  [\\"https://picsum.photos/id/1011/1024/1024\\"]\\n"
        "\\n"
        "DO NOT use:\\n"
        "  https://source.unsplash.com/... (SHUT DOWN - returns HTML page)\\n"
        "  https://picsum.photos/1024/1024 (redirects - sometimes fails)\\n"
        "  https://placehold.it/... (404)\\n"
        "  ${input.image} or {{image_url}} (not a URL, will break)\\n\\n"

        '''
    server = server[:old_img.start()] + new_img + server[old_img.end():]
    print("  OK: image sources section updated")
else:
    print("  SKIP: image sources section not found")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_v23', SERVER)
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
    ("exact tool shape example",     "THE EXACT TOOL NODE SHAPE" in fs),
    ("wrong examples present",       "WRONG OUTPUT — DO NOT PRODUCE" in fs),
    ("correct example present",      "CORRECT EXAMPLE 1" in fs),
    ("runtime explanation",          "NO template engine" in fs or "There is NO template engine" in fs),
    ("message is truly empty note",  "truly empty — no variable" in fs),
    ("image ID 237 mentioned",       "picsum.photos/id/237" in fs),
    ("unsplash deprecated warned",   "SHUT DOWN - returns HTML" in fs),
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
    print("\nNext:")
    print("  git add server.py")
    print("  git commit -m 'Prompt: concrete few-shot examples for tool node format'")
    print("  git push origin main")
    print()
    print("Then:")
    print("  taskkill /F /IM python.exe")
    print("  python server.py")
    print("  In browser: clear AI chat, then ask: 'post a random quote to instagram'")
else:
    print("Review FAIL lines. Backup: server.py.backup_v23")