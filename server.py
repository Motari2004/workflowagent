from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
import requests
try:
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except ImportError as _ie:
    psycopg = None
    dict_row = None
    _HAS_PSYCOPG = False
    print(f"[db] psycopg import failed: {_ie}")

from dotenv import load_dotenv
import os as _os
load_dotenv()  # loads .env from the current directory

import json
import time
import uuid
import threading
import re
from datetime import datetime
from pathlib import Path
import os

app = Flask(__name__)

# ============================================================
# Available AI models for the assistant panel
# ============================================================
AVAILABLE_MODELS = {
    # Gemini models — all support Google Search grounding
    'gemini-flash-25':  {'provider': 'gemini', 'model': 'gemini-2.5-flash',          'label': 'Gemini 2.5 Flash'},
    'gemini-pro-25':    {'provider': 'gemini', 'model': 'gemini-2.5-pro',            'label': 'Gemini 2.5 Pro'},
    'gemini-flash-31':  {'provider': 'gemini', 'model': 'gemini-3.1-pro-preview',    'label': 'Gemini 3.1 Pro (Preview)'},
    'gemini-flash-35':  {'provider': 'gemini', 'model': 'gemini-3.5-flash',          'label': 'Gemini 3.5 Flash'},
    'gemini-flash-38':  {'provider': 'gemini', 'model': 'gemini-3.8-flash',          'label': 'Gemini 3.8 Flash'},

    # Ollama models (no internet access)
    'ollama-gpt':       {'provider': 'ollama', 'model': 'gpt-oss:120b',               'label': 'Ollama GPT (no internet)'},
    'ollama-gemma':     {'provider': 'ollama', 'model': 'gemma4:31b-cloud',           'label': 'Ollama Gemma 4 (no internet)'},
}

# ============================================================
# AI model helpers — used by /ai-chat
# ============================================================

def _gemini_call(api_key, system, contents, model_name='gemini-flash-latest', max_retries=2, use_search=False):
    """Call Gemini API with retry logic. Optional Google Search grounding."""
    import time
    for attempt in range(max_retries):
        try:
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}
            }
            if use_search:
                payload["tools"] = [{"google_search": {}}]
            
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60
            )
            if r.status_code == 200:
                try:
                    return r.json()['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    print(f"[gemini] Unexpected response shape: {r.text[:200]}")
                    return None
            elif r.status_code == 503:
                print(f"[gemini] 503 overloaded (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            else:
                print(f"[gemini] Error {r.status_code}: {r.text[:300]}")
                return None
        except requests.exceptions.Timeout:
            print(f"[gemini] Timeout (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None
        except Exception as e:
            print(f"[gemini] Exception: {e}")
            return None
    return None


def _ollama_call(message, system, model_override=None):
    """Call Ollama Cloud API."""
    api_key = _os.environ.get('OLLAMA_API_KEY')
    host = _os.environ.get('OLLAMA_HOST', 'https://ollama.com')
    model = model_override or _os.environ.get('OLLAMA_MODEL', 'gemma4:31b')

    # Fallback to credentials file if .env not set
    if not api_key:
        try:
            c = load_creds('ollama')
            if c:
                api_key = c.get('api_key')
                host = c.get('host', host)
                model = model_override or c.get('model', model)
        except Exception:
            pass

    if not api_key:
        print("[ollama] No API key configured")
        return None

    try:
        r = requests.post(
            f"{host}/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message}
                ],
                "stream": False
            },
            timeout=60
        )
        if r.status_code == 200:
            return r.json().get('message', {}).get('content', '')
        else:
            print(f"[ollama] Error {r.status_code}: {r.text[:300]}")
            return None
    except Exception as e:
        print(f"[ollama] Exception: {e}")
        return None



CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Methods', '*')
    return response

SYMBOL_MAP = {'bitcoin':'BTC','ethereum':'ETH','solana':'SOL','binancecoin':'BNB','cardano':'ADA','ripple':'XRP','dogecoin':'DOGE'}








# ============================================================
# STORAGE — Postgres (Neon) when DATABASE_URL is set, else local files
# ============================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_DB = bool(DATABASE_URL) and _HAS_PSYCOPG

_pool = None
if USE_DB:
    try:
        _test = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True, connect_timeout=10)
        _test.close()
        print("[db] Neon connection OK (direct connect)")
    except Exception as _e:
        print(f"[db] Connection failed: {_e} — falling back to filesystem")
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



_db_init_schema()

def memory_save_message(role, text, session_id=None):
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
        f.write(json.dumps(entry) + "\n")
    return entry

def memory_recent(hours=24, limit=30):
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
    return messages[-limit:]

def memory_load_facts():
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
    return {"name": None, "preferences": [], "projects": []}

def memory_save_fact(key, value):
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
    return facts

def memory_build_context():
    """Build the system prompt memory block."""
    facts = memory_load_facts()
    recent = memory_recent(hours=48, limit=20)

    parts = []
    if facts.get("name"):
        parts.append(f"User's name: {facts['name']}")
    if facts.get("preferences"):
        parts.append("User preferences: " + "; ".join(facts["preferences"]))
    if facts.get("projects"):
        parts.append("Active projects: " + "; ".join(facts["projects"]))

    if recent:
        parts.append("\nRECENT CONVERSATION:")
        for m in recent[-10:]:
            role = "User" if m["role"] == "user" else "AI"
            parts.append(f"{role}: {m['text'][:200]}")

    if not parts:
        return ""

    return "\n\nMEMORY (things you know about this user):\n" + "\n".join(parts)



_schedulers = {}
_scheduler_lock = threading.Lock()

# ---------- Workflow storage ----------
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
    if p.exists(): p.unlink()

# ---------- Execution log ----------
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
        f.write(json.dumps(entry)+"\n")
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
    lines = [l for l in p.read_text(encoding='utf-8').split("\n") if l.strip()]
    return [json.loads(l) for l in lines[-limit:]][::-1]

# ---------- Credentials ----------
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
    if p.exists(): p.unlink()

# ---------- Helper ----------
def extract_number(s):
    if not s: return None
    m = re.search(r'-?[\d,]+\.?\d*', str(s).replace(',', ''))
    return float(m.group()) if m else None

# ---------- 20 TOOL HANDLERS ----------
# Each handler receives (creds dict, message string, extra dict) -> result string

def tool_discord(creds, msg, extra):
    url = creds.get('webhook_url')
    if not url: return "[ERROR] Discord webhook not configured"
    
    # If msg is a file path, upload the file as an attachment
    if msg and os.path.exists(msg.strip()):
        try:
            filepath = msg.strip()
            ext = os.path.splitext(filepath)[1].lower()
            mime = {
                '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg',
                '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.gif': 'image/gif', '.mp4': 'video/mp4', '.pdf': 'application/pdf',
            }.get(ext, 'application/octet-stream')
            with open(filepath, 'rb') as f:
                files = {'file': (os.path.basename(filepath), f, mime)}
                r = requests.post(url, data={'content': '🔊 Generated audio'}, files=files, timeout=30)
            return f"Discord {r.status_code} (file uploaded: {os.path.basename(filepath)})"
        except Exception as e:
            return f"[ERROR] Discord upload: {e}"
    
    # Otherwise send as text
    try:
        r = requests.post(url, json={"content": msg or "(empty)"}, timeout=10)
        return f"Discord {r.status_code}"
    except Exception as e: return f"[ERROR] Discord: {e}"

def tool_slack(creds, msg, extra):
    url = creds.get('webhook_url')
    if not url: return "[ERROR] Slack webhook not configured"
    try:
        r = requests.post(url, json={"text": msg or "(empty)"}, timeout=10)
        return f"Slack {r.status_code}"
    except Exception as e: return f"[ERROR] Slack: {e}"

def tool_telegram(creds, msg, extra):
    token, chat = creds.get('bot_token'), creds.get('chat_id')
    if not token or not chat: return "[ERROR] Telegram not configured"
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": msg or "(empty)"}, timeout=10)
        return f"Telegram {r.status_code}"
    except Exception as e: return f"[ERROR] Telegram: {e}"

def tool_email_mailgun(creds, msg, extra):
    key, domain, to = creds.get('api_key'), creds.get('domain'), creds.get('to')
    frm = creds.get('from', f"bot@{domain}")
    if not (key and domain and to): return "[ERROR] Mailgun not configured"
    try:
        r = requests.post(f"https://api.mailgun.net/v3/{domain}/messages",
                          auth=("api", key),
                          data={"from": frm, "to": to, "subject": "Workflow Alert", "text": msg or "(empty)"},
                          timeout=15)
        return f"Mailgun {r.status_code}"
    except Exception as e: return f"[ERROR] Mailgun: {e}"

def tool_github_issue(creds, msg, extra):
    token, repo = creds.get('token'), creds.get('repo')  # repo = "owner/name"
    if not (token and repo): return "[ERROR] GitHub not configured"
    try:
        r = requests.post(f"https://api.github.com/repos/{repo}/issues",
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                          json={"title": (msg or "Workflow Issue")[:80], "body": msg or "", "labels": ["workflow"]},
                          timeout=15)
        if r.status_code in (200,201):
            return f"GitHub issue created: {r.json().get('html_url','')}"
        return f"GitHub {r.status_code}: {r.text[:150]}"
    except Exception as e: return f"[ERROR] GitHub: {e}"

def tool_github_comment(creds, msg, extra):
    token, repo, issue = creds.get('token'), creds.get('repo'), extra.get('issue_number')
    if not (token and repo and issue): return "[ERROR] GitHub comment not configured"
    try:
        r = requests.post(f"https://api.github.com/repos/{repo}/issues/{issue}/comments",
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                          json={"body": msg or ""}, timeout=15)
        return f"GitHub comment {r.status_code}"
    except Exception as e: return f"[ERROR] GitHub: {e}"

def tool_notion(creds, msg, extra):
    token, db_id = creds.get('token'), creds.get('database_id')
    if not (token and db_id): return "[ERROR] Notion not configured"
    try:
        r = requests.post("https://api.notion.com/v1/pages",
                          headers={"Authorization": f"Bearer {token}",
                                   "Notion-Version": "2022-06-28",
                                   "Content-Type": "application/json"},
                          json={"parent": {"database_id": db_id},
                                "properties": {"Name": {"title": [{"text": {"content": (msg or "Untitled")[:80]}}]}}},
                          timeout=15)
        return f"Notion {r.status_code}"
    except Exception as e: return f"[ERROR] Notion: {e}"

def tool_google_sheets(creds, msg, extra):
    """
    POST to a Google Apps Script webhook.
    Uses {"content": ...} format so the Apps Script parses it
    consistently with the HTTP Request node.
    """
    url = creds.get('webhook_url')
    if not url:
        return "[ERROR] Google Sheets: webhook_url not configured"
    try:
        r = requests.post(url, json={"content": msg or ""}, timeout=15)
        return f"Sheets {r.status_code}"
    except Exception as e:
        return f"[ERROR] Sheets: {e}"

def tool_twilio_sms(creds, msg, extra):
    sid, token, from_num, to_num = creds.get('sid'), creds.get('token'), creds.get('from'), creds.get('to')
    if not (sid and token and from_num and to_num): return "[ERROR] Twilio not configured"
    try:
        r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                          auth=(sid, token),
                          data={"From": from_num, "To": to_num, "Body": msg or "(empty)"},
                          timeout=15)
        return f"Twilio {r.status_code}"
    except Exception as e: return f"[ERROR] Twilio: {e}"

def tool_openai(creds, msg, extra):
    key = creds.get('api_key')
    if not key: return "[ERROR] OpenAI not configured"
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": creds.get('model', 'gpt-4o-mini'),
                                "messages": [{"role": "user", "content": msg or "Say hello"}]},
                          timeout=45)
        if r.status_code == 200:
            content = r.json()['choices'][0]['message']['content']
            return f"GPT: {content[:500]}"
        return f"OpenAI {r.status_code}: {r.text[:200]}"
    except Exception as e: return f"[ERROR] OpenAI: {e}"

def tool_stripe(creds, msg, extra):
    key = creds.get('api_key')
    if not key: return "[ERROR] Stripe not configured"
    try:
        r = requests.get("https://api.stripe.com/v1/balance",
                         headers={"Authorization": f"Bearer {key}"},
                         timeout=15)
        return f"Stripe {r.status_code}: {r.text[:200]}"
    except Exception as e: return f"[ERROR] Stripe: {e}"

def tool_weather(creds, msg, extra):
    city = creds.get('city', 'London')
    key = creds.get('api_key')  # OpenWeather key optional
    try:
        if key:
            r = requests.get(f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric", timeout=10)
            if r.status_code == 200:
                d = r.json()
                return f"{city}: {d['main']['temp']}°C, {d['weather'][0]['description']}"
        r = requests.get(f"https://wttr.in/{city}?format=%t+%C", timeout=10)
        return f"{city}: {r.text.strip()}"
    except Exception as e: return f"[ERROR] Weather: {e}"

def tool_coingecko(creds, msg, extra):
    coin = creds.get('coin', 'bitcoin')
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd", timeout=10)
        return f"CoinGecko: {r.text[:200]}"
    except Exception as e: return f"[ERROR] CoinGecko: {e}"

def tool_binance(creds, msg, extra):
    symbol = creds.get('symbol', 'BTCUSDT')
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=10)
        return f"Binance: {r.text[:200]}"
    except Exception as e: return f"[ERROR] Binance: {e}"

def tool_news(creds, msg, extra):
    key = creds.get('api_key')
    if not key: return "[ERROR] NewsAPI not configured"
    try:
        r = requests.get(f"https://newsapi.org/v2/top-headlines?country=us&apiKey={key}", timeout=10)
        if r.status_code == 200:
            titles = [a['title'] for a in r.json()['articles'][:3]]
            return "News: " + " | ".join(titles)
        return f"NewsAPI {r.status_code}"
    except Exception as e: return f"[ERROR] News: {e}"

def tool_rss(creds, msg, extra):
    url = creds.get('url')
    if not url: return "[ERROR] RSS URL not configured"
    try:
        r = requests.get(url, timeout=10)
        # naive RSS title extraction (avoid adding feedparser dep)
        titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', r.text)
        return "RSS: " + " | ".join(titles[1:4])[:300] if len(titles) > 1 else "RSS: (no items)"
    except Exception as e: return f"[ERROR] RSS: {e}"

def tool_webhook(creds, msg, extra):
    url = creds.get('url')
    if not url: return "[ERROR] Webhook URL not configured"
    try:
        r = requests.post(url, json={"content": msg or ""}, timeout=10)
        return f"Webhook {r.status_code}"
    except Exception as e: return f"[ERROR] Webhook: {e}"

def tool_http_custom(creds, msg, extra):
    url, method = creds.get('url'), creds.get('method', 'POST').upper()
    headers = creds.get('headers', {})
    body = creds.get('body')
    if not url: return "[ERROR] Custom HTTP: no URL"
    try:
        kwargs = {"timeout": 15, "headers": headers}
        if method in ('POST','PUT','PATCH'):
            kwargs["json"] = body if body else {"content": msg}
        r = requests.request(method, url, **kwargs)
        return f"HTTP {r.status_code}: {r.text[:250]}"
    except Exception as e: return f"[ERROR] HTTP: {e}"

def tool_mqtt_publish(creds, msg, extra):
    # Placeholder — requires paho-mqtt installed
    return "[INFO] MQTT requires 'pip install paho-mqtt' and extra setup"


def tool_gemini(creds, msg, extra):
    """Google Gemini API — free tier available at https://aistudio.google.com/apikey"""
    key = creds.get('api_key')
    if not key:
        return "[ERROR] Gemini: no API key"
    model = creds.get('model', 'gemini-3.5-flash')
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": msg or "Say hello"}]}]},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            try:
                text = data['candidates'][0]['content']['parts'][0]['text']
                return text.strip()
            except (KeyError, IndexError):
                return f"Gemini: unexpected response: {r.text[:200]}"
        return f"Gemini {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return f"[ERROR] Gemini: {e}"



def tool_ollama(creds, msg, extra):
    """
    Send a prompt to Ollama Cloud (ollama.com) or local Ollama.
    Reads OLLAMA_API_KEY, OLLAMA_HOST, OLLAMA_MODEL from .env
    unless overridden in credentials.
    """
    import os
    api_key = creds.get('api_key') or os.environ.get('OLLAMA_API_KEY')
    host = creds.get('host') or os.environ.get('OLLAMA_HOST', 'https://ollama.com')
    model = creds.get('model') or os.environ.get('OLLAMA_MODEL', 'gemma4:31b')

    if not api_key:
        return "[ERROR] Ollama: OLLAMA_API_KEY not set in .env or credentials"

    try:
        from ollama import Client
        client = Client(
            host=host,
            headers={'Authorization': f'Bearer {api_key}'}
        )
        response = client.chat(
            model=model,
            messages=[{'role': 'user', 'content': msg or 'Say hello'}]
        )
        return response.message.content
    except Exception as e:
        return f"[ERROR] Ollama: {e}"



import smtplib
from email.message import EmailMessage

def tool_gmail_smtp(creds, msg, extra):
    """Send email via Gmail SMTP using an App Password."""
    sender = creds.get('email')
    app_password = creds.get('app_password')
    recipient = creds.get('to')
    subject = (extra.get('subject') if extra else None) or "Workflow Alert"

    if not (sender and app_password and recipient):
        return "[ERROR] Gmail SMTP: missing email, app_password, or to"

    try:
        email = EmailMessage()
        email['From'] = sender
        email['To'] = recipient
        email['Subject'] = subject
        email.set_content(msg or '(empty)')

        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, app_password)
            server.send_message(email)

        return f"Gmail: sent to {recipient}"

    except smtplib.SMTPAuthenticationError:
        return "[ERROR] Gmail: auth failed — check App Password (16 chars, no spaces)"
    except smtplib.SMTPException as e:
        return f"[ERROR] Gmail SMTP: {e}"
    except Exception as e:
        return f"[ERROR] Gmail: {e}"


def tool_research(creds, msg, extra):
    query = (extra.get('query') or msg or '').strip()
    if not query:
        return "[ERROR] No research query"

    url = 'http://127.0.0.1:10000/api/remote_chat'
    body = {"message": query, "session_id": extra.get('session_id') or 'default_research', "voice": False}
    headers = {"Content-Type": "application/json"}

    print(f"[research] POST {url} query={query[:80]}")

    try:
        r = requests.post(url, json=body, headers=headers, timeout=90)
        print(f"[research] HTTP {r.status_code}")
    except requests.exceptions.Timeout:
        return "[ERROR] Research timed out (90s)"
    except requests.exceptions.ConnectionError as e:
        return f"[ERROR] Cannot reach 127.0.0.1:10000. {e}"
    except Exception as e:
        return f"[ERROR] Research failed: {e}"

    if r.status_code != 200:
        return f"[ERROR] Research HTTP {r.status_code}: {r.text[:300]}"

    try:
        data = r.json()
    except Exception:
        return f"[ERROR] Research non-JSON: {r.text[:300]}"

    response = data.get('response') or data.get('reply') or data.get('message') or ''
    if not response:
        return f"[ERROR] No response field. Keys: {list(data.keys())}"

    print(f"[research] Got {len(response)} chars")
    return response.strip()


AI_TOOLS = [
    {
        "name": "research",
        "description": "Call the private research assistant. USE for 'research X', 'do research', 'do more research on X', 'look up X'. Returns text response.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The research question"}
            },
            "required": ["query"]
        }
    }
]


def _gemini_call_with_tools(api_key, system, contents, model_name, max_rounds=5):
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
        "tools": [{"functionDeclarations": AI_TOOLS}]
    }

    for round_num in range(max_rounds):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=180
            )
        except Exception as e:
            print(f"[gemini-tools] FAILED: {e}")
            return f"[API ERROR] {e}"

        if r.status_code != 200:
            print(f"[gemini-tools] HTTP {r.status_code}: {r.text[:300]}")
            return f"[API ERROR] Gemini HTTP {r.status_code}"

        try:
            data = r.json()
            parts = data['candidates'][0]['content']['parts']
        except (KeyError, IndexError):
            return f"[API ERROR] Bad Gemini response"

        tool_calls = [p for p in parts if 'functionCall' in p]
        text_parts = [p.get('text', '') for p in parts if 'text' in p]

        if not tool_calls:
            return ''.join(text_parts)

        print(f"[agent] Round {round_num + 1}: {len(tool_calls)} tool call(s)")
        contents.append({"role": "model", "parts": parts})

        tool_responses = []
        for tc in tool_calls:
            fn = tc['functionCall']
            name = fn.get('name', '')
            args = fn.get('args', {})
            print(f"[agent]   -> {name}({str(args)[:100]})")

            if name == 'research':
                result = tool_research({}, '', args)
            else:
                result = f"[ERROR] Unknown tool: {name}"

            print(f"[agent]   <- {result[:150]}")
            tool_responses.append({
                "functionResponse": {"name": name, "response": {"result": result[:4000]}}
            })

        contents.append({"role": "user", "parts": tool_responses})
        payload['contents'] = contents

    return "[ERROR] Too many tool rounds"



def tool_buffer(creds, msg, extra):
    """Post to Buffer via GraphQL API. Requires personal API key from Buffer Settings -> API."""
    token = creds.get('api_key')
    channel_id = creds.get('channel_id')  # optional; if omitted, posts to first channel

    if not token:
        return "[ERROR] Buffer: api_key not configured (Settings -> API in Buffer)"
    if not (msg or '').strip():
        return "[ERROR] Buffer: no content to post"

    text = msg.strip()
    if len(text) > 280:
        text = text[:277] + '...'

    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on Post {
          id
          status
          channel { id name service }
        }
        ... on MutationError {
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "text": text,
            "saveToDraft": True,   # safest: creates a draft, user publishes from Buffer
        }
    }
    if channel_id:
        variables["input"]["channelId"] = channel_id

    try:
        r = requests.post(
            'https://api.buffer.com',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            json={"query": query, "variables": variables},
            timeout=20,
        )
    except requests.exceptions.Timeout:
        return "[ERROR] Buffer: timeout (20s)"
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Buffer: network: {e}"

    if r.status_code != 200:
        return f"[ERROR] Buffer {r.status_code}: {r.text[:300]}"

    try:
        data = r.json()
    except Exception:
        return f"[ERROR] Buffer: non-JSON response: {r.text[:200]}"

    if 'errors' in data:
        return f"[ERROR] Buffer GraphQL: {str(data['errors'])[:300]}"

    post = (data.get('data') or {}).get('createPost') or {}
    if 'message' in post:
        return f"[ERROR] Buffer: {post['message']}"
    post_id = post.get('id', '?')
    status = post.get('status', 'draft')
    return f"Buffer 200: {status} (id={post_id})"


def tool_zernio(creds, msg, extra):
    """Post to Zernio. Requires api_key (sk_...) and account_id from GET /v1/accounts."""
    token = creds.get('api_key')
    account_id = creds.get('account_id')

    if not token:
        return "[ERROR] Zernio: api_key not configured (starts with sk_)"
    if not account_id:
        return "[ERROR] Zernio: account_id not configured (get from GET /v1/accounts)"
    if not (msg or '').strip():
        return "[ERROR] Zernio: no content to post"

    text = msg.strip()

    try:
        r = requests.post(
            'https://zernio.com/api/v1/posts',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            json={
                'content': text,
                'publishNow': True,
                'platforms': [{'accountId': account_id}],
            },
            timeout=20,
        )
    except requests.exceptions.Timeout:
        return "[ERROR] Zernio: timeout (20s)"
    except requests.exceptions.RequestException as e:
        return f"[ERROR] Zernio: network: {e}"

    if r.status_code in (200, 201):
        try:
            data = r.json()
            post_id = data.get('_id') or data.get('id', '?')
            return f"Zernio {r.status_code}: posted (id={post_id})"
        except Exception:
            return f"Zernio {r.status_code}: posted"

    if r.status_code == 401:
        return "[ERROR] Zernio: 401 Unauthorized — check API key"
    if r.status_code == 409:
        return "[ERROR] Zernio: 409 duplicate content (same content posted within 24h)"
    return f"[ERROR] Zernio {r.status_code}: {r.text[:300]}"


TOOL_HANDLERS = {
    'discord':         tool_discord,
    'slack':           tool_slack,
    'telegram':        tool_telegram,
    'gmail-smtp':      tool_gmail_smtp,
    'github-issue':    tool_github_issue,
    'github-comment':  tool_github_comment,
    'notion':          tool_notion,
    'google-sheets':   tool_google_sheets,
    'twilio-sms':      tool_twilio_sms,
    'openai':          tool_openai,
    'gemini':          tool_gemini,
    'ollama':          tool_ollama,
    'stripe':          tool_stripe,
    'weather':         tool_weather,
    'coingecko':       tool_coingecko,
    'binance':         tool_binance,
    'newsapi':         tool_news,
    'rss':             tool_rss,
    'webhook':         tool_webhook,
    'http-custom':     tool_http_custom,
    'buffer':          tool_buffer,
    'zernio':          tool_zernio,
    'mqtt':            tool_mqtt_publish,
    # The 20th: 'telegram' counts twice in the "messaging" family; adding one more
    'pushover':        lambda c,m,e: _pushover(c,m),
    'research':       tool_research,
}

def _pushover(creds, msg):
    token, user = creds.get('app_token'), creds.get('user_key')
    if not (token and user): return "[ERROR] Pushover not configured"
    try:
        r = requests.post("https://api.pushover.net/1/messages.json",
                          data={"token": token, "user": user, "message": msg or "(empty)"},
                          timeout=10)
        return f"Pushover {r.status_code}"
    except Exception as e: return f"[ERROR] Pushover: {e}"

# ---------- Pipeline runner ----------

import subprocess
import tempfile
import shutil

def _ensure_node_binary():
    """
    On Vercel (serverless), there is no system Node.js.
    Extract the bundled node.gz into /tmp/node on first call.
    The file persists for the lifetime of the function instance.
    """
    import gzip as _gzip
    here = Path(__file__).parent
    archive = here / "nodejs" / "node.gz"
    target = Path("/tmp") / "node"

    if not archive.exists():
        print(f"[js] Node archive not found at {archive}")
        return None

    if not target.exists():
        try:
            with _gzip.open(archive, 'rb') as fin, open(target, 'wb') as fout:
                shutil.copyfileobj(fin, fout)
            os.chmod(target, 0o755)
            print(f"[js] Extracted bundled node -> {target}")
        except Exception as e:
            print(f"[js] Extraction failed: {e}")
            return None

    return str(target)


def run_js_code(user_code, input_value, timeout=30):
    """
    Execute JavaScript via Node.js subprocess with UTF-8 encoding.
    Uses an async IIFE so `await fetch(...)` works in the Code node.
    """
    node_exe = shutil.which("node")
    if not node_exe:
        node_exe = _ensure_node_binary()
    if not node_exe:
        return {"ok": False, "output": None,
                "error": "Node.js not found in PATH or bundled (expected nodejs/node.gz)"}

    template = r"""
const fs = require('fs');
const _input = fs.readFileSync(process.argv[2], 'utf-8');
let _output = _input;
function output(val) { _output = typeof val === 'string' ? val : JSON.stringify(val); }

// Auto-parse `input` into `data` so JS Code nodes can use either style.
let _jsonText = _input;
if (typeof _jsonText === 'string' && _jsonText.startsWith('HTTP ')) {
    const _ci = _jsonText.indexOf(':');
    if (_ci > 0) _jsonText = _jsonText.slice(_ci + 1).trim();
}
let data = null;
try {
    data = JSON.parse(_jsonText);
    if (data && typeof data.response === 'string') {
        try { data = JSON.parse(data.response); } catch (_) {}
    }
} catch (_) { data = null; }

const input = _input;
(async () => {
    try {
""" + user_code + r"""
        process.stdout.write(String(_output));
    } catch (err) {
        process.stderr.write("ERROR: " + (err && err.stack ? err.stack : String(err)));
        process.exit(1);
    }
})();
"""
    js_path = None
    in_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(template)
            js_path = tmp.name

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as inp:
            inp.write(str(input_value or ""))
            in_path = inp.name

        result = subprocess.run(
            [node_exe, js_path, in_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )

        if result.returncode != 0:
            err = (result.stderr or "").strip() or "Unknown JS error"
            return {"ok": False, "output": None, "error": err}
        return {"ok": True, "output": (result.stdout or "").strip(), "error": None}

    except subprocess.TimeoutExpired:
        return {"ok": False, "output": None, "error": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"ok": False, "output": None, "error": str(e)}
    finally:
        for p in (js_path, in_path):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass


def run_python_code(user_code, input_value, timeout=5):
    """
    Execute user-supplied Python. Provides `input` variable and `output()` helper.
    """
    template = user_code
    try:
        # Simple exec in a controlled namespace
        ns = {"input": input_value, "result": input_value}
        def output(val): ns["result"] = val
        ns["output"] = output
        exec(template, {"__builtins__": __builtins__}, ns)
        return {"ok": True, "output": str(ns.get("result", "")), "error": None}
    except Exception as e:
        return {"ok": False, "output": None, "error": str(e)}


def execute_workflow(nodes, extra_input=None):
    logs, final_data = [], None
    current_memory = str(extra_input) if extra_input is not None else ""
    print(f"\n--- EXECUTING (input: {str(extra_input)[:80]}) ---")
    for i, node in enumerate(nodes):
        node_type = node.get('type')
        node_data = node.get('data', {})
        print(f"  Node {i}: {node_type}")
        logs.append(f"Executing: {node_type}...")
        try:
            if node_type == 'webhook-input':
                logs.append(f"Webhook payload: {current_memory[:120] or '(empty)'}")

            elif node_type == 'market-data':
                raw = str(node_data.get('coin','bitcoin')).lower()
                sym = SYMBOL_MAP.get(raw, raw.upper())
                try:
                    r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}USDT", timeout=10)
                    p = r.json()
                    if 'price' in p:
                        current_memory = f"Current {sym} Price: ${float(p['price']):,.2f}"
                        logs.append(f"Success: {current_memory}")
                    else:
                        current_memory = f"[ERROR] Binance: {p.get('msg','unknown')}"
                        logs.append(current_memory)
                except Exception as e:
                    current_memory = f"[ERROR] Network: {e}"; logs.append(current_memory)

            elif node_type == 'filter':
                kw = node_data.get('keyword','Price')
                if kw.lower() in current_memory.lower():
                    current_memory = f"[VALIDATED] {current_memory}"
                    logs.append(f"Filter matched: {kw}")
                else:
                    current_memory = f"[REJECTED] {current_memory}"
                    logs.append(f"Filter failed: {kw}")

            elif node_type == 'math':
                op, val = node_data.get('op','multiply'), float(node_data.get('value',1))
                num = extract_number(current_memory)
                if num is not None:
                    res = {'multiply':num*val,'add':num+val,'subtract':num-val,
                           'divide':num/val if val else num}.get(op, num)
                    current_memory = f"Math({op} {val}): ${res:,.2f}"
                    logs.append(current_memory)
                else:
                    logs.append("Math: no number found")

            elif node_type == 'compare':
                op, th = node_data.get('operator','>'), float(node_data.get('threshold',0))
                num = extract_number(current_memory)
                if num is None:
                    logs.append("Compare: no number — stopping"); break
                passed = {'>':num>th,'<':num<th,'>=':num>=th,'<=':num<=th,'==':num==th}.get(op, False)
                if passed:
                    current_memory = f"[PASS {num} {op} {th}] {current_memory}"
                    logs.append("Compare passed")
                else:
                    logs.append(f"Compare failed: {num} not {op} {th}"); current_memory = None; break

            elif node_type == 'json-extract':
                path = node_data.get('path','')
                text = current_memory
                if text.startswith('HTTP '):
                    parts = text.split(':', 1)
                    if len(parts) > 1: text = parts[1].strip()
                try:
                    obj = json.loads(text)
                    for key in path.split('.'):
                        obj = obj[key] if isinstance(obj, dict) else obj[int(key)]
                    current_memory = str(obj)
                    logs.append(f"Extracted {path}: {current_memory}")
                except Exception as e:
                    logs.append(f"[ERROR] JSON extract: {e}"); current_memory = None; break

            elif node_type == 'tool':
                service = node_data.get('service', 'http-custom')
                handler = TOOL_HANDLERS.get(service)
                if not handler:
                    current_memory = f"[ERROR] Unknown tool: {service}"; logs.append(current_memory)
                else:
                    creds = load_creds(service) or {}
                    # Per-node overrides for one-off configs
                    for k, v in (node_data.get('config') or {}).items():
                        if v: creds[k] = v
                    
                    # SANITIZE MESSAGE: strip any template syntax
                    raw_msg = node_data.get('message') or ''
                    if raw_msg and ('{{' in raw_msg or '${' in raw_msg):
                        logs.append(f"[WARN] Stripping template from tool message: {raw_msg[:50]}")
                        raw_msg = ''
                    
                    msg = raw_msg or current_memory
                    result = handler(creds, msg, node_data.get('extra') or {})
                    current_memory = result
                    logs.append(result)


            elif node_type == 'delay':
                secs = int(node_data.get('seconds', 5))
                if secs < 1: secs = 1
                if secs > 300: secs = 300
                logs.append(f"Delaying {secs}s...")
                time.sleep(secs)
                logs.append(f"Delay complete ({secs}s)")

            elif node_type == 'code':
                lang = node_data.get('lang', 'javascript')
                code = node_data.get('code', '').strip()
                if not code:
                    logs.append("Code node: no code provided — passing through")
                else:
                    runner = run_js_code if lang == 'javascript' else run_python_code
                    res = runner(code, current_memory)
                    if res['ok']:
                        current_memory = res['output']
                        logs.append(f"Code ({lang}): {current_memory[:200]}")
                    else:
                        current_memory = f"[CODE ERROR] {res['error']}"
                        logs.append(current_memory)

            elif node_type == 'http-request':
                url = node_data.get('url','').strip()
                method = node_data.get('method','GET').upper()
                body = node_data.get('body')
                headers = node_data.get('headers', {})
                if not url:
                    current_memory = "[ERROR] HTTP: no URL"; logs.append(current_memory)
                else:
                    try:
                        kwargs = {"timeout": 30, "headers": headers}
                        if method in ('POST','PUT','PATCH'):
                            if body:
                                try:
                                    kwargs["json"] = json.loads(body) if isinstance(body, str) else body
                                except Exception:
                                    kwargs["json"] = body
                            else:
                                kwargs["json"] = {"content": current_memory}
                        r = requests.request(method, url, **kwargs)
                        # ---- Detect binary responses (audio, image, etc.) ----
                        content_type = r.headers.get('Content-Type', '')
                        if 'audio/' in content_type or 'image/' in content_type or 'octet-stream' in content_type:
                            ext = 'wav' if 'wav' in content_type else ('mp3' if 'mp3' in content_type else ('png' if 'png' in content_type else 'bin'))
                            filename = f"output_{uuid.uuid4().hex[:8]}.{ext}"
                            filepath = Path(filename)
                            filepath.write_bytes(r.content)
                            current_memory = str(filepath.absolute())
                            logs.append(f"HTTP {r.status_code}: saved binary to {filename} ({len(r.content)} bytes)")
                        else:
                            full_text = r.text
                            preview = full_text[:250] + ('...' if len(full_text) > 250 else '')
                            current_memory = f"HTTP {r.status_code}: {full_text}"
                            logs.append(f"HTTP {r.status_code}: {preview}")
                    except Exception as e:
                        current_memory = f"[ERROR] HTTP: {e}"; logs.append(current_memory)
            elif node_type == 'console':
                final_data = current_memory
                logs.append(f"Output: {current_memory}")

        except Exception as e:
            logs.append(f"[ERROR] {node_type}: {e}")

    print(f"  Done. Result: {final_data}")
    return {"status":"success","logs":logs,"data":final_data}




PUBLIC_DIR = Path(__file__).parent / 'public'

@app.route('/')
def index():
    return send_from_directory(str(PUBLIC_DIR), 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(str(PUBLIC_DIR), path)




@app.route('/run', methods=['POST','OPTIONS'])
def run_workflow():
    if request.method == 'OPTIONS': return make_response("", 204)
    data = request.json or {}
    nodes = data.get('nodes', [])
    wf = data.get('workflow_name','unnamed')
    if not nodes: return jsonify({"status":"error","logs":["No nodes"],"data":None}), 400
    result = execute_workflow(nodes)
    log_execution(wf, "manual", result)
    return jsonify(result)

@app.route('/workflows', methods=['GET'])
def list_all_workflows(): return jsonify({"workflows": list_workflows()})

@app.route('/workflows/<name>', methods=['GET','PUT','DELETE'])
def wf_by_name(name):
    if request.method == 'GET':
        wf = load_workflow(name)
        return jsonify(wf) if wf else (jsonify({"error":"not found"}), 404)
    if request.method == 'PUT':
        wf = request.json
        if not wf or 'nodes' not in wf: return jsonify({"error":"invalid"}), 400
        save_workflow(name, wf); return jsonify({"status":"saved","name":name})
    delete_workflow(name)
    return jsonify({"status":"deleted"})

@app.route('/webhook/<name>', methods=['POST','GET','OPTIONS'])
def webhook_trigger(name):
    if request.method == 'OPTIONS': return make_response("", 204)
    wf = load_workflow(name)
    if not wf: return jsonify({"error":f"workflow '{name}' not found"}), 404
    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        initial = json.dumps(payload) if payload else None
    else:
        initial = str(dict(request.args)) if request.args else None
    print(f"\nWEBHOOK: {name}")
    result = execute_workflow(wf.get('nodes', []), extra_input=initial)
    log_execution(name, "webhook", result)
    return jsonify({"status":"triggered","workflow":name,"result":result.get('data'),"logs":result.get('logs')})

def _schedule_loop(name, interval, stop_event):
    while not stop_event.is_set():
        wf = load_workflow(name)
        if wf:
            try:
                result = execute_workflow(wf.get('nodes', []))
                log_execution(name, "schedule", result)
            except Exception as e:
                print(f"Scheduled run failed: {e}")
        if stop_event.wait(timeout=interval): break

@app.route('/schedule/<name>', methods=['POST','DELETE'])
def schedule(name):
    if request.method == 'DELETE':
        with _scheduler_lock: s = _schedulers.pop(name, None)
        if s: s['stop_event'].set(); return jsonify({"status":"stopped","workflow":name})
        return jsonify({"error":"not scheduled"}), 404
    data = request.json or {}
    interval = int(data.get('interval_seconds', 60))
    if interval < 5: return jsonify({"error":"min 5s"}), 400
    if not load_workflow(name): return jsonify({"error":f"'{name}' not found"}), 404
    with _scheduler_lock:
        if name in _schedulers: _schedulers[name]['stop_event'].set()
        ev = threading.Event()
        t = threading.Thread(target=_schedule_loop, args=(name, interval, ev), daemon=True)
        _schedulers[name] = {'thread': t, 'stop_event': ev, 'interval': interval}
        t.start()
    return jsonify({"status":"scheduled","workflow":name,"interval_seconds":interval})

@app.route('/schedules', methods=['GET'])
def list_schedules():
    return jsonify({"schedules":[{"name":k,"interval_seconds":v['interval']}
                                  for k,v in _schedulers.items() if v['thread'].is_alive()]})

@app.route('/executions/<name>', methods=['GET'])
def get_executions(name):
    return jsonify({"executions": read_execution_log(name, int(request.args.get('limit',50)))})

# ---------- Credentials API ----------
@app.route('/credentials', methods=['GET'])
def list_creds():
    return jsonify({"configured": list_configured_creds()})

@app.route('/credentials/<service>', methods=['GET','PUT','DELETE'])
def creds_service(service):
    if request.method == 'GET':
        c = load_creds(service)
        return jsonify(c) if c else (jsonify({"error":"not configured"}), 404)
    if request.method == 'PUT':
        save_creds(service, request.json or {})
        return jsonify({"status":"saved","service":service})
    delete_creds(service)
    return jsonify({"status":"deleted"})




@app.route('/ai-models', methods=['GET'])
def ai_models():
    """List available models and which ones are configured."""
    gemini_creds = load_creds('gemini')
    ollama_creds = load_creds('ollama')
    
    has_gemini = bool(gemini_creds and gemini_creds.get('api_key'))
    has_ollama = bool(ollama_creds and ollama_creds.get('api_key'))
    
    models = []
    for key, cfg in AVAILABLE_MODELS.items():
        available = False
        if cfg['provider'] == 'gemini':
            available = has_gemini
        elif cfg['provider'] == 'ollama':
            available = has_ollama
        models.append({
            'key': key,
            'label': cfg['label'],
            'provider': cfg['provider'],
            'available': available
        })
    
    return jsonify({'models': models})


































@app.route('/ai-chat', methods=['POST', 'OPTIONS'])
def ai_chat():
    """Simple Gemini chat proxy — no credentials needed on the client."""
    if request.method == 'OPTIONS':
        return make_response("", 204)

    data = request.json or {}
    message = (data.get('message') or '').strip()
    history = data.get('history') or []
    
    system = data.get('system') or (
        "You are the Workflow Pro Architect. Concise, execution-focused.\n\n"

        "### RULE ZERO - RESEARCH CALLS research() DIRECTLY ###\n"
        "You have ONE tool: `research(query)` - calls private research assistant.\n\n"

        "CALL research() DIRECTLY (do NOT build workflow) when user says:\n"
        "  - 'do research' / 'do research on X' / 'do more research on X'\n"
        "  - 'research X' / 'look up X' / 'what is X' / 'find me X'\n"
        "  - 'ask my assistant about X' / 'search for X'\n"
        "  - Any research request WITHOUT email/send/post/discord/slack target\n\n"

        "When calling research():\n"
        "  1. Call research(query='topic')\n"
        "  2. Read result\n"
        "  3. Answer user with TEXT\n"
        "  4. DO NOT output JSON. DO NOT build workflow.\n\n"

        "BUILD WORKFLOW ONLY IF user says:\n"
        "  - 'research X and email me'\n"
        "  - 'send the research to discord/slack/telegram'\n"
        "  - 'email me a summary of X'\n\n"

        "TEST: ANSWER only? call research() directly. DELIVERY needed? build workflow.\n\n"

        "### BUILD WORKFLOWS\n"
        "Format: a JSON array of nodes. Each node is {type: string, data: OBJECT}.\n"
        "`data` is ALWAYS an object with named keys — NEVER a raw string.\n\n"

        "Node schemas (exact key names):\n"
        "  trigger/webhook    data: {}                             (no keys)\n"
        "  action/http        data: {url: string, method: string, body?: string, headers?: object}\n"
        "  logic/code         data: {code: string, lang: \"javascript\"}\n"
        "                     ← data.code contains the JS source as a STRING,\n"
        "                       data.lang is the language, usually \"javascript\".\n"
        "  tool/integration   data: {service: string, message: string}\n"
        "                     ← service = one of: gmail-smtp, discord, slack, telegram,\n"
        "                       notion, google-sheets, twilio-sms, webhook, http-custom.\n"
        "                       message = \"\" (empty — auto-inherits previous output).\n"
        "  output/console     data: {}                             (no keys)\n\n"

        "WRONG examples (do NOT emit):\n"
        "  {\"type\": \"logic/code\", \"data\": \"...JS string...\"}             ← data must be object, not string\n"
        "  {\"type\": \"tool/integration\", \"data\": {\"integration\": \"email\", ...}}  ← must use `service`, not `integration`\n"
        "  {\"type\": \"tool/integration\", \"data\": {\"to\": \"...\", \"subject\": \"...\"}}    ← only `service` and `message` allowed\n\n"

        "CORRECT example for a Code node:\n"
        "  {\"type\": \"logic/code\",\n"
        "   \"data\": {\n"
        "     \"lang\": \"javascript\",\n"
        "     \"code\": \"if (!data || !data.jobs) { output('[ERROR] no jobs'); } else { output(data.jobs.slice(0,3).map(function(j){return j.title;}).join('\\\\n')); }\"\n"
        "   }}\n\n"

        "CORRECT example for an email tool node (gmail-smtp):\n"
        "  {\"type\": \"tool/integration\",\n"
        "   \"data\": {\"service\": \"gmail-smtp\", \"message\": \"\"}}\n\n"

        "For research + delivery:\n"
        "  url: '/api/remote_chat'\n"
        "  method: 'POST'\n"
        "  body: JSON string with message/session_id/voice\n"
        "  headers: JSON string with Content-Type\n"
        "Response shape: {\"status\":\"success\", \"response\":\"<inner-json-string>\"}\n"
        "  → The Code node's `data` variable is auto-flattened to the inner payload,\n"
        "    so use `data.jobs`, `data.status`, NOT `data.response.jobs`.\n\n"

        "### CODE NODES (JavaScript)\n"
        "Every JS Code node runs in a sandbox with THREE variables:\n"
        "  - input:  STRING — raw text from the previous node (may start with 'HTTP 200: ')\n"
        "  - data:   OBJECT|null — input auto-parsed as JSON. If input looked like\n"
        "            {status, response}, the runtime recursively parses `.response`.\n"
        "            So `data` always ends up as the INNER payload (e.g. {jobs:[...]}).\n"
        "  - output: FUNCTION — call output(value) to pass a result to the next node.\n\n"

        "HARD RULES for JS Code nodes:\n"
        "  1. NO require(), fs, path, process, Buffer, or any Node.js builtin.\n"
        "     Allowed globals: JSON, Math, Date, String, Array, Object, RegExp,\n"
        "                     Promise, console.log (goes to stderr).\n"
        "  2. NO `return` at top level — use `output(result)` instead.\n"
        "  3. `data` may be null if input isn't JSON — always guard with:\n"
        "     if (!data) { output('[ERROR] no JSON'); } else { ... }\n"
        "  4. EVERY code node MUST end with output(...).\n"
        "  5. Do NOT use `data.response.jobs` — use `data.jobs` (already flattened).\n\n"

        "CANONICAL EXAMPLE — extract jobs from Remotive and format for email:\n"
        "```javascript\n"
        "if (!data || !data.jobs) {\n"
        "  output('[ERROR] No jobs in response');\n"
        "} else {\n"
        "  const top3 = data.jobs.slice(0, 3);\n"
        "  const lines = top3.map(function(j) {\n"
        "    return '• ' + (j.title || 'Unknown') + ' – ' + (j.company_name || 'Unknown') + '\\n' +\n"
        "           '  Location: ' + (j.candidate_required_location || 'Unknown') + '\\n' +\n"
        "           '  URL: ' + (j.url || '');\n"
        "  });\n"
        "  output(lines.join('\\n\\n'));\n"
        "}\n"
        "```\n\n"

        "When the previous node outputs JSON via HTTP request, `input` looks like\n"
        "'HTTP 200: {...}' and `data` is the parsed object. You do NOT need to parse.\n\n"

        "### KNOWN-WORKING APIs (use these; do NOT invent others)\n"
        "  Bitcoin price:  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\n"
        "                  returns {bitcoin:{usd:97500}}\n"
        "                  use: data.bitcoin.usd\n"
        "                  THIS IS THE ONLY reliable Bitcoin API from Vercel.\n"
        "  Crypto prices:  https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd\n"
        "                  returns {ethereum:{usd:3400}}\n"
        "                  use: data.ethereum.usd\n"
        "  Remote jobs:    https://remotive.com/api/remote-jobs\n"
        "                  returns {jobs:[...]}\n"
        "                  use: data.jobs\n"
        "  Weather:        https://wttr.in/CITY?format=j1\n"
        "                  use: data.current_condition[0].temp_C\n"
        "  GitHub issues:  https://api.github.com/repos/OWNER/REPO/issues?state=open&per_page=5\n"
        "                  returns an ARRAY\n"
        "                  use: Array.isArray(data) ? data : []\n"
        "  RSS example:    https://news.ycombinator.com/rss\n"
        "                  returns XML - data will be NULL\n"
        "                  use: input (raw string) with RegExp\n"
        "  News:           https://newsapi.org/v2/top-headlines?country=us&apiKey=KEY\n"
        "                  use: data.articles\n\n"

        "DEPRECATED URLs - NEVER emit these:\n"
        "  - api.coindesk.com        (DNS dead since 2024)\n"
        "  - api.binance.com         (HTTP 451 from Vercel US East)\n"
        "  - remotive.io             (use remotive.com)\n"
        "  - api.cryptocompare.com   (requires paid key)\n\n"

        "If the user asks for Bitcoin price, ALWAYS use CoinGecko:\n"
        "  https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd\n\n"


        "### TOOLS\n"
        "tool/integration message field MUST be empty string \"\" — the tool node\n"
        "automatically uses the previous node's output as its message.\n"
        "email/discord/slack/sheets -> tool/integration\n"
        "APIs -> action/http"
    )
    
    
    
    
    
    
    

    if not message:
        return jsonify({"error": "no message"}), 400

# SIMPLE URL INJECTION
    current_urls = re.findall(r'https?://[^\s\)\],]+', message)
    if current_urls:
        chosen_url = current_urls[0].rstrip('.,;:!?)]>')
        print(f"[inject] User pasted URL: {chosen_url}")
        message = f"[USER PROVIDED URL]\n{chosen_url}\n[END URL]\n\nUser request: {message}"

    # Load Gemini API key from credentials
    creds = load_creds('gemini')
    if not creds or not creds.get('api_key'):
        return jsonify({
            "error": "Gemini API key not configured. Go to Credentials → Google Gemini → Configure."
        }), 400

    try:

        # Load memory context and prepend to system prompt
        try:
            memory_context = memory_build_context()
            if memory_context:
                system = system + memory_context
                print(f"[ai-chat] Loaded memory context ({len(memory_context)} chars)")
        except Exception as mem_err:
            print(f"[ai-chat] Memory load failed (non-fatal): {mem_err}")

        # Save the user's message to memory
        try:
            memory_save_message("user", message)
        except Exception as mem_err:
            print(f"[ai-chat] Memory save failed: {mem_err}")

        # Get selected model from request
        model_key = (data.get('model') or 'gemini-flash').strip()
        model_config = AVAILABLE_MODELS.get(model_key)
        
        if not model_config:
            # Unknown model — fall back to gemini-flash
            model_config = AVAILABLE_MODELS['gemini-flash-25']
            model_key = 'gemini-flash-25'
        
        provider = model_config['provider']
        model_name = model_config['model']
        
        print(f"[ai-chat] Requested model: {model_key} → provider={provider}, model={model_name}")
        
        # Build conversation
        contents = []
        for h in history[-10:]:
            role = h.get('role', 'user')
            text = h.get('text', '')
            if not text:
                continue
            contents.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": text}]
            })
        contents.append({"role": "user", "parts": [{"text": message}]})
        
        # Route to provider
        if provider == 'gemini':
            creds_g = load_creds('gemini')
            if not creds_g or not creds_g.get('api_key'):
                return jsonify({"error": "Gemini API key not configured. Go to Credentials."}), 400
            # Detect if user is asking to build a workflow (needs web search)
            build_keywords = ['build', 'generate', 'workflow', 'create', 'make']
            use_search = False
            
            print(f"[ai-chat] Google Search grounding: {use_search}")
            
            reply = _gemini_call_with_tools(
                api_key=creds_g['api_key'],
                system=system,
                contents=contents,
                model_name=model_name
            )
            if reply:
                # Save AI reply to memory
                try:
                    memory_save_message("bot", reply.strip())
                except Exception:
                    pass
                return jsonify({"reply": reply.strip(), "model": model_key})
            # Fallback to Ollama on Gemini failure
            print("[ai-chat] Gemini failed, trying Ollama fallback")
            fallback = _ollama_call(message, system)
            if fallback:
                return jsonify({"reply": fallback.strip(), "model": 'ollama-gpt', "fallback": True})
            return jsonify({"error": "Gemini failed and no Ollama fallback available"}), 500
        
        elif provider == 'ollama':
            # Gemma 4 doesn't support function calling, so the backend
            # detects research requests and calls the tool directly.
            # Then feeds the result back to Ollama for the natural answer.
            
            research_keywords = [
                'research', 'do research', 'look up', 'find out',
                'what is', 'what are', 'tell me about', 'search for',
                'investigate', 'explore', 'api list', 'list apis',
            ]
            msg_lc = message.lower()
            wants_research = any(kw in msg_lc for kw in research_keywords)
            
            # Check if this is a delivery request (research AND email/discord)
            delivery_keywords = ['email', 'send to', 'post to', 'discord', 'slack', 'telegram', 'sheets', 'notion']
            wants_delivery = any(kw in msg_lc for kw in delivery_keywords)
            
            if wants_research and not wants_delivery:
                # Backend calls research tool directly
                print(f"[ollama-research] Detected research request")
                research_result = tool_research({}, message, {})
                print(f"[ollama-research] Got {len(research_result)} chars")
                
                # Feed result to Ollama
                augmented_message = (
                    f"User asked: {message}\n\n"
                    f"Research result:\n{research_result}\n\n"
                    f"Answer the user's question using the research result above. "
                    f"Be concise and direct. Do not mention the research process."
                )
                
                reply = _ollama_call(augmented_message, system, model_override=model_name)
            else:
                reply = _ollama_call(message, system, model_override=model_name)
            
            if reply:
                return jsonify({"reply": reply.strip(), "model": model_key})
            return jsonify({"error": f"Ollama failed for model {model_name}"}), 500
        
        return jsonify({"error": f"Unknown provider: {provider}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500









@app.route('/api/remote_chat', methods=['POST', 'OPTIONS'])
def remote_chat():
    if request.method == 'OPTIONS':
        return make_response("", 204)

    data = request.json or {}
    user_msg = data.get('message', '').strip()
    session_id = data.get('session_id', 'default_research')

    if not user_msg:
        return jsonify({"error": "No message"}), 400

    try:
        creds = load_creds('gemini')
        if not creds or not creds.get('api_key'):
            return jsonify({"error": "Gemini key not configured"}), 400

        research_system = (
            "You are a research assistant. Answer questions thoroughly and factually.\n"
            "Include specific API names, URLs, and details when asked.\n"
            "Do NOT output JSON workflows. Just answer in plain text."
        )

        contents = [{"role": "user", "parts": [{"text": user_msg}]}]

        reply = _gemini_call(
            api_key=creds['api_key'],
            system=research_system,
            contents=contents,
            model_name='gemini-2.5-flash',
            use_search=True
        )

        if not reply:
            return jsonify({"error": "Research failed"}), 500

        return jsonify({
            "status": "success",
            "response": reply.strip(),
            "session_id": session_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ai-memory/facts', methods=['GET', 'PUT'])
def ai_memory_facts():
    if request.method == 'GET':
        return jsonify(memory_load_facts())
    data = request.json or {}
    for k, v in data.items():
        memory_save_fact(k, v)
    return jsonify({"ok": True, "facts": memory_load_facts()})

@app.route('/ai-memory/recent', methods=['GET'])
def ai_memory_recent():
    hours = int(request.args.get('hours', 24))
    limit = int(request.args.get('limit', 50))
    return jsonify({"messages": memory_recent(hours, limit)})

@app.route('/ai-memory/stats', methods=['GET'])
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
    })

@app.route('/ai-memory/clear', methods=['POST'])
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
    return jsonify({"ok": True, "removed_files": removed})

# ═══════════════════════════════════════════════════════════════
# CATCH-UP DISPATCHER
# Runs a scheduled workflow whenever its scheduled time has
# passed since last_run_at — even if the dispatcher woke late.
# ═══════════════════════════════════════════════════════════════

def _cron_matches_minute(cron_expr, dt):
    """Check if cron expression matches the given minute (UTC)."""
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False

        def match_field(field, value):
            if field == '*':
                return True
            for item in field.split(','):
                if '/' in item:
                    base, step = item.split('/')
                    step = int(step)
                    if base == '*':
                        if value % step == 0:
                            return True
                    elif '-' in base:
                        lo, hi = base.split('-')
                        if int(lo) <= value <= int(hi) and (value - int(lo)) % step == 0:
                            return True
                elif '-' in item:
                    lo, hi = item.split('-')
                    if int(lo) <= value <= int(hi):
                        return True
                elif int(item) == value:
                    return True
            return False

        minute, hour, day, month, weekday = parts
        cron_wd = (dt.weekday() + 1) % 7

        return (
            match_field(minute, dt.minute) and
            match_field(hour, dt.hour) and
            match_field(day, dt.day) and
            match_field(month, dt.month) and
            match_field(weekday, cron_wd)
        )
    except Exception as e:
        print("[cron] parse error '{}': {}".format(cron_expr, e))
        return False


def _find_most_recent_slot(cron_expr, now):
    """Scan backwards from now and return the most recent matching minute.
    Returns None if no slot found within 40 days.
    """
    from datetime import timedelta
    current = now.replace(second=0, microsecond=0)
    max_iterations = 60 * 24 * 40
    iterations = 0
    while iterations < max_iterations:
        if _cron_matches_minute(cron_expr, current):
            return current
        current -= timedelta(minutes=1)
        iterations += 1
    return None


@app.route('/cron/tick', methods=['POST', 'GET'])
def cron_tick():
    """Catch-up dispatcher.

    For each workflow with mode=scheduled:
      1. Find the most recent scheduled slot (<= now)
      2. If that slot is AFTER last_run_at → we missed it → run now
      3. Otherwise → already ran for that slot → skip
    """
    from datetime import datetime as _dt, timedelta
    now_utc = _dt.utcnow().replace(second=0, microsecond=0)

    # Load all workflows
    if USE_DB:
        rows = _db_all("SELECT name, payload FROM workflows")
        all_wfs = [(r["name"], r["payload"] or {}) for r in rows]
    else:
        all_wfs = []
        for p in DATA_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                all_wfs.append((p.stem, data))
            except Exception:
                continue

    ran, skipped, errors = [], [], []

    for name, payload in all_wfs:
        if payload.get("mode") != "scheduled":
            continue
        schedule = (payload.get("schedule") or "").strip()
        if not schedule:
            continue

        # Parse last_run_at (default: now - 24h so first tick catches today's slot)
        last_run_str = payload.get("last_run_at")
        if last_run_str:
            try:
                last_run = _dt.fromisoformat(last_run_str.replace("Z", ""))
            except Exception:
                last_run = now_utc - timedelta(hours=24)
        else:
            last_run = now_utc - timedelta(hours=24)

        # Find most recent scheduled slot
        slot = _find_most_recent_slot(schedule, now_utc)
        if slot is None:
            skipped.append(name)
            continue

        # Run if that slot is AFTER last_run (we haven't run for it yet)
        if last_run < slot:
            try:
                wf = load_workflow(name)
                result = execute_workflow(wf.get("nodes", []))
                log_execution(name, "cron", result)

                # Update last_run_at
                wf_payload = wf or {}
                wf_payload["last_run_at"] = now_utc.isoformat() + "Z"
                save_workflow(name, wf_payload)

                delay = int((now_utc - slot).total_seconds() / 60)
                ran.append({
                    "name": name,
                    "slot": slot.isoformat() + "Z",
                    "delay_minutes": delay,
                })
                print("[cron] ran {} (slot {}, {}min late)".format(
                    name, slot.strftime("%Y-%m-%d %H:%M"), delay))
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
                print("[cron] error {}: {}".format(name, e))
        else:
            skipped.append(name)

    return jsonify({
        "checked_at": now_utc.isoformat() + "Z",
        "ran": ran,
        "skipped": skipped,
        "errors": errors,
    })


if __name__ == '__main__':
    print("\n=======================================")
    print("WORKFLOW PRO ENGINE v5.0 — 20 TOOLS")
    print("Dashboard: http://localhost:10000")
    print("Webhook:   POST /webhook/<name>")
    print("Schedule:  POST /schedule/<name>")
    print("Credentials: PUT /credentials/<service>")
    print("=======================================\n")
    app.run(host='0.0.0.0', port=10000, debug=False, threaded=True)
