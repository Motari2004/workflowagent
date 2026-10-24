import os, shutil, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'

if not os.path.exists(SERVER):
    print("Not found:", SERVER); exit(1)

shutil.copy(SERVER, SERVER + '.backup_direct')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

print("File:", len(code), "chars\n")
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Fix imports — drop psycopg_pool
# ═══════════════════════════════════════════════════════════════
print("[1] Fixing imports...")

old = '''try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    _HAS_PSYCOPG = True
except ImportError:
    psycopg = None
    dict_row = None
    ConnectionPool = None
    _HAS_PSYCOPG = False'''

new = '''try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError as _ie:
    psycopg = None
    dict_row = None
    _HAS_PSYCOPG = False
    print(f"[db] psycopg import failed: {_ie}")'''

if old in code:
    code = code.replace(old, new, 1)
    changes += 1
    print("  OK - imports fixed")
else:
    print("  SKIP - imports already fixed")

# ═══════════════════════════════════════════════════════════════
# 2. Replace ConnectionPool init with direct-connect test
# ═══════════════════════════════════════════════════════════════
print("\n[2] Replacing pool init...")

old = '''_pool = None
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

new = '''_pool = None
if USE_DB:
    try:
        _test = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10)
        _test.close()
        print("[db] Neon connection OK (direct connect)")
    except Exception as _e:
        print(f"[db] Connection failed: {_e} — falling back to filesystem")
        USE_DB = False'''

if old in code:
    code = code.replace(old, new, 1)
    changes += 1
    print("  OK - pool init replaced")
else:
    print("  SKIP - pool init already replaced")

# ═══════════════════════════════════════════════════════════════
# 3. Replace _db_exec / _db_one / _db_all / _db_init_schema
#    to use direct psycopg.connect instead of _pool.connection()
# ═══════════════════════════════════════════════════════════════
print("\n[3] Replacing DB helpers...")

pattern = re.compile(
    r"def _db_init_schema\(\):.*?(?=\ndef memory_save_message)",
    re.DOTALL
)

new_block = '''def _db_init_schema():
    if not USE_DB:
        return
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workflows (
                        name TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS credentials (
                        service TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS execution_logs (
                        id BIGSERIAL PRIMARY KEY,
                        workflow TEXT NOT NULL,
                        source TEXT NOT NULL,
                        status TEXT,
                        result JSONB,
                        logs JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_exec_wf_created
                        ON execution_logs(workflow, created_at DESC);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_messages (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
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
                        updated_at TIMESTAMPTZ DEFAULT NOW()
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
    code = pattern.sub(new_block, code, count=1)
    changes += 1
    print("  OK - helpers replaced")
else:
    print("  FAIL - could not match helper block")

# ═══════════════════════════════════════════════════════════════
# 4. Ensure single schema-init call after helpers
# ═══════════════════════════════════════════════════════════════
print("\n[4] Ensuring schema init runs once...")

# Remove stray top-level calls
code = re.sub(r'^_db_init_schema\(\)\s*$', '', code, flags=re.MULTILINE)

# Insert one call after _db_all
anchor = "\ndef _db_all(query, params=None):"
if anchor in code and "\n_db_init_schema()\n" not in code:
    idx = code.find(anchor)
    end = code.find("\ndef ", idx + 10)
    if end != -1:
        code = code[:end] + "\n\n_db_init_schema()\n" + code[end:]
        changes += 1
        print("  OK - init call inserted")

# ═══════════════════════════════════════════════════════════════
# Write and verify
# ═══════════════════════════════════════════════════════════════
with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

print("\n" + "=" * 55)
print(f"Wrote {len(code)} chars — {changes} change(s)")
print("=" * 55)

print("\nSyntax check...")
try:
    with open(SERVER, 'r', encoding='utf-8') as f:
        compile(f.read(), SERVER, 'exec')
    print("OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR line {e.lineno}: {e.msg}")
    shutil.copy(SERVER + '.backup_direct', SERVER)
    print("Restored from backup")
    exit(1)

# Final verification
with open(SERVER, 'r', encoding='utf-8') as f:
    final = f.read()

checks = [
    ("psycopg import",          "import psycopg" in final),
    ("No psycopg_pool",         "psycopg_pool" not in final),
    ("No ConnectionPool",       "ConnectionPool" not in final),
    ("Direct connect helpers",  final.count("psycopg.connect(DATABASE_URL") >= 4),
    ("Schema call present",     final.count("_db_init_schema()") >= 1),
    ("app = Flask",             "app = Flask(__name__)" in final),
]
print("\nVERIFICATION:")
all_ok = True
for name, ok in checks:
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
    if not ok:
        all_ok = False

print()
if all_ok and changes > 0:
    print("PATCH COMPLETE")
else:
    print("Review FAIL lines")

print()
print("NEXT:")
print("1. requirements.txt should be:")
print("   flask>=3.0")
print("   flask-cors>=4.0")
print("   requests>=2.31")
print("   python-dotenv>=1.0")
print("   psycopg[binary]>=3.2")
print("   ollama>=0.3.0")
print()
print("2. git add server.py requirements.txt")
print("   git commit -m 'DB: direct connect, no psycopg_pool'")
print("   git push")