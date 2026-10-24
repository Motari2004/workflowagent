# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')
HTML = os.path.join(PROJECT, 'public', 'index.html')

for f in [SERVER, HTML]:
    if not os.path.exists(f):
        print("FAIL: missing " + f); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v6')
shutil.copy(HTML, HTML + '.backup_v6')
print("Backed up")

sc = 0
hc = 0

# ============================================================
# SERVER.PY
# ============================================================
with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

# ---------- PATCH 1: merge backend memory into contents ----------
print("\n[1] Merging DB history into Gemini contents...")

old_contents = '''        # Build conversation
        contents = []
        for h in history[-10:]:
            role = h.get('role', 'user')
            text = h.get('text', '')
            if not text:
                continue
            contents.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": text}]
            })'''

new_contents = '''        # Build conversation - combine frontend history + DB memory
        contents = []
        seen_texts = set()

        def add_turn(role, text):
            text = (text or '').strip()
            if not text or text in seen_texts:
                return
            seen_texts.add(text)
            contents.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": text}]
            })

        # 1. DB memory (last 20 messages over 24h) - lowest priority, oldest first
        try:
            db_recent = memory_recent(hours=24, limit=20)
            for m in db_recent:
                add_turn(m.get('role', 'user'), m.get('text', ''))
            if db_recent:
                print(f"[ai-chat] Merged {len(db_recent)} DB memory turns")
        except Exception as e:
            print(f"[ai-chat] DB memory load failed: {e}")

        # 2. Frontend history (last 10 turns) - highest priority
        for h in history[-10:]:
            add_turn(h.get('role', 'user'), h.get('text', ''))'''

if old_contents in server:
    server = server.replace(old_contents, new_contents, 1)
    sc += 1
    print("  OK: DB memory merged into contents")
else:
    print("  SKIP: contents build pattern not matched")

# ---------- PATCH 2: ensure bot messages saved for every provider ----------
print("\n[2] Ensuring bot messages saved for all providers...")

# Gemini - already saves on success, but let's make it unconditional
old_gemini_save = '''            if reply:
                # Save AI reply to memory
                try:
                    memory_save_message("bot", reply.strip())
                except Exception:
                    pass
                return jsonify({"reply": reply.strip(), "model": model_key})'''

new_gemini_save = '''            if reply:
                try:
                    memory_save_message("bot", reply.strip())
                except Exception as e:
                    print(f"[ai-chat] Bot memory save failed: {e}")
                return jsonify({"reply": reply.strip(), "model": model_key})'''

if old_gemini_save in server:
    server = server.replace(old_gemini_save, new_gemini_save, 1)
    sc += 1
    print("  OK: Gemini bot message save confirmed")

# Ollama - has no bot save at all
old_ollama = '''            if reply:
                return jsonify({"reply": reply.strip(), "model": model_key})
            return jsonify({"error": f"Ollama failed for model {model_name}"}), 500'''

new_ollama = '''            if reply:
                try:
                    memory_save_message("bot", reply.strip())
                except Exception as e:
                    print(f"[ai-chat] Ollama bot memory save failed: {e}")
                return jsonify({"reply": reply.strip(), "model": model_key})
            return jsonify({"error": f"Ollama failed for model {model_name}"}), 500'''

if old_ollama in server:
    server = server.replace(old_ollama, new_ollama, 1)
    sc += 1
    print("  OK: Ollama bot message save added")
else:
    print("  SKIP: Ollama save pattern not matched")

# ---------- PATCH 3: add /ai-chat/history endpoint ----------
print("\n[3] Adding /ai-chat/history endpoint...")

if '@app.route(\'/ai-chat/history\'' not in server:
    # Insert before /ai-memory/facts
    anchor = "@app.route('/ai-memory/facts', methods=['GET', 'PUT'])"
    history_endpoint = '''@app.route('/ai-chat/history', methods=['GET'])
def ai_chat_history():
    """Return the last N conversation turns for the frontend to restore."""
    limit = int(request.args.get('limit', 20))
    try:
        msgs = memory_recent(hours=24 * 7, limit=limit)
        result = []
        for m in msgs:
            result.append({
                "role": m.get("role", "user"),
                "text": m.get("text", ""),
                "ts": m.get("ts", "")
            })
        return jsonify({"history": result, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e), "history": []}), 500


@app.route('/ai-memory/facts', methods=['GET', 'PUT'])'''

    if anchor in server:
        server = server.replace(anchor, history_endpoint, 1)
        sc += 1
        print("  OK: /ai-chat/history endpoint added")
    else:
        print("  FAIL: anchor not found for history endpoint")
else:
    print("  SKIP: /ai-chat/history already exists")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_v6', SERVER)
    print("  Restored from backup")
    sys.exit(1)

# ============================================================
# INDEX.HTML
# ============================================================
print("\n" + "=" * 55)
print("INDEX.HTML")
print("=" * 55)

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

# ---------- PATCH 4: load server history on page load ----------
print("\n[4] Loading server history on page load...")

# Find the init section where renderHistory() is called
old_init = '''    // ---- Initial render ----
    renderHistory();
    console.log('[ai] AI panel ready');'''

new_init = '''    // ---- Initial render ----
    renderHistory();

    // ---- Load persistent history from server ----
    async function loadServerHistory() {
        try {
            const res = await fetch('/ai-chat/history?limit=20');
            if (!res.ok) return;
            const data = await res.json();
            const serverMsgs = data.history || [];
            if (serverMsgs.length === 0) return;

            // If localStorage already has history, prefer whichever is longer
            if (history.length >= serverMsgs.length) {
                console.log('[ai] localStorage history is current:', history.length);
                return;
            }

            // Convert server format to frontend format
            const converted = serverMsgs.map(m => ({
                role: m.role === 'bot' ? 'bot' : 'user',
                text: m.text || ''
            }));

            history = converted;
            saveHistory();
            renderHistory();
            console.log('[ai] Loaded', converted.length, 'messages from server');
        } catch (e) {
            console.warn('[ai] Could not load server history:', e);
        }
    }
    loadServerHistory();

    console.log('[ai] AI panel ready');'''

if old_init in html:
    html = html.replace(old_init, new_init, 1)
    hc += 1
    print("  OK: server history loads on panel init")
else:
    print("  SKIP: initial render pattern not matched")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ============================================================
# VERIFY
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fs = open(SERVER, 'r', encoding='utf-8').read()
fh = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("server: DB memory merged",        "Merged" in fs and "DB memory" in fs),
    ("server: /ai-chat/history route",  "@app.route('/ai-chat/history'" in fs),
    ("server: Ollama bot save",         "Ollama bot memory save" in fs),
    ("server: dedup logic",             "seen_texts" in fs),
    ("html: server history loader",     "loadServerHistory" in fh),
    ("html: fetches /ai-chat/history",  "fetch('/ai-chat/history" in fh),
    ("html: prefers longer history",    "history.length >= serverMsgs.length" in fh),
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
    print("server: {} changes, html: {} changes".format(sc, hc))
    print()
    print("Next:")
    print("  git add server.py public/index.html")
    print("  git commit -m 'AI: persistent conversation memory across reloads'")
    print("  git push origin main")
else:
    print("Review FAIL lines above. Backups: *.backup_v6")