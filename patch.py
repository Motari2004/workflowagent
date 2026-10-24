import os, shutil, sys, re

SERVER = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\server.py'
if not os.path.exists(SERVER):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(SERVER, SERVER + '.backup_merge')
print("Backed up\n")

with open(SERVER, 'r', encoding='utf-8') as f:
    code = f.read()

old = '''@app.route('/workflows/<name>', methods=['GET','PUT','DELETE'])
def wf_by_name(name):
    if request.method == 'GET':
        wf = load_workflow(name)
        return jsonify(wf) if wf else (jsonify({"error":"not found"}), 404)
    if request.method == 'PUT':
        wf = request.json
        if not wf or 'nodes' not in wf: return jsonify({"error":"invalid"}), 400
        save_workflow(name, wf); return jsonify({"status":"saved","name":name})
    delete_workflow(name)
    return jsonify({"status":"deleted"})'''

new = '''@app.route('/workflows/<name>', methods=['GET','PUT','DELETE'])
def wf_by_name(name):
    if request.method == 'GET':
        wf = load_workflow(name)
        return jsonify(wf) if wf else (jsonify({"error":"not found"}), 404)
    if request.method == 'PUT':
        wf = request.json
        if not wf or 'nodes' not in wf:
            return jsonify({"error":"invalid"}), 400
        
        # Merge preserve: keep mode/schedule/last_run_at if not in incoming payload
        existing = load_workflow(name) or {}
        if 'mode' not in wf:
            wf['mode'] = existing.get('mode', 'once')
        if 'schedule' not in wf:
            wf['schedule'] = existing.get('schedule', '')
        if 'last_run_at' not in wf:
            wf['last_run_at'] = existing.get('last_run_at')
        
        save_workflow(name, wf)
        return jsonify({"status":"saved","name":name})
    delete_workflow(name)
    return jsonify({"status":"deleted"})'''

if old in code:
    code = code.replace(old, new, 1)
    print("OK — PUT handler now merges mode/schedule")
else:
    print("FAIL — PUT handler pattern not matched")
    # Try regex
    pattern = re.compile(
        r"@app\.route\('/workflows/<name>',\s*methods=\['GET','PUT','DELETE'\]\)[\s\S]*?return jsonify\(\{\"status\":\"deleted\"\}\)",
        re.DOTALL
    )
    if pattern.search(code):
        code = pattern.sub(new, code, count=1)
        print("OK — PUT handler replaced (regex)")

with open(SERVER, 'w', encoding='utf-8') as f:
    f.write(code)

try:
    compile(open(SERVER, 'r', encoding='utf-8').read(), SERVER, 'exec')
    print("Compiles OK")
except SyntaxError as e:
    print("FAIL line {}: {}".format(e.lineno, e.msg))
    shutil.copy(SERVER + '.backup_merge', SERVER)
    sys.exit(1)

print("\nNext: git add server.py && git commit -m 'Merge preserve mode/schedule on PUT' && git push")