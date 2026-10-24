import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_simple_sched')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("File: {} chars".format(len(html)))
changes = 0

# ═══════════════════════════════════════════════════════════════
# Replace the entire openScheduleModal function
# ═══════════════════════════════════════════════════════════════
print("[1] Replacing openScheduleModal with simpler 12-hour version...")

old_fn_pattern = re.compile(
    r"async function openScheduleModal\(\) \{[\s\S]*?\n\}\n\nfunction updateScheduleBadge",
    re.DOTALL
)

new_fn = '''async function openScheduleModal() {
    let name = document.getElementById('workflowName').value.trim();
    if (document.getElementById('workflowInputContainer').style.display === 'none') {
        name = document.getElementById('currentLoadedName').textContent.trim();
    }
    if (!name) { toast('Save or name the workflow first', 'error'); return; }
    
    // Save canvas first so we don't lose nodes
    const saved = await saveCurrentWorkflow();
    if (!saved) { toast('Could not save workflow first', 'error'); return; }
    
    // Fetch current mode + schedule
    let currentMode = 'once', currentSchedule = '';
    try {
        const r = await fetch(`/workflows/${encodeURIComponent(name)}`);
        if (r.ok) {
            const d = await r.json();
            currentMode = d.mode || 'once';
            currentSchedule = d.schedule || '';
        }
    } catch (_) {}
    
    // Parse existing cron into hour/minute/am-pm (assume daily = "M H * * *")
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
    
    // Build hour options 1-12
    let hourOpts = '';
    for (let h = 1; h <= 12; h++) {
        hourOpts += `<option value="${h}" ${h === initHour12 ? 'selected' : ''}>${h}</option>`;
    }
    // Build minute options (00, 05, 10, ..., 55)
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
                <i class="fas fa-clock text-blue-400"></i> Schedule "${name}"
            </h2>
            <p style="font-size:12px; color:#94a3b8; margin-bottom:20px; line-height:1.5;">
                Runs <strong>once per day</strong> at the time you set below.
                If the scheduler wakes up late, the workflow still runs — catch-up handles it.
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
    
    // Update preview when any picker changes
    function updatePreview() {
        const h = parseInt(hourSel.value);
        const m = String(parseInt(minSel.value)).padStart(2, '0');
        const ap = ampmSel.value;
        preview.textContent = `${h}:${m} ${ap} (UTC) daily`;
    }
    hourSel.addEventListener('change', updatePreview);
    minSel.addEventListener('change', updatePreview);
    ampmSel.addEventListener('change', updatePreview);
    
    // Cancel
    document.getElementById('modalCancelBtn').addEventListener('click', () => overlay.remove());
    
    // Stop schedule
    removeBtn.addEventListener('click', async () => {
        try {
            const r = await fetch(`/workflows/${encodeURIComponent(name)}`);
            const wf = r.ok ? await r.json() : {};
            wf.mode = 'once';
            wf.schedule = '';
            wf.last_run_at = null;
            
            const saveRes = await fetch(`/workflows/${encodeURIComponent(name)}`, {
                method: 'PUT',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(wf)
            });
            if (saveRes.ok) {
                toast('Schedule stopped', 'success');
                overlay.remove();
                updateScheduleBadge('once', '');
                await refreshWorkflowList();
            }
        } catch (e) {
            toast('Error: ' + e.message, 'error');
        }
    });
    
    // Save schedule — convert 12h time to cron
    document.getElementById('modalSaveBtn').addEventListener('click', async () => {
        const h = parseInt(hourSel.value);       // 1..12
        const m = parseInt(minSel.value);         // 0..55
        const ap = ampmSel.value;                 // 'AM' or 'PM'
        
        // Convert 12h to 24h
        let hour24;
        if (ap === 'AM') {
            hour24 = (h === 12) ? 0 : h;
        } else {
            hour24 = (h === 12) ? 12 : (h + 12);
        }
        
        // Build cron expression: "M H * * *"
        const cronExpr = `${m} ${hour24} * * *`;
        
        try {
            const r = await fetch(`/workflows/${encodeURIComponent(name)}`);
            const wf = await r.json();
            wf.mode = 'scheduled';
            wf.schedule = cronExpr;
            if (!wf.last_run_at) {
                wf.last_run_at = new Date(Date.now() - 24*60*60*1000).toISOString().replace('.000', '');
            }
            
            const saveRes = await fetch(`/workflows/${encodeURIComponent(name)}`, {
                method: 'PUT',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(wf)
            });
            if (saveRes.ok) {
                const timeStr = `${h}:${String(m).padStart(2, '0')} ${ap}`;
                toast('Scheduled daily at ' + timeStr + ' UTC', 'success');
                overlay.remove();
                updateScheduleBadge('scheduled', cronExpr);
                await refreshWorkflowList();
            } else {
                toast('Save failed', 'error');
            }
        } catch (e) {
            toast('Error: ' + e.message, 'error');
        }
    });
}

function updateScheduleBadge'''

if old_fn_pattern.search(html):
    # ★ Use lambda to avoid escape processing in replacement string
    html = old_fn_pattern.sub(lambda m: new_fn, html, count=1)
    changes += 1
    print("  OK — openScheduleModal replaced with 12-hour version")
else:
    print("  FAIL — openScheduleModal pattern not matched")

# ═══════════════════════════════════════════════════════════════
# Update the badge to show a friendlier label
# ═══════════════════════════════════════════════════════════════
print("\n[2] Improving badge display...")

old_badge = '''function updateScheduleBadge(mode, schedule) {
    const badge = document.getElementById('schedBadge');
    if (!badge) return;
    if (mode === 'scheduled' && schedule) {
        badge.textContent = '🔄';
        badge.style.color = '#22c55e';
        badge.title = 'Scheduled: ' + schedule;
    } else {
        badge.textContent = '';
        badge.title = '';
    }
}'''

new_badge = '''function updateScheduleBadge(mode, schedule) {
    const badge = document.getElementById('schedBadge');
    if (!badge) return;
    if (mode === 'scheduled' && schedule) {
        let label = 'daily';
        try {
            const parts = schedule.trim().split(/\\s+/);
            if (parts.length === 5) {
                const min = parseInt(parts[0]) || 0;
                const hour24 = parseInt(parts[1]) || 0;
                let h12, ap;
                if (hour24 === 0) { h12 = 12; ap = 'AM'; }
                else if (hour24 === 12) { h12 = 12; ap = 'PM'; }
                else if (hour24 < 12) { h12 = hour24; ap = 'AM'; }
                else { h12 = hour24 - 12; ap = 'PM'; }
                label = `${h12}:${String(min).padStart(2,'0')} ${ap}`;
            }
        } catch (_) {}
        badge.textContent = label;
        badge.style.color = '#22c55e';
        badge.title = 'Scheduled: ' + schedule;
    } else {
        badge.textContent = '';
        badge.title = '';
    }
}'''

if old_badge in html:
    # Use lambda too — the badge contains regex escape \s
    html = html.replace(old_badge, new_badge, 1)
    changes += 1
    print("  OK — badge shows friendly time (e.g. '9:00 AM')")

# ═══════════════════════════════════════════════════════════════
# Also improve the dropdown labels — show friendly time instead of raw cron
# ═══════════════════════════════════════════════════════════════
print("\n[3] Improving dropdown labels...")

old_dropdown = '''opt.textContent = (mode === 'scheduled' ? '🔄 ' : '') + name + (schedule ? ` [${schedule}]` : '');'''

new_dropdown = '''let timeLabel = '';
                if (mode === 'scheduled' && schedule) {
                    try {
                        const parts = schedule.trim().split(/\\s+/);
                        if (parts.length === 5) {
                            const min = parseInt(parts[0]) || 0;
                            const hour24 = parseInt(parts[1]) || 0;
                            let h12, ap;
                            if (hour24 === 0) { h12 = 12; ap = 'AM'; }
                            else if (hour24 === 12) { h12 = 12; ap = 'PM'; }
                            else if (hour24 < 12) { h12 = hour24; ap = 'AM'; }
                            else { h12 = hour24 - 12; ap = 'PM'; }
                            timeLabel = ` — ${h12}:${String(min).padStart(2,'0')} ${ap}`;
                        }
                    } catch (_) {}
                }
                opt.textContent = (mode === 'scheduled' ? '🔄 ' : '') + name + timeLabel;'''

if old_dropdown in html:
    html = html.replace(old_dropdown, new_dropdown, 1)
    changes += 1
    print("  OK — dropdown shows friendly time (e.g. '🔄 daily-report — 9:00 AM')")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
print("\n[4] Verifying...")

final = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("12-hour hour picker",        'id="modalHour"' in final),
    ("12-hour minute picker",      'id="modalMin"' in final),
    ("AM/PM selector",             'id="modalAmPm"' in final),
    ("No mode dropdown",           'id="modalSchedMode"' not in final),
    ("Preview updates on change",  'function updatePreview()' in final),
    ("Converts 12h to cron",       'hour24 = (h === 12) ? 0 : h' in final),
    ("Badge shows friendly time",  'badge.textContent = label' in final),
    ("Dropdown shows friendly",    'timeLabel = ` — ${h12}:' in final),
    ("Stop Schedule button",       'id="modalRemoveBtn"' in final),
    ("Save Schedule button",       'id="modalSaveBtn"' in final),
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
    print("  git commit -m 'Schedule modal: 12-hour time picker, no mode dropdown'")
    print("  git push origin main")
else:
    print("Review FAIL lines above")
    print("Backup: index.html.backup_simple_sched")