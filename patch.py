import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found:", SERVER); exit(1)

shutil.copy(SERVER, SERVER + '.backup_neon')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

print("File:", len(code), "chars\n")
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Imports — add psycopg + guard for local dev
# ═══════════════════════════════════════════════════════════════
print("[1] Adding psycopg import...")

if 'import psycopg' not in code:
    # Insert after "import requests"
    anchor = "import requests\n"
    inject = (
        "import requests\n"
        "try:\n"
        "    import psycopg\n"
        "    from psycopg.rows import dict_row\n"
        "    from psycopg_pool import ConnectionPool\n"
        "    _HAS_PSYCOPG = True\n"
        "except ImportError:\n"
        "    psycopg = None\n"
        "    dict_row = None\n"
        "    ConnectionPool = None\n"
        "    _HAS_PSYCOPG = False\n"
    )
    if anchor in code:
        code = code.replace(anchor, inject, 1)
        changes += 1
        print("  OK - psycopg import added")

# ═══════════════════════════════════════════════════════════════
# 2. Replace storage path block with DB-aware version
# ═══════════════════════════════════════════════════════════════
print("\n[2] Replacing storage paths...")

old_block = re.compile(
    r"DATA_DIR\s*=\s*Path\(\"workflows\"\)[^\n]*\n"
    r"LOG_DIR\s*=\s*Path\(\"execution_logs\"\)[^\n]*\n"
    r"CREDS_DIR\s*=\s*Path\(\"credentials\"\)[^\n]*\n"
    r"(?:\s*\n)?"
    r"#\s*=+\s*\n"
    r"#\s*AI MEMORY[^\n]*\n"
    r"#\s*=+\s*\n"
    r"MEMORY_DIR\s*=\s*Path\(\"memory\"\)[^\n]*\n"
    r"SESSIONS_DIR\s*=\s*MEMORY_DIR\s*/\s*\"sessions\"[^\n]*\n"
    r"FACTS_FILE\s*=\s*MEMORY_DIR\s*/\s*\"facts\.json\"\n"
    r"SUMMARY_FILE\s*=\s*MEMORY_DIR\s*/\s*\"summary\.json\"",
    re.DOTALL
)

new_block = '''# ============================================================
# STORAGE — Postgres (Neon) when DATABASE_URL is set, else local files
# ============================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_DB = bool(DATABASE_URL) and _HAS_PSYCOPG

_pool = None
if USE_DB:
    try:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=4,
            timeout=10,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        print("[db] Neon Postgres pool ready")
    except Exception as _e:
        print(f"[db] Pool init failed: {_e} — falling back to local files")
        _pool = None
        USE_DB = False

# Legacy filesystem paths (only used when USE_DB is False, e.g. local dev)
_IS_SERVERLESS = bool(
    os.environ.get("VERCEL")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    or os.environ.get("AWS_EXECUTION_ENV")
)

if _IS_SERVERLESS and not USE_DB:
    _BASE = Path("/tmp") / "workflow-pro"
    _BASE.mkdir(parents=True, exist_ok=True)
else:
    _BASE = Path(".")

DATA_DIR     = _BASE / "workflows"
LOG_DIR      = _BASE / "execution_logs"
CREDS_DIR    = _BASE / "credentials"
MEMORY_DIR   = _BASE / "memory"
SESSIONS_DIR = MEMORY_DIR / "sessions"
FACTS_FILE   = MEMORY_DIR / "facts.json"
SUMMARY_FILE = MEMORY_DIR / "summary.json"

if not USE_DB:
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    CREDS_DIR.mkdir(exist_ok=True)
    MEMORY_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

print(f"[storage] mode={'postgres' if USE_DB else 'filesystem'} base={_BASE.resolve()}")


# ============================================================
# Schema bootstrap — safe to run every boot
# ============================================================
def _db_init_schema():
    if not USE_DB or _pool is None:
        return
    try:
        with _pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    name        TEXT PRIMARY KEY,
                    payload     JSONB NOT NULL,
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS credentials (
                    service     TEXT PRIMARY KEY,
                    payload     JSONB NOT NULL,
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id          BIGSERIAL PRIMARY KEY,
                    workflow    TEXT NOT NULL,
                    source      TEXT NOT NULL,
                    status      TEXT,
                    result      JSONB,
                    logs        JSONB,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_exec_wf_created
                    ON execution_logs(workflow, created_at DESC);
                CREATE TABLE IF NOT EXISTS memory_messages (
                    id          BIGSERIAL PRIMARY KEY,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    role        TEXT NOT NULL,
                    text        TEXT NOT NULL,
                    session_id  TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_mem_created
                    ON memory_messages(created_at DESC);
                CREATE TABLE IF NOT EXISTS memory_facts (
                    key         TEXT PRIMARY KEY,
                    value       JSONB,
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                );
            """)
        print("[db] schema ensured")
    except Exception as e:
        print(f"[db] schema init failed: {e}")

_db_init_schema()


def _db_exec(query, params=None):
    """Execute a write query. Returns True on success."""
    if not USE_DB or _pool is None:
        return False
    try:
        with _pool.connection() as conn, conn.cursor() as cur:
            cur.execute(query, params or ())
        return True
    except Exception as e:
        print(f"[db] exec failed: {e}")
        return False


def _db_one(query, params=None):
    """Fetch one row as dict, or None."""
    if not USE_DB or _pool is None:
        return None
    try:
        with _pool.connection() as conn, conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchone()
    except Exception as e:
        print(f"[db] query failed: {e}")
        return None


def _db_all(query, params=None):
    """Fetch all rows as list of dicts."""
    if not USE_DB or _pool is None:
        return []
    try:
        with _pool.connection() as conn, conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall() or []
    except Exception as e:
        print(f"[db] query failed: {e}")
        return []

'''

if old_block.search(code):
    code = old_block.sub(new_block, code, count=1)
    changes += 1
    print("  OK - storage block replaced")
else:
    print("  FAIL - storage block not matched (manual edit needed)")

# ═══════════════════════════════════════════════════════════════
# 3. Replace save/load/list workflow
# ═══════════════════════════════════════════════════════════════
print("\n[3] Replacing workflow storage functions...")

old_wf = '''# ---------- Workflow storage ----------
def save_workflow(name, wf):
    (DATA_DIR / f"{name}.json").write_text(json.dumps(wf, indent=2), encoding='utf-8')
def load_workflow(name):
    p = DATA_DIR / f"{name}.json"
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
def list_workflows():
    return sorted([p.stem for p in DATA_DIR.glob("*.json")])'''

new_wf = '''# ---------- Workflow storage ----------
def save_workflow(name, wf):
    if USE_DB:
        _db_exec(
            """INSERT INTO workflows (name, payload, updated_at)
               VALUES (%s, %s::jsonb, NOW())
               ON CONFLICT (name) DO UPDATE SET
                 payload = EXCLUDED.payload,
                 updated_at = NOW()""",
            (name, json.dumps(wf))
        )
        return
    (DATA_DIR / f"{name}.json").write_text(json.dumps(wf, indent=2), encoding='utf-8')

def load_workflow(name):
    if USE_DB:
        row = _db_one("SELECT payload FROM workflows WHERE name = %s", (name,))
        return row["payload"] if row else None
    p = DATA_DIR / f"{name}.json"
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

def list_workflows():
    if USE_DB:
        rows = _db_all("SELECT name FROM workflows ORDER BY name")
        return [r["name"] for r in rows]
    return sorted([p.stem for p in DATA_DIR.glob("*.json")])

def delete_workflow(name):
    if USE_DB:
        _db_exec("DELETE FROM workflows WHERE name = %s", (name,))
        return
    p = DATA_DIR / f"{name}.json"
    if p.exists(): p.unlink()'''

if old_wf in code:
    code = code.replace(old_wf, new_wf, 1)
    changes += 1
    print("  OK - workflow funcs replaced")
else:
    print("  SKIP - workflow block not matched")

# ═══════════════════════════════════════════════════════════════
# 4. Replace execution log functions
# ═══════════════════════════════════════════════════════════════
print("\n[4] Replacing execution log functions...")

old_log = '''# ---------- Execution log ----------
def log_execution(wf_name, source, result):
    entry = {"id": uuid.uuid4().hex[:8], "timestamp": datetime.utcnow().isoformat()+"Z",
             "source": source, "status": result.get("status"),
             "result": result.get("data"), "logs": result.get("logs", [])}
    with (LOG_DIR / f"{wf_name}.jsonl").open("a", encoding='utf-8') as f:
        f.write(json.dumps(entry)+"\\n")
    return entry
def read_execution_log(wf_name, limit=50):
    p = LOG_DIR / f"{wf_name}.jsonl"
    if not p.exists(): return []
    lines = [l for l in p.read_text(encoding='utf-8').split("\\n") if l.strip()]
    return [json.loads(l) for l in lines[-limit:]][::-1]'''

new_log = '''# ---------- Execution log ----------
def log_execution(wf_name, source, result):
    entry = {"id": uuid.uuid4().hex[:8], "timestamp": datetime.utcnow().isoformat()+"Z",
             "source": source, "status": result.get("status"),
             "result": result.get("data"), "logs": result.get("logs", [])}
    if USE_DB:
        _db_exec(
            """INSERT INTO execution_logs (workflow, source, status, result, logs)
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)""",
            (wf_name, source, result.get("status"),
             json.dumps(result.get("data")) if result.get("data") is not None else None,
             json.dumps(result.get("logs", [])))
        )
        return entry
    with (LOG_DIR / f"{wf_name}.jsonl").open("a", encoding='utf-8') as f:
        f.write(json.dumps(entry)+"\\n")
    return entry

def read_execution_log(wf_name, limit=50):
    if USE_DB:
        rows = _db_all(
            """SELECT id, created_at AS timestamp, source, status, result, logs
               FROM execution_logs WHERE workflow = %s
               ORDER BY created_at DESC LIMIT %s""",
            (wf_name, limit)
        )
        for r in rows:
            ts = r.get("timestamp")
            r["timestamp"] = ts.isoformat() + "Z" if ts else None
            r["id"] = str(r["id"])[:8]
        return rows
    p = LOG_DIR / f"{wf_name}.jsonl"
    if not p.exists(): return []
    lines = [l for l in p.read_text(encoding='utf-8').split("\\n") if l.strip()]
    return [json.loads(l) for l in lines[-limit:]][::-1]'''

if old_log in code:
    code = code.replace(old_log, new_log, 1)
    changes += 1
    print("  OK - log funcs replaced")
else:
    print("  SKIP - log block not matched")

# ═══════════════════════════════════════════════════════════════
# 5. Replace credentials functions
# ═══════════════════════════════════════════════════════════════
print("\n[5] Replacing credentials funcs...")

old_creds = '''# ---------- Credentials ----------
def load_creds(service):
    p = CREDS_DIR / f"{service}.json"
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
def save_creds(service, creds):
    (CREDS_DIR / f"{service}.json").write_text(json.dumps(creds, indent=2), encoding='utf-8')'''

new_creds = '''# ---------- Credentials ----------
def load_creds(service):
    if USE_DB:
        row = _db_one("SELECT payload FROM credentials WHERE service = %s", (service,))
        return row["payload"] if row else None
    p = CREDS_DIR / f"{service}.json"
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

def save_creds(service, creds):
    if USE_DB:
        _db_exec(
            """INSERT INTO credentials (service, payload, updated_at)
               VALUES (%s, %s::jsonb, NOW())
               ON CONFLICT (service) DO UPDATE SET
                 payload = EXCLUDED.payload,
                 updated_at = NOW()""",
            (service, json.dumps(creds))
        )
        return
    (CREDS_DIR / f"{service}.json").write_text(json.dumps(creds, indent=2), encoding='utf-8')

def list_configured_creds():
    if USE_DB:
        rows = _db_all("SELECT service FROM credentials ORDER BY service")
        return [r["service"] for r in rows]
    return [p.stem for p in CREDS_DIR.glob("*.json")]

def delete_creds(service):
    if USE_DB:
        _db_exec("DELETE FROM credentials WHERE service = %s", (service,))
        return
    p = CREDS_DIR / f"{service}.json"
    if p.exists(): p.unlink()'''

if old_creds in code:
    code = code.replace(old_creds, new_creds, 1)
    changes += 1
    print("  OK - creds funcs replaced")
else:
    print("  SKIP - creds block not matched")

# ═══════════════════════════════════════════════════════════════
# 6. Replace memory functions
# ═══════════════════════════════════════════════════════════════
print("\n[6] Replacing memory functions...")

# memory_save_message
old_mem_save = '''def memory_save_message(role, text, session_id=None):
    """Append one message to today's session log."""
    from datetime import datetime as _dt
    today = _dt.utcnow().strftime("%Y-%m-%d")
    path = SESSIONS_DIR / f"{today}.jsonl"
    entry = {
        "ts": _dt.utcnow().isoformat() + "Z",
        "role": role,
        "text": text[:5000],  # cap at 5k per message
        "session_id": session_id or "default"
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\\n")
    return entry'''

new_mem_save = '''def memory_save_message(role, text, session_id=None):
    """Append one message to memory."""
    from datetime import datetime as _dt
    text = (text or "")[:5000]
    if USE_DB:
        _db_exec(
            """INSERT INTO memory_messages (role, text, session_id)
               VALUES (%s, %s, %s)""",
            (role, text, session_id or "default")
        )
        return {"ts": _dt.utcnow().isoformat() + "Z", "role": role,
                "text": text, "session_id": session_id or "default"}
    today = _dt.utcnow().strftime("%Y-%m-%d")
    path = SESSIONS_DIR / f"{today}.jsonl"
    entry = {"ts": _dt.utcnow().isoformat() + "Z", "role": role,
             "text": text, "session_id": session_id or "default"}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\\n")
    return entry'''

if old_mem_save in code:
    code = code.replace(old_mem_save, new_mem_save, 1)
    changes += 1
    print("  OK - memory_save_message replaced")
else:
    print("  SKIP - memory_save not matched")

# memory_recent
old_mem_recent = '''def memory_recent(hours=24, limit=30):
    """Load messages from the last N hours."""
    from datetime import datetime as _dt, timedelta
    cutoff = _dt.utcnow() - timedelta(hours=hours)
    messages = []
    for p in sorted(SESSIONS_DIR.glob("*.jsonl"), reverse=True):
        try:
            for line in p.read_text(encoding="utf-8").splitlines()[-200:]:
                if not line.strip(): continue
                try:
                    entry = json.loads(line)
                    ts = _dt.fromisoformat(entry["ts"].replace("Z", ""))
                    if ts >= cutoff:
                        messages.append(entry)
                except Exception:
                    continue
        except Exception:
            continue
    messages.sort(key=lambda m: m["ts"])
    return messages[-limit:]'''

new_mem_recent = '''def memory_recent(hours=24, limit=30):
    """Load messages from the last N hours."""
    from datetime import datetime as _dt, timedelta
    if USE_DB:
        rows = _db_all(
            """SELECT created_at AS ts, role, text, session_id
               FROM memory_messages
               WHERE created_at > NOW() - INTERVAL '%s hours'
               ORDER BY created_at ASC LIMIT %s""",
            (int(hours), int(limit))
        )
        for r in rows:
            if r.get("ts"): r["ts"] = r["ts"].isoformat() + "Z"
        return rows
    cutoff = _dt.utcnow() - timedelta(hours=hours)
    messages = []
    for p in sorted(SESSIONS_DIR.glob("*.jsonl"), reverse=True):
        try:
            for line in p.read_text(encoding="utf-8").splitlines()[-200:]:
                if not line.strip(): continue
                try:
                    entry = json.loads(line)
                    ts = _dt.fromisoformat(entry["ts"].replace("Z", ""))
                    if ts >= cutoff:
                        messages.append(entry)
                except Exception:
                    continue
        except Exception:
            continue
    messages.sort(key=lambda m: m["ts"])
    return messages[-limit:]'''

if old_mem_recent in code:
    code = code.replace(old_mem_recent, new_mem_recent, 1)
    changes += 1
    print("  OK - memory_recent replaced")
else:
    print("  SKIP - memory_recent not matched")

# memory_load_facts / memory_save_fact
old_facts_load = '''def memory_load_facts():
    """Load long-term facts (name, preferences, etc)."""
    if FACTS_FILE.exists():
        try:
            return json.loads(FACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"name": None, "preferences": [], "projects": []}'''

new_facts_load = '''def memory_load_facts():
    """Load long-term facts (name, preferences, etc)."""
    if USE_DB:
        rows = _db_all("SELECT key, value FROM memory_facts")
        facts = {r["key"]: r["value"] for r in rows}
        return {
            "name": facts.get("name"),
            "preferences": facts.get("preferences", []) if isinstance(facts.get("preferences"), list) else [],
            "projects": facts.get("projects", []) if isinstance(facts.get("projects"), list) else [],
        }
    if FACTS_FILE.exists():
        try:
            return json.loads(FACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"name": None, "preferences": [], "projects": []}'''

if old_facts_load in code:
    code = code.replace(old_facts_load, new_facts_load, 1)
    changes += 1
    print("  OK - memory_load_facts replaced")

old_facts_save = '''def memory_save_fact(key, value):
    """Save a fact to remember forever."""
    facts = memory_load_facts()
    facts[key] = value
    FACTS_FILE.write_text(json.dumps(facts, indent=2), encoding="utf-8")
    return facts'''

new_facts_save = '''def memory_save_fact(key, value):
    """Save a fact to remember forever."""
    if USE_DB:
        _db_exec(
            """INSERT INTO memory_facts (key, value, updated_at)
               VALUES (%s, %s::jsonb, NOW())
               ON CONFLICT (key) DO UPDATE SET
                 value = EXCLUDED.value, updated_at = NOW()""",
            (key, json.dumps(value))
        )
        return memory_load_facts()
    facts = memory_load_facts()
    facts[key] = value
    FACTS_FILE.write_text(json.dumps(facts, indent=2), encoding="utf-8")
    return facts'''

if old_facts_save in code:
    code = code.replace(old_facts_save, new_facts_save, 1)
    changes += 1
    print("  OK - memory_save_fact replaced")

# ═══════════════════════════════════════════════════════════════
# 7. Update route that lists credentials
# ═══════════════════════════════════════════════════════════════
print("\n[7] Updating /credentials listing route...")

old_list_creds = '''@app.route('/credentials', methods=['GET'])
def list_creds():
    return jsonify({"configured": [p.stem for p in CREDS_DIR.glob("*.json")]})'''

new_list_creds = '''@app.route('/credentials', methods=['GET'])
def list_creds():
    return jsonify({"configured": list_configured_creds()})'''

if old_list_creds in code:
    code = code.replace(old_list_creds, new_list_creds, 1)
    changes += 1
    print("  OK - list_creds updated")

# Update DELETE handler to use delete_creds
old_creds_delete = '''    if request.method == 'PUT':
        save_creds(service, request.json or {})
        return jsonify({"status":"saved","service":service})
    p = CREDS_DIR / f"{service}.json"
    if p.exists(): p.unlink()
    return jsonify({"status":"deleted"})'''

new_creds_delete = '''    if request.method == 'PUT':
        save_creds(service, request.json or {})
        return jsonify({"status":"saved","service":service})
    delete_creds(service)
    return jsonify({"status":"deleted"})'''

if old_creds_delete in code:
    code = code.replace(old_creds_delete, new_creds_delete, 1)
    changes += 1
    print("  OK - creds delete updated")

# ═══════════════════════════════════════════════════════════════
# 8. Update workflow DELETE route
# ═══════════════════════════════════════════════════════════════
print("\n[8] Updating workflow DELETE...")

old_wf_delete = '''    p = DATA_DIR / f"{name}.json"
    if p.exists(): p.unlink()
    return jsonify({"status":"deleted"})'''

new_wf_delete = '''    delete_workflow(name)
    return jsonify({"status":"deleted"})'''

if old_wf_delete in code:
    code = code.replace(old_wf_delete, new_wf_delete, 1)
    changes += 1
    print("  OK - workflow delete updated")

# ═══════════════════════════════════════════════════════════════
# 9. Fix PUBLIC_DIR + static routes
# ═══════════════════════════════════════════════════════════════
print("\n[9] Fixing public dir for serverless...")

if 'PUBLIC_DIR = Path(__file__).parent' not in code:
    # Insert after "app = Flask(__name__)"
    anchor = "app = Flask(__name__)\n"
    inject = 'app = Flask(__name__)\nPUBLIC_DIR = Path(__file__).parent / "public"\n'
    if anchor in code:
        code = code.replace(anchor, inject, 1)
        changes += 1
        print("  OK - PUBLIC_DIR defined")

old_index = '''@app.route('/')
def index(): return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path): return send_from_directory('public', path)'''

new_index = '''@app.route('/')
def index():
    return send_from_directory(str(PUBLIC_DIR), 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(str(PUBLIC_DIR), path)'''

if old_index in code:
    code = code.replace(old_index, new_index, 1)
    changes += 1
    print("  OK - static routes updated")

# ═══════════════════════════════════════════════════════════════
# 10. Guard app.run() inside __main__
# ═══════════════════════════════════════════════════════════════
print("\n[10] Guarding app.run()...")

old_run = "app.run(host='0.0.0.0', port=10000, debug=False, threaded=True)"
if old_run in code:
    # Check if it's already indented (inside if block)
    lines = code.split('\n')
    for i, line in enumerate(lines):
        if line.strip() == old_run:
            if not line.startswith('    '):
                # Not indented — indent it
                lines[i] = '    ' + old_run
                code = '\n'.join(lines)
                changes += 1
                print("  OK - app.run() indented inside __main__")
            else:
                print("  OK - app.run() already guarded")
            break

# ═══════════════════════════════════════════════════════════════
# 11. Update /ai-memory/stats to use DB when enabled
# ═══════════════════════════════════════════════════════════════
print("\n[11] Updating /ai-memory/stats...")

old_stats = '''@app.route('/ai-memory/stats', methods=['GET'])
def ai_memory_stats():
    total = 0
    for p in SESSIONS_DIR.glob("*.jsonl"):
        total += len(p.read_text(encoding="utf-8").splitlines())
    return jsonify({
        "total_messages": total,
        "sessions": len(list(SESSIONS_DIR.glob("*.jsonl"))),
        "facts": memory_load_facts(),
        "memory_dir": str(MEMORY_DIR.absolute())
    })'''

new_stats = '''@app.route('/ai-memory/stats', methods=['GET'])
def ai_memory_stats():
    if USE_DB:
        row = _db_one("SELECT COUNT(*) AS n FROM memory_messages") or {}
        total = row.get("n", 0)
        sessions = _db_one("SELECT COUNT(DISTINCT session_id) AS n FROM memory_messages") or {}
        return jsonify({
            "total_messages": total,
            "sessions": sessions.get("n", 0),
            "facts": memory_load_facts(),
            "backend": "postgres"
        })
    total = 0
    for p in SESSIONS_DIR.glob("*.jsonl"):
        total += len(p.read_text(encoding="utf-8").splitlines())
    return jsonify({
        "total_messages": total,
        "sessions": len(list(SESSIONS_DIR.glob("*.jsonl"))),
        "facts": memory_load_facts(),
        "backend": "filesystem",
        "memory_dir": str(MEMORY_DIR.absolute())
    })'''

if old_stats in code:
    code = code.replace(old_stats, new_stats, 1)
    changes += 1
    print("  OK - stats route updated")

# ═══════════════════════════════════════════════════════════════
# 12. Update /ai-memory/clear
# ═══════════════════════════════════════════════════════════════
print("\n[12] Updating /ai-memory/clear...")

old_clear = '''@app.route('/ai-memory/clear', methods=['POST'])
def ai_memory_clear():
    days = int(request.json.get('days', 0) if request.json else 0)
    if days == 0:
        # Clear all
        for p in SESSIONS_DIR.glob("*.jsonl"):
            p.unlink()
        if FACTS_FILE.exists(): FACTS_FILE.unlink()
        return jsonify({"ok": True, "message": "All memory cleared"})
    else:
        from datetime import datetime as _dt, timedelta
        cutoff = _dt.utcnow() - timedelta(days=days)
        removed = 0
        for p in SESSIONS_DIR.glob("*.jsonl"):
            if p.stat().st_mtime < cutoff.timestamp():
                p.unlink()
                removed += 1
        return jsonify({"ok": True, "removed_files": removed})'''

new_clear = '''@app.route('/ai-memory/clear', methods=['POST'])
def ai_memory_clear():
    days = int(request.json.get('days', 0) if request.json else 0)
    if USE_DB:
        if days == 0:
            _db_exec("DELETE FROM memory_messages")
            _db_exec("DELETE FROM memory_facts")
            return jsonify({"ok": True, "message": "All memory cleared"})
        _db_exec("DELETE FROM memory_messages WHERE created_at < NOW() - INTERVAL '%s days'" % int(days))
        return jsonify({"ok": True, "message": f"Memory older than {days} days cleared"})
    if days == 0:
        for p in SESSIONS_DIR.glob("*.jsonl"):
            p.unlink()
        if FACTS_FILE.exists(): FACTS_FILE.unlink()
        return jsonify({"ok": True, "message": "All memory cleared"})
    from datetime import datetime as _dt, timedelta
    cutoff = _dt.utcnow() - timedelta(days=days)
    removed = 0
    for p in SESSIONS_DIR.glob("*.jsonl"):
        if p.stat().st_mtime < cutoff.timestamp():
            p.unlink()
            removed += 1
    return jsonify({"ok": True, "removed_files": removed})'''

if old_clear in code:
    code = code.replace(old_clear, new_clear, 1)
    changes += 1
    print("  OK - clear route updated")

# ═══════════════════════════════════════════════════════════════
# Write + verify
# ═══════════════════════════════════════════════════════════════
with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

print("\n" + "=" * 55)
print("Wrote", len(code), "chars —", changes, "patch(es) applied")
print("=" * 55)

print("\nVerifying syntax...")
try:
    with open(SERVER, 'r', encoding='utf-8') as f:
        compile(f.read(), SERVER, 'exec')
    print("OK — compiles clean")
except SyntaxError as e:
    print(f"SYNTAX ERROR line {e.lineno}: {e.msg}")
    if e.text:
        print(f"   {e.text[:120]}")
    shutil.copy(SERVER + '.backup_neon', SERVER)
    print("Restored from backup")
    exit(1)

# Verify
with open(SERVER, 'r', encoding='utf-8') as f:
    final = f.read()

print("\nVERIFICATION:")
checks = [
    ("psycopg import",          "import psycopg" in final),
    ("DATABASE_URL variable",   "DATABASE_URL = os.environ" in final),
    ("USE_DB flag",             "USE_DB = bool(DATABASE_URL)" in final),
    ("Connection pool",         "_pool = ConnectionPool" in final),
    ("Schema init",             "_db_init_schema()" in final),
    ("save_workflow DB path",   "INSERT INTO workflows" in final),
    ("load_workflow DB path",   "SELECT payload FROM workflows" in final),
    ("save_creds DB path",      "INSERT INTO credentials" in final),
    ("memory_save_message DB",  "INSERT INTO memory_messages" in final),
    ("memory_recent DB",        "SELECT created_at AS ts" in final),
    ("delete_workflow helper",  "def delete_workflow" in final),
    ("list_configured_creds",   "def list_configured_creds" in final),
    ("PUBLIC_DIR from __file__","PUBLIC_DIR = Path(__file__).parent" in final),
    ("app.run indented",
        any(line.startswith('    ') and 'app.run(host' in line
            for line in final.split('\n'))),
    ("No import-time mkdir crash",
        "_IS_SERVERLESS and not USE_DB" in final),
]
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

print()
if all_ok and changes > 0:
    print("PATCH COMPLETE")
elif changes == 0:
    print("NOTHING CHANGED — file may already be patched")
else:
    print("PARTIAL — review FAIL lines above")

print()
print("NEXT STEPS:")
print()
print("1. Add DATABASE_URL to .env and Vercel env vars")
print("2. Add psycopg[binary] to requirements.txt")
print("3. Test locally: python server.py")
print("   Should print: [storage] mode=postgres")
print("4. Commit and push:")
print("   git add -A")
print("   git commit -m 'Neon Postgres storage'")
print("   git push")