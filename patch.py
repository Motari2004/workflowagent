import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found:", SERVER); exit(1)

shutil.copy(SERVER, SERVER + '.backup_direct')
print("Backed up to server.py.backup_direct\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

print(f"File: {len(code)} chars\n")
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Remove psycopg_pool from imports (keep psycopg only)
# ═══════════════════════════════════════════════════════════════
print("[1] Fixing imports — drop psycopg_pool...")

old_imports = '''try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    _HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    dict_row = None
    ConnectionPool = None
    _HAS_PSYCOPG = False'''

new_imports = '''try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError as _ie:
    psycopg = None
    dict_row = None
    _HAS_PSYCOPG = False
    print(f"[db] psycopg import failed: {_ie}")'''

if old_imports in code:
    code = code.replace(old_imports, new_imports, 1)
    changes += 1
    print("  OK - imports fixed")
else:
    print("  SKIP - imports already correct or different")

# ═══════════════════════════════════════════════════════════════
# 2. Replace pool init with direct connection test
# ═══════════════════════════════════════════════════════════════
print("\n[2] Replacing pool init with direct connect...")

old_pool = '''_pool = None
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
        USE_DB = False'''

new_pool = '''_pool = None
if USE_DB:
    try:
        _test = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10)
        _test.close()
        print("[db] Neon connection OK (direct connect)")
    except Exception as _e:
        print(f"[db] Connection failed: {_e} — falling back to filesystem")
        USE_DB = False'''

if old_pool in code:
    code = code.replace(old_pool, new_pool, 1)
    changes += 1
    print("  OK - pool init replaced")
else:
    print("  SKIP - pool init already replaced or different")

# ═══════════════════════════════════════════════════════════════
# 3. Replace _db_init_schema, _db_exec, _db_one, _db_all
#    (all four currently use _pool.connection())
# ═══════════════════════════════════════════════════════════════
print("\n[3] Replacing DB helper functions...")

# Match all four together from def _db_init_schema to end of _db_all
pattern = re.compile(
    r"def _db_init_schema\(\):.*?(?=\ndef memory_save_message)",
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
                        name        TEXT PRIMARY KEY,
                        payload     JSONB NOT NULL,
                        updated_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS credentials (
                        service     TEXT PRIMARY KEY,
                        payload     JSONB NOT NULL,
                        updated_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS execution_logs (
                        id          BIGSERIAL PRIMARY KEY,
                        workflow    TEXT NOT NULL,
                        source      TEXT NOT NULL,
                        status      TEXT,
                        result      JSONB,
                        logs        JSONB,
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_exec_wf_created
                        ON execution_logs(workflow, created_at DESC);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_messages (
                        id          BIGSERIAL PRIMARY KEY,
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        role        TEXT NOT NULL,
                        text        TEXT NOT NULL,
                        session_id  TEXT
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mem_created
                        ON memory_messages(created_at DESC);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_facts (
                        key         TEXT PRIMARY KEY,
                        value       JSONB,
                        updated_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
        print("[db] schema ensured")
    except Exception as e:
        print(f"[db] schema init failed: {e}")


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
if pattern.search(code):
    code = pattern.sub(new_helpers, code, count=1)
    changes += 1
    print("  OK - helper functions replaced")
else:
    print("  FAIL - could not match helper block")

# ═══════════════════════════════════════════════════════════════
# 4. Remove the standalone "_db_init_schema()" call at module
#    scope (it's inside the new block now), then re-add ONE call
#    right after the new _db_all function.
# ═══════════════════════════════════════════════════════════════
print("\n[4] Ensuring schema init is called exactly once...")

# Strip any standalone top-level call
code = re.sub(r'^_db_init_schema\(\)\s*$', '', code, flags=re.MULTILINE)

# Insert one call after _db_all definition
anchor = "\ndef _db_all(query, params=None):"
if anchor in code:
    # find end of _db_all function
    idx = code.find(anchor)
    end = code.find("\ndef ", idx + 10)
    if end == -1:
        end = code.find("\n\n\n", idx)
    if end != -1:
        code = code[:end] + "\n\n_db_init_schema()\n" + code[end:]
        changes += 1
        print("  OK - schema init call inserted after _db_all")
    else:
        print("  SKIP - could not find end of _db_all")
else:
    print("  SKIP - _db_all not found")

# ═══════════════════════════════════════════════════════════════
# Write and verify
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
    shutil.copy(SERVER + '.backup_direct', SERVER)
    print("Restored from backup")
    exit(1)

# ═══════════════════════════════════════════════════════════════
# Verify all pieces in place
# ═══════════════════════════════════════════════════════════════
with open(SERVER, 'r', encoding='utf-8') as f:
    final = f.read()

checks = [
    ("psycopg import present",     "import psycopg" in final),
    ("No psycopg_pool anywhere",   "psycopg_pool" not in final),
    ("No ConnectionPool",          "ConnectionPool" not in final),
    ("DATABASE_URL read",          'os.environ.get("DATABASE_URL"' in final),
    ("USE_DB computed",            "USE_DB = bool(DATABASE_URL)" in final),
    ("Direct connection test",     "Neon connection OK (direct connect)" in final),
    ("_db_init_schema direct",     'psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10)' in final),
    ("save_workflow DB path",      "INSERT INTO workflows (name, payload" in final),
    ("load_workflow DB path",      "SELECT payload FROM workflows" in final),
    ("save_creds DB path",         "INSERT INTO credentials" in final),
    ("memory_save_message DB",     "INSERT INTO memory_messages" in final),
    ("Schema init call exists",    final.count("_db_init_schema()") >= 1),
    ("app = Flask present",        "app = Flask(__name__)" in final),
    ("app.run inside __main__",
        any(line.startswith('    ') and 'app.run(host' in line for line in final.split('\n'))),
]
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

print()
if all_ok and changes > 0:
    print("PATCH COMPLETE — all checks passed")
elif changes == 0:
    print("NOTHING CHANGED — already patched")
else:
    print("PARTIAL — review FAIL lines")

print()
print("NEXT STEPS:")
print()
print("1. Update requirements.txt (remove psycopg_pool):")
print("   flask>=3.0")
print("   flask-cors>=4.0")
print("   requests>=2.31")
print("   python-dotenv>=1.0")
print("   psycopg[binary]>=3.2")
print("   ollama>=0.3.0")
print()
print("2. Test locally:")
print("   python -c \"import server; print('app:', server.app, 'USE_DB:', server.USE_DB)\"")
print()
print("3. Commit and push:")
print("   git add server.py requirements.txt")
print("   git commit -m 'DB: direct psycopg connect, drop pool'")
print("   git push")