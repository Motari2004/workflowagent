import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found:", SERVER); exit(1)

shutil.copy(SERVER, SERVER + '.backup_db')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

print("File:", len(code), "chars\n")
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Replace the whole import + pool block with a robust version
#    (drops psycopg_pool requirement, uses direct connections)
# ═══════════════════════════════════════════════════════════════
print("[1] Replacing imports + DB init block...")

old_import_block = re.compile(
    r"try:\s*\n"
    r"\s*import psycopg\s*\n"
    r".*?"
    r"_HAS_PSYCOPG = False\s*\n"
    r"(?:[^\n]*\n)*?"
    r"_pool = None\s*\n"
    r".*?"
    r"USE_DB = False\s*\n",
    re.DOTALL
)

new_import_block = '''# ============================================================
# NEON POSTGRES — direct connections (no psycopg_pool dependency)
# ============================================================
try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError as _ie:
    psycopg = None
    dict_row = None
    _HAS_PSYCOPG = False
    print(f"[db] psycopg import failed: {_ie}")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

print(f"[db] DATABASE_URL present: {bool(DATABASE_URL)} (len={len(DATABASE_URL)})")
print(f"[db] psycopg available: {_HAS_PSYCOPG}")

USE_DB = bool(DATABASE_URL) and _HAS_PSYCOPG

# Quick connection test so boot logs are honest
if USE_DB:
    try:
        _test = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10)
        _test.close()
        print("[db] Neon connection OK")
    except Exception as _e:
        print(f"[db] Connection failed: {_e}")
        USE_DB = False

'''

# Match the "try: import psycopg ... USE_DB = False" region
match = re.search(
    r"try:\s*\n\s*import psycopg[\s\S]*?USE_DB = False\n",
    code
)
if match:
    old_block = match.group(0)
    code = code.replace(old_block, new_import_block, 1)
    changes += 1
    print("  OK - import + DB init replaced")
else:
    print("  FAIL - could not locate psycopg import block")

# ═══════════════════════════════════════════════════════════════
# 2. Replace _db_init_schema, _db_exec, _db_one, _db_all
#    with direct-connection versions
# ═══════════════════════════════════════════════════════════════
print("\n[2] Replacing DB helper functions...")

old_helpers = re.compile(
    r"def _db_init_schema\(\):[\s\S]*?(?=\n# ---------- Workflow storage|def save_workflow)",
    re.DOTALL
)

new_helpers = '''def _db_init_schema():
    if not USE_DB:
        return
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workflows (
                        name TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS credentials (
                        service TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS execution_logs (
                        id BIGSERIAL PRIMARY KEY,
                        workflow TEXT NOT NULL,
                        source TEXT NOT NULL,
                        status TEXT,
                        result TEXT,
                        logs JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_exec_wf_created
                        ON execution_logs(workflow, created_at DESC);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_messages (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        role TEXT NOT NULL,
                        text TEXT NOT NULL,
                        session_id TEXT
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mem_created
                        ON memory_messages(created_at DESC);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_facts (
                        key TEXT PRIMARY KEY,
                        value JSONB,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
        print("[db] Schema ready")
    except Exception as e:
        print(f"[db] Schema init failed: {e}")


def _db_exec(query, params=None):
    if not USE_DB:
        return False
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
        return True
    except Exception as e:
        print(f"[db] exec failed: {e}")
        return False


def _db_one(query, params=None):
    if not USE_DB:
        return None
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                return cur.fetchone()
    except Exception as e:
        print(f"[db] query failed: {e}")
        return None


def _db_all(query, params=None):
    if not USE_DB:
        return []
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                return cur.fetchall() or []
    except Exception as e:
        print(f"[db] query failed: {e}")
        return []

'''

if old_helpers.search(code):
    code = old_helpers.sub(new_helpers, code, count=1)
    changes += 1
    print("  OK - helper functions replaced")
else:
    print("  FAIL - helpers not matched (already updated?)")

# ═══════════════════════════════════════════════════════════════
# 3. Remove the old _db_init_schema() call at module scope if present
#    (it's included inside new helpers block now)
# ═══════════════════════════════════════════════════════════════
print("\n[3] Ensuring schema init is called once...")

# Remove any standalone _db_init_schema() call that isn't the definition
# We'll re-add it right after the helpers block
code = re.sub(r'^_db_init_schema\(\)\s*$', '', code, flags=re.MULTILINE)

# Insert one call right after the new helpers block
if "_db_init_schema()" not in code.split("def _db_exec")[0]:
    # find end of _db_all function and insert call
    anchor = "def _db_all(query, params=None):"
    idx = code.find(anchor)
    if idx != -1:
        # find the end of that function (next "def " at col 0)
        end_idx = code.find("\ndef ", idx + 10)
        if end_idx == -1:
            end_idx = len(code)
        code = code[:end_idx] + "\n\n_db_init_schema()\n" + code[end_idx:]
        changes += 1
        print("  OK - db init call inserted")
else:
    print("  SKIP - init call already present")

# ═══════════════════════════════════════════════════════════════
# 4. Update save/load workflow to match table column `payload`
# ═══════════════════════════════════════════════════════════════
print("\n[4] Verifying workflow storage functions...")

# Only patch if old column name 'data' is still used
old_save = '''    if USE_DB:
        _db_exec(
            """INSERT INTO workflows (name, payload, updated_at)
               VALUES (%s, %s::jsonb, NOW())
               ON CONFLICT (name) DO UPDATE SET
                 payload = EXCLUDED.payload,
                 updated_at = NOW()""",
            (name, json.dumps(wf))
        )
        return'''

if 'INSERT INTO workflows (name, payload' not in code:
    old_save_v1 = '''    if USE_DB:
        _db_exec(
            """INSERT INTO workflows (name, data, updated_at)
               VALUES (%s, %s::jsonb, NOW())
               ON CONFLICT (name) DO UPDATE SET
                 data = EXCLUDED.data,
                 updated_at = NOW()""",
            (name, json.dumps(wf))
        )
        return'''
    if old_save_v1 in code:
        code = code.replace(old_save_v1, old_save, 1)
        changes += 1
        print("  OK - save_workflow fixed")
    else:
        print("  SKIP - save_workflow already correct")

# ═══════════════════════════════════════════════════════════════
# 5. Write + verify
# ═══════════════════════════════════════════════════════════════
with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

print("\n" + "=" * 55)
print(f"Wrote {len(code)} chars — {changes} change(s)")
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
    shutil.copy(SERVER + '.backup_db', SERVER)
    print("Restored from backup")
    exit(1)

# Verify presence
with open(SERVER, 'r', encoding='utf-8') as f:
    final = f.read()

checks = [
    ("psycopg import",       "import psycopg" in final),
    ("No psycopg_pool",      "psycopg_pool" not in final),
    ("DATABASE_URL read",    'os.environ.get("DATABASE_URL"' in final),
    ("USE_DB computed",      "USE_DB = bool(DATABASE_URL)" in final),
    ("Connection test",      "Neon connection OK" in final),
    ("Schema init",          "def _db_init_schema" in final),
    ("db_exec helper",       "def _db_exec" in final),
    ("save_workflow DB",     "INSERT INTO workflows (name, payload" in final),
    ("load_workflow DB",     "SELECT payload FROM workflows" in final),
    ("save_creds DB",        "INSERT INTO credentials" in final),
    ("memory DB",            "INSERT INTO memory_messages" in final),
    ("Schema call once",     final.count("_db_init_schema()") >= 1),
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
    print("NOTHING CHANGED — already patched")
else:
    print("PARTIAL — review FAIL lines")