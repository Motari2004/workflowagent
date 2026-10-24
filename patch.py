import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_sched_isolate')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("File: {} chars".format(len(html)))
changes = 0

# ═══════════════════════════════════════════════════════════════
# Replace openScheduleModal with an isolated version:
#   - captures workflow name at open time
#   - disables buttons while an operation is running
#   - never reads stale DOM after modal is open
#   - verifies name before every PUT
# ═══════════════════════════════════════════════════════════════
print("[1] Rewriting openScheduleModal with name isolation...")

# Find the whole function
old_fn_pattern = re.compile(
    r"async function openScheduleModal\(\) \{[\s\S]*?\n\}\n\nfunction updateScheduleBadge",
    re.DOTALL
)

new_fn = '''async function openScheduleModal() {
    // ── Capture the workflow name ONCE. Never read DOM again during the modal. ──
    let capturedName = document.getElementById('workflowName').value.trim();
    if (document.getElementById('workflowInputContainer').style.display === 'none') {
        capturedName = document.getElementById('currentLoadedName').textContent.trim();
    }
    if (!capturedName) { toast('Save or name the workflow first', 'error'); return; }
    
    // Save the canvas first (this uses the canvas state, not the modal)
    const saved = await saveCurrentWorkflow();
    if (!saved) { toast('Could not save workflow first', 'error'); return; }
    
    // Re-fetch — the save may have auto-named or adjusted
    let currentMode = 'once', currentSchedule = '';
    try {
        const r = await fetch(`/workflows/${encodeURIComponent(capturedName)}`);
        if (r.ok) {
            const d = await r.json();
            currentMode = d.mode || 'once';
            currentSchedule = d.schedule || '';
        }
    } catch (_) {}
    
    // Parse existing cron to 12-hour time
    let initHour12 = 9, initMin = 0, initAmPm = 'AM', hasSchedule = currentMode === 'scheduled' && currentSchedule;
    if (hasSchedule) {
        const parts = currentSchedule.trim().split(/\\s+/);
        if (parts.length === 5) {
            const min = parseInt(parts[0]) || 0;
            let hour24 = parseInt(parts[1]) || 9;
            initMin = min;
            if (hour24 === 0) { initHour12 = 12; initAmPm = 'AM'; }
            else if (hour24 === 12) { initHour12 = 12; initAmPm = 'PM'; }
            else if (hour24 < 12) { initHour12 = hour24; initAmPm = 'AM'; }
            else { initHour12 = hour24 - 12; initAmPm = 'PM'; }
        }
    }
    
    // Build modal
    document.querySelectorAll('.modal-overlay').forEach(m => m.remove());
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    
    let hourOpts = '';
    for (let h = 1; h <= 12; h++) {
        hourOpts += `<option value="${h}" ${h === initHour12 ? 'selected' : ''}>${h}</option>`;
    }
    let minOpts = '';
    for (let m = 0; m < 60; m += 5) {
        const mm = String(m).padStart(2, '0');
        minOpts += `<option value="${m}" ${m === initMin ? 'selected' : ''}>${mm}</option>`;
    }
    
    const timeDisplay = hasSchedule
        ? `${initHour12}:${String(initMin).padStart(2,'0')} ${initAmPm} (UTC) daily`
        : 'not scheduled';
    
    overlay.innerHTML = `
        <div class="modal" style="width: 480px;">
            <h2 style="margin-top:0; font-size:16px; display:flex; align-items:center; gap:8px;">
                <i class="fas fa-clock text-blue-400"></i> Schedule "<span id="modalWorkflowName">${capturedName}</span>"
            </h2>
            <p style="font-size:12px; color:#94a3b8; margin-bottom:20px; line-height:1.5;">
                Runs <strong>once per day</strong> at the time you set below. Catch-up handles missed slots.
            </p>
            
            <div style="margin-bottom:8px;">
                <label style="display:block; font-size:11px; color:#94a3b8; text-transform:uppercase; margin-bottom:8px; letter-spacing:0.05em;">Daily Run Time (UTC)</label>
                <div style="display:flex; gap:8px; align-items:center;">
                    <select id="modalHour" class="pro-input" style="width:90px; height:42px; font-size:16px; text-align:center; padding:0;">
                        ${hourOpts}
                    </select>
                    <span style="font-size:20px; color:#64748b; font-weight:600;">:</span>
                    <select id="modalMin" class="pro-input" style="width:90px; height:42px; font-size:16px; text-align:center; padding:0;">
                        ${minOpts}
                    </select>
                    <select id="modalAmPm" class="pro-input" style="width:100px; height:42px; font-size:14px; text-align:center; padding:0;">
                        <option value="AM" ${initAmPm === 'AM' ? 'selected' : ''}>AM</option>
                        <option value="PM" ${initAmPm === 'PM' ? 'selected' : ''}>PM</option>
                    </select>
                </div>
                <div style="font-size:11px; color:#475569; margin-top:6px;">
                    Current: <span id="modalPreview" style="color:#60a5fa;">${timeDisplay}</span>
                </div>
            </div>
            
            <div style="font-size:10px; color:#64748b; margin-top:16px; padding:10px; background:rgba(148,163,184,0.05); border-radius:6px; line-height:1.6;">
                <strong style="color:#94a3b8;">Common times:</strong><br>
                Morning reports → 9:00 AM • Noon check → 12:00 PM<br>
                Evening summary → 6:00 PM • Midnight → 12:00 AM
            </div>
            
            <div class="modal-buttons" style="justify-content: space-between; margin-top:24px;">
                <button class="modal-btn secondary" id="modalRemoveBtn" style="display:${hasSchedule ? 'block' : 'none'};">Stop Schedule</button>
                <div style="display:flex; gap:8px; margin-left:auto;">
                    <button class="modal-btn secondary" id="modalCancelBtn">Cancel</button>
                    <button class="modal-btn primary" id="modalSaveBtn">Save Schedule</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    
    const hourSel = document.getElementById('modalHour');
    const minSel = document.getElementById('modalMin');
    const ampmSel = document.getElementById('modalAmPm');
    const preview = document.getElementById('modalPreview');
    const removeBtn = document.getElementById('modalRemoveBtn');
    const saveBtn = document.getElementById('modalSaveBtn');
    const cancelBtn = document.getElementById('modalCancelBtn');
    
    // Prevent race: mark modal busy while any save/remove is in flight
    let busy = false;
    function setBusy(v) {
        busy = v;
        saveBtn.disabled = v;
        removeBtn.disabled = v;
        cancelBtn.disabled = v;
        saveBtn.textContent = v ? 'Working...' : 'Save Schedule';
        removeBtn.textContent = v ? 'Working...' : 'Stop Schedule';
    }
    
    function updatePreview() {
        const h = parseInt(hourSel.value);
        const m = String(parseInt(minSel.value)).padStart(2, '0');
        const ap = ampmSel.value;
        preview.textContent = `${h}:${m} ${ap} (UTC) daily`;
    }
    hourSel.addEventListener('change', updatePreview);
    minSel.addEventListener('change', updatePreview);
    ampmSel.addEventListener('change', updatePreview);
    
    cancelBtn.addEventListener('click', () => overlay.remove());
    
    // Stop Schedule — uses capturedName, NEVER the DOM
    removeBtn.addEventListener('click', async () => {
        if (busy) return;
        setBusy(true);
        try {
            const r = await fetch(`/workflows/${encodeURIComponent(capturedName)}`);
            if (!r.ok) throw new Error('workflow not found');
            const wf = await r.json();
            wf.mode = 'once';
            wf.schedule = '';
            wf.last_run_at = null;
            
            const saveRes = await fetch(`/workflows/${encodeURIComponent(capturedName)}`, {
                method: 'PUT',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(wf)
            });
            if (!saveRes.ok) throw new Error('save failed ' + saveRes.status);
            
            toast('Schedule removed from "' + capturedName + '"', 'success');
            overlay.remove();
            
            // Update badge only if the CURRENTLY loaded workflow is still this one
            const currentName = document.getElementById('currentLoadedName').textContent.trim();
            if (currentName === capturedName) {
                updateScheduleBadge('once', '');
            }
            await refreshWorkflowList();
        } catch (e) {
            toast('Error: ' + e.message, 'error');
            setBusy(false);
        }
    });
    
    // Save Schedule — uses capturedName, NEVER the DOM
    saveBtn.addEventListener('click', async () => {
        if (busy) return;
        setBusy(true);
        
        const h = parseInt(hourSel.value);
        const m = parseInt(minSel.value);
        const ap = ampmSel.value;
        
        let hour24;
        if (ap === 'AM') {
            hour24 = (h === 12) ? 0 : h;
        } else {
            hour24 = (h === 12) ? 12 : (h + 12);
        }
        const cronExpr = `${m} ${hour24} * * *`;
        
        try {
            const r = await fetch(`/workflows/${encodeURIComponent(capturedName)}`);
            if (!r.ok) throw new Error('workflow not found');
            const wf = await r.json();
            wf.mode = 'scheduled';
            wf.schedule = cronExpr;
            if (!wf.last_run_at) {
                wf.last_run_at = new Date(Date.now() - 24*60*60*1000).toISOString().replace('.000', '');
            }
            
            const saveRes = await fetch(`/workflows/${encodeURIComponent(capturedName)}`, {
                method: 'PUT',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(wf)
            });
            if (!saveRes.ok) throw new Error('save failed ' + saveRes.status);
            
            const timeStr = `${h}:${String(m).padStart(2, '0')} ${ap}`;
            toast('Scheduled "' + capturedName + '" daily at ' + timeStr + ' UTC', 'success');
            overlay.remove();
            
            // Update badge only if the CURRENTLY loaded workflow is still this one
            const currentName = document.getElementById('currentLoadedName').textContent.trim();
            if (currentName === capturedName) {
                updateScheduleBadge('scheduled', cronExpr);
            }
            await refreshWorkflowList();
        } catch (e) {
            toast('Error: ' + e.message, 'error');
            setBusy(false);
        }
    });
}

function updateScheduleBadge'''

if old_fn_pattern.search(html):
    html = old_fn_pattern.sub(lambda m: new_fn, html, count=1)
    changes += 1
    print("  OK — openScheduleModal rewritten with name isolation")
else:
    print("  FAIL — openScheduleModal pattern not matched")

# ═══════════════════════════════════════════════════════════════
# Also close any open modal when a different workflow is loaded
# (prevents the "still-open modal for wrong workflow" scenario)
# ═══════════════════════════════════════════════════════════════
print("\n[2] Auto-close schedule modal when workflow changes...")

# Add to loadWorkflowFromSelector — close any open modals at the start
old_load_start = '''async function loadWorkflowFromSelector(name) {
    if (!name) return; 

    confirmLoadWorkflow(name, async () => {
        try {'''

new_load_start = '''async function loadWorkflowFromSelector(name) {
    if (!name) return; 

    // Close any open modal (prevents stale schedule modal from acting on the wrong workflow)
    document.querySelectorAll('.modal-overlay').forEach(m => m.remove());

    confirmLoadWorkflow(name, async () => {
        try {'''

if old_load_start in html:
    html = html.replace(old_load_start, new_load_start, 1)
    changes += 1
    print("  OK — modals close when loading a different workflow")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
print("\n[3] Verifying...")

final = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("captures name once",           'let capturedName = document.getElementById' in final),
    ("shows name in modal title",    'id="modalWorkflowName"' in final),
    ("uses capturedName in fetch",   'fetch(`/workflows/${encodeURIComponent(capturedName)}`)' in final),
    ("uses capturedName in PUT",     'fetch(`/workflows/${encodeURIComponent(capturedName)}`' in final),
    ("prevents double-click",        'if (busy) return;' in final),
    ("busy disables buttons",        'saveBtn.disabled = v;' in final),
    ("badge only updates if same",   "if (currentName === capturedName)" in final),
    ("modals close on load",         "document.querySelectorAll('.modal-overlay').forEach(m => m.remove());\n\n    confirmLoadWorkflow" in final),
    ("confirms name in toast",       "toast('Schedule removed from \"' + capturedName" in final),
    ("12-hour picker intact",        'id="modalHour"' in final),
]

all_ok = True
for name, ok in checks:
    print("  [{}] {}".format("OK  " if ok else "FAIL", name))
    if not ok:
        all_ok = False

print()
if all_ok:
    print("=" * 55)
    print("PATCH COMPLETE")
    print("=" * 55)
    print("\nNext:")
    print("  git add public/index.html")
    print("  git commit -m 'Fix schedule modal: isolate workflow name, disable during ops, close on workflow switch'")
    print("  git push origin main")
else:
    print("Review FAIL lines above")