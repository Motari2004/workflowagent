# -*- coding: utf-8 -*-
import os, shutil, sys, re

PROJECT = r'C:\Users\PC\Desktop\modular\workflow-pro-v3'
SERVER = os.path.join(PROJECT, 'server.py')
HTML = os.path.join(PROJECT, 'public', 'index.html')

for f in [SERVER, HTML]:
    if not os.path.exists(f):
        print("FAIL: missing " + f); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_v24')
shutil.copy(HTML, HTML + '.backup_v24')
print("Backed up\n")

# ============================================================
# SERVER.PY — add Unsplash integration + tracking
# ============================================================
print("=" * 55)
print("SERVER.PY")
print("=" * 55)

with open(SERVER, 'r', encoding='utf-8') as f:
    server = f.read()

sc = 0

# --- 1. Schema: add used_images table ---
print("\n[1] Adding used_images table...")

if 'CREATE TABLE IF NOT EXISTS used_images' not in server:
    # Add to _db_init_schema
    old_schema = '''                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_facts (
                        key TEXT PRIMARY KEY,
                        value JSONB,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)'''

    new_schema = '''                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_facts (
                        key TEXT PRIMARY KEY,
                        value JSONB,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS used_images (
                        photo_id TEXT PRIMARY KEY,
                        url TEXT NOT NULL,
                        source TEXT,
                        used_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_used_images_used_at
                        ON used_images(used_at DESC);
                """)'''

    if old_schema in server:
        server = server.replace(old_schema, new_schema, 1)
        sc += 1
        print("  OK: used_images table added to schema")
    else:
        print("  WARN: schema pattern not matched")
else:
    print("  SKIP: used_images table already exists")

# --- 2. Add used_images helper functions ---
print("\n[2] Adding image tracking helpers...")

if 'def get_used_image_ids' not in server:
    # Insert before the tools section
    marker = "# ---------- 20 TOOL HANDLERS ----------"
    helpers = '''# ---------- Image tracking ----------
USED_IMAGES_FILE = MEMORY_DIR / "used_images.json"

def get_used_image_ids():
    """Return set of photo IDs already used."""
    if USE_DB:
        rows = _db_all("SELECT photo_id FROM used_images")
        return set(r["photo_id"] for r in rows)
    if USED_IMAGES_FILE.exists():
        try:
            data = json.loads(USED_IMAGES_FILE.read_text(encoding='utf-8'))
            return set(item.get('photo_id', '') for item in data)
        except Exception:
            pass
    return set()

def mark_image_used(photo_id, url, source='unsplash'):
    """Mark a photo as used."""
    if not photo_id:
        return False
    if USE_DB:
        _db_exec(
            """INSERT INTO used_images (photo_id, url, source, used_at)
               VALUES (%s, %s, %s, NOW())
               ON CONFLICT (photo_id) DO NOTHING""",
            (photo_id, url, source)
        )
        return True
    # Filesystem
    items = []
    if USED_IMAGES_FILE.exists():
        try:
            items = json.loads(USED_IMAGES_FILE.read_text(encoding='utf-8'))
        except Exception:
            items = []
    if not any(i.get('photo_id') == photo_id for i in items):
        items.append({
            'photo_id': photo_id,
            'url': url,
            'source': source,
            'used_at': datetime.utcnow().isoformat() + 'Z',
        })
        USED_IMAGES_FILE.write_text(json.dumps(items, indent=2), encoding='utf-8')
    return True

def get_used_images_list(limit=50):
    """Return list of used images, most recent first."""
    if USE_DB:
        rows = _db_all(
            """SELECT photo_id, url, source, used_at
               FROM used_images
               ORDER BY used_at DESC LIMIT %s""",
            (limit,)
        )
        for r in rows:
            if r.get('used_at'):
                r['used_at'] = r['used_at'].isoformat() + 'Z'
        return rows
    if USED_IMAGES_FILE.exists():
        try:
            items = json.loads(USED_IMAGES_FILE.read_text(encoding='utf-8'))
            items.sort(key=lambda x: x.get('used_at', ''), reverse=True)
            return items[:limit]
        except Exception:
            pass
    return []

def fetch_random_unsplash_image(query='nature'):
    """Fetch a random Unsplash photo, skipping already-used IDs.
    
    Requires UNSPLASH_ACCESS_KEY in credentials (service='unsplash').
    Falls back to picsum.photos if Unsplash not configured or exhausted.
    """
    creds = load_creds('unsplash') or {}
    access_key = (creds.get('access_key') or '').strip()
    
    used_ids = get_used_image_ids()
    print(f"[unsplash] {len(used_ids)} images already used")
    
    if access_key:
        # Try up to 30 random pages, 30 photos each = up to 900 candidates
        import random as _random
        for attempt in range(30):
            try:
                page = _random.randint(1, 100)
                r = requests.get(
                    "https://api.unsplash.com/photos/random",
                    headers={
                        "Authorization": f"Client-ID {access_key}",
                        "Accept-Version": "v1",
                    },
                    params={
                        "query": query,
                        "orientation": "squarish",
                        "count": 1,
                    },
                    timeout=15,
                )
            except Exception as e:
                print(f"[unsplash] network error: {e}")
                break
            
            if r.status_code == 401:
                print("[unsplash] 401 Unauthorized - check access key")
                break
            if r.status_code == 403:
                print("[unsplash] 403 - rate limit reached")
                break
            if r.status_code != 200:
                print(f"[unsplash] HTTP {r.status_code}: {r.text[:200]}")
                continue
            
            try:
                data = r.json()
            except Exception:
                continue
            
            # /photos/random returns a single object (not an array)
            if isinstance(data, list):
                data = data[0] if data else None
            if not data:
                continue
            
            photo_id = data.get('id', '')
            if not photo_id:
                continue
            if photo_id in used_ids:
                print(f"[unsplash] {photo_id} already used, retrying")
                continue
            
            # Use the "regular" URL size (1080w, quality 80) — big enough for Instagram
            urls = data.get('urls') or {}
            image_url = urls.get('regular') or urls.get('full') or urls.get('small')
            if not image_url:
                continue
            
            # Unsplash attribution (required by their ToS)
            user = data.get('user') or {}
            attribution = {
                'photographer_name': user.get('name', 'Unknown'),
                'photographer_url': user.get('links', {}).get('html', ''),
            }
            
            return {
                'url': image_url,
                'photo_id': photo_id,
                'source': 'unsplash',
                'attribution': attribution,
                'query': query,
            }
        
        print("[unsplash] exhausted attempts, falling back to picsum")
    
    # Fallback: picsum.photos (always works, no API key)
    import uuid as _uuid
    seed = _uuid.uuid4().hex[:10]
    fallback_url = f"https://picsum.photos/seed/{seed}/1024/1024"
    return {
        'url': fallback_url,
        'photo_id': f'picsum_{seed}',
        'source': 'picsum',
        'attribution': {'photographer_name': 'Picsum', 'photographer_url': 'https://picsum.photos'},
        'query': None,
    }


'''
    if marker in server:
        server = server.replace(marker, helpers + marker, 1)
        sc += 1
        print("  OK: image tracking helpers added")
    else:
        print("  FAIL: insertion marker not found")

# --- 3. Add HTTP endpoints for image tracking ---
print("\n[3] Adding /images/next and /images/mark-used endpoints...")

if '@app.route(\'/images/next\'' not in server:
    # Insert before the buffer_channels route (stable anchor)
    anchor = "@app.route('/buffer/channels', methods=['GET'])"
    new_routes = '''@app.route('/images/next', methods=['GET'])
def images_next():
    """Return one random image URL, skipping already-used photos.
    
    Query params:
      - query: search term (default "nature")
      - mark_used: if "true", immediately mark as used (default false)
    """
    query = request.args.get('query', 'nature')
    mark_now = request.args.get('mark_used', 'false').lower() == 'true'
    try:
        result = fetch_random_unsplash_image(query)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if not result.get('url'):
        return jsonify({"error": "No image found"}), 500
    if mark_now:
        try:
            mark_image_used(result['photo_id'], result['url'], result.get('source', 'unknown'))
        except Exception as e:
            print(f"[images/next] mark_used failed: {e}")
    return jsonify(result)


@app.route('/images/mark-used', methods=['POST'])
def images_mark_used():
    """Mark a photo as used so it won't be returned again."""
    data = request.json or {}
    photo_id = data.get('photo_id', '').strip()
    url = data.get('url', '').strip()
    source = data.get('source', 'unsplash')
    if not photo_id:
        return jsonify({"error": "photo_id required"}), 400
    try:
        mark_image_used(photo_id, url, source)
        return jsonify({"ok": True, "photo_id": photo_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/images/used', methods=['GET'])
def images_used():
    """List recently used images."""
    limit = int(request.args.get('limit', 50))
    return jsonify({"images": get_used_images_list(limit), "count": len(get_used_images_list(limit))})


@app.route('/images/clear-used', methods=['POST'])
def images_clear_used():
    """Clear the used-images history (danger: allows reusing images)."""
    if USE_DB:
        _db_exec("DELETE FROM used_images")
    else:
        if USED_IMAGES_FILE.exists():
            USED_IMAGES_FILE.unlink()
    return jsonify({"ok": True, "message": "Used images cleared"})


@app.route('/buffer/channels', methods=['GET'])'''

    if anchor in server:
        server = server.replace(anchor, new_routes, 1)
        sc += 1
        print("  OK: image endpoints added")
    else:
        print("  FAIL: anchor not found for image endpoints")

# --- 4. execute_workflow: resolve media_urls from previous JSON ---
print("\n[4] Adding dynamic media_urls resolution...")

old_tool_dispatch = '''            elif node_type == 'tool':
                service = node_data.get('service', 'http-custom')
                handler = TOOL_HANDLERS.get(service)
                if not handler:
                    current_memory = f"[ERROR] Unknown tool: {service}"; logs.append(current_memory)
                else:'''

new_tool_dispatch = '''            elif node_type == 'tool':
                service = node_data.get('service', 'http-custom')
                handler = TOOL_HANDLERS.get(service)
                if not handler:
                    current_memory = f"[ERROR] Unknown tool: {service}"; logs.append(current_memory)
                else:
                    # --- Dynamic media_urls from previous JSON ---
                    # If node_data.media_urls == "FROM_PREVIOUS", parse current_memory
                    # as JSON and use its media_urls field
                    if node_data.get('media_urls') == 'FROM_PREVIOUS' or node_data.get('media_urls') == ['FROM_PREVIOUS']:
                        try:
                            prev = json.loads(current_memory)
                            if isinstance(prev, dict) and prev.get('media_urls'):
                                node_data['media_urls'] = prev['media_urls']
                                print(f"[dynamic] media_urls from previous: {prev['media_urls']}")
                        except Exception as e:
                            print(f"[dynamic] failed to parse previous: {e}")
                    # Also if node_data.message == "FROM_PREVIOUS", use previous text field
                    if node_data.get('message') == 'FROM_PREVIOUS':
                        try:
                            prev = json.loads(current_memory)
                            if isinstance(prev, dict) and prev.get('message'):
                                node_data['message'] = prev['message']
                                print(f"[dynamic] message from previous: {prev['message'][:80]}")
                        except Exception as e:
                            print(f"[dynamic] failed to parse previous: {e}")
'''

if old_tool_dispatch in server:
    server = server.replace(old_tool_dispatch, new_tool_dispatch, 1)
    sc += 1
    print("  OK: dynamic media_urls resolution added")
else:
    print("  WARN: tool dispatch pattern not matched")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(server)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("\n  [OK  ] server.py compiles")
except SyntaxError as e:
    print("\n  [FAIL] line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_v24', SERVER)
    sys.exit(1)

# ============================================================
# Verify
# ============================================================
print("\n" + "=" * 55)
print("VERIFICATION")
print("=" * 55)

fs = open(SERVER, 'r', encoding='utf-8').read()

checks = [
    ("used_images table",         "CREATE TABLE IF NOT EXISTS used_images" in fs),
    ("get_used_image_ids",        "def get_used_image_ids" in fs),
    ("mark_image_used",           "def mark_image_used" in fs),
    ("fetch_random_unsplash",     "def fetch_random_unsplash_image" in fs),
    ("/images/next route",        "@app.route('/images/next'" in fs),
    ("/images/mark-used route",   "@app.route('/images/mark-used'" in fs),
    ("/images/used route",        "@app.route('/images/used'" in fs),
    ("dynamic media resolution",  "FROM_PREVIOUS" in fs),
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
    print(f"\nChanges: {sc} in server.py")
    print()
    print("Next steps:")
    print()
    print("1. Get an Unsplash Access Key (free):")
    print("   https://unsplash.com/developers")
    print("   → Create New Application → copy Access Key")
    print()
    print("2. Save it to credentials:")
    print("   curl -X PUT http://localhost:10000/credentials/unsplash \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"access_key\": \"YOUR_ACCESS_KEY\"}'")
    print()
    print("3. Restart Flask:")
    print("   taskkill /F /IM python.exe")
    print("   python server.py")
    print()
    print("4. Test the endpoint:")
    print("   curl http://localhost:10000/images/next")
    print()
    print("5. Then build the new workflow (see docs below)")
else:
    print("Review FAIL lines. Backup: server.py.backup_v24")