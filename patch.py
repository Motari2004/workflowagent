import os, shutil, sys, re

HTML = r'C:\Users\PC\Desktop\modular\workflow-pro-v3\public\index.html'

if not os.path.exists(HTML):
    print("ERROR: not found"); sys.exit(1)

shutil.copy(HTML, HTML + '.backup_schedmodal')
print("Backed up\n")

with open(HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print("File: {} chars".format(len(html)))
changes = 0

# ═══════════════════════════════════════════════════════════════
# 1. Remove the sidebar mode + schedule UI that was added
# ═══════════════════════════════════════════════════════════════
print("\n[1] Removing sidebar mode/schedule UI...")

old_sidebar_ui = '''<div style="margin-bottom:8px;">
                <select id="workflowMode" class="pro-input" title="How this workflow runs">
                    <option value="once">▶ One-shot (manual / webhook only)</option>
                    <option value="scheduled">🔄 Scheduled (auto-runs)</option>
                </select>
            </div>
            <div id="scheduleFields" style="display:none; margin-bottom:8px;">
                <label style="display:block; font-size:10px; color:#64748b; margin-bottom:4px; text-transform:uppercase;">Cron Schedule (UTC)</label>
                <input id="workflowSchedule" type="text" class="pro-input" placeholder="0 9 * * *" value="0 9 * * *">
                <div style="font-size:9px; color:#475569; margin-top:4px; line-height:1.6;">
                    <code style="color:#94a3b8;">0 9 * * *</code> — daily 9:00 UTC<br>
                    <code style="color:#94a3b8;">22 8 * * *</code> — daily 8:22 UTC<br>
                    <code style="color:#94a3b8;">0 6 * * 1-5</code> — weekdays 6:00 UTC<br>
                    <code style="color:#94a3b8;">*/10 * * * *</code> — every 10 min
                </div>
            </div>
            '''

if old_sidebar_ui in html:
    html = html.replace(old_sidebar_ui, '', 1)
    changes += 1
    print("  OK — removed sidebar mode/schedule UI")
else:
    # Try without trailing whitespace
    old_alt = old_sidebar_ui.rstrip()
    if old_alt in html:
        html = html.replace(old_alt, '', 1)
        changes += 1
        print("  OK — removed sidebar mode/schedule UI (alt)")
    else:
        print("  WARN — sidebar UI not found (may be from a different patch)")
        print("  Searching for 'workflowMode' in sidebar...")
        if 'id="workflowMode"' in html:
            # Try to find and remove the whole block
            pattern = re.compile(
                r'<div style="margin-bottom:8px;">\s*<select id="workflowMode"[\s\S]*?</div>\s*(?=<div id="workflowLoadedContainer")',
                re.DOTALL
            )
            if pattern.search(html):
                html = pattern.sub('', html, count=1)
                changes += 1
                print("  OK — removed via regex")

# ═══════════════════════════════════════════════════════════════
# 2. Replace the Schedule button's onclick
# ═══════════════════════════════════════════════════════════════
print("\n[2] Rewiring Schedule button...")

old_btn = '''<button onclick="scheduleCurrentWorkflow()" class="pro-btn">
                <i class="fas fa-clock"></i>
                <span>Schedule</span>
                <span class="shortcut">60s</span>
            </button>'''

new_btn = '''<button onclick="openScheduleModal()" class="pro-btn">
                <i class="fas fa-clock"></i>
                <span>Schedule</span>
                <span class="shortcut" id="schedBadge"></span>
            </button>'''

if old_btn in html:
    html = html.replace(old_btn, new_btn, 1)
    changes += 1
    print("  OK — Schedule button rewired to openScheduleModal()")
else:
    # Try alternate — some patches may have changed the shortcut
    pattern = re.compile(
        r'<button onclick="scheduleCurrentWorkflow\(\)"[^>]*>[\s\S]*?</button>',
        re.DOTALL
    )
    if pattern.search(html):
        html = pattern.sub(new_btn, html, count=1)
        changes += 1
        print("  OK — Schedule button rewired (regex)")

# ═══════════════════════════════════════════════════════════════
# 3. Remove the old mode toggle listener
# ═══════════════════════════════════════════════════════════════
print("\n[3] Removing old mode toggle listener...")

old_listener = '''// Show/hide schedule field based on mode
(function() {
    const modeEl = document.getElementById('workflowMode');
    const schedEl = document.getElementById('scheduleFields');
    if (modeEl && schedEl) {
        modeEl.addEventListener('change', function() {
            schedEl.style.display = (this.value === 'scheduled') ? 'block' : 'none';
        });
    }
})();

'''

if old_listener in html:
    html = html.replace(old_listener, '', 1)
    changes += 1
    print("  OK — old listener removed")

# ═══════════════════════════════════════════════════════════════
# 4. Remove mode + schedule from saveCurrentWorkflow
# ═══════════════════════════════════════════════════════════════
print("\n[4] Simplifying saveCurrentWorkflow...")

old_save_add = '''const mode = document.getElementById('workflowMode')?.value || 'once';
    const schedule = document.getElementById('workflowSchedule')?.value.trim() || '';
    
    const payload = {
        nodes: buildPayload(),
        graph: graph.serialize(),
        mode: mode,
        schedule: schedule,
        updated_at: new Date().toISOString()
    };'''

new_save_add = '''// Preserve existing mode/schedule (not edited here — Schedule button handles that)
    let _existingMode = 'once', _existingSchedule = '';
    try {
        const _r = await fetch(`/workflows/${encodeURIComponent(name)}`);
        if (_r.ok) {
            const _d = await _r.json();
            _existingMode = _d.mode || 'once';
            _existingSchedule = _d.schedule || '';
        }
    } catch (_) {}
    
    const payload = {
        nodes: buildPayload(),
        graph: graph.serialize(),
        mode: _existingMode,
        schedule: _existingSchedule,
        updated_at: new Date().toISOString()
    };'''

if old_save_add in html:
    html = html.replace(old_save_add, new_save_add, 1)
    changes += 1
    print("  OK — saveCurrentWorkflow preserves existing mode/schedule")
else:
    print("  WARN — saveCurrentWorkflow pattern not matched")

# ═══════════════════════════════════════════════════════════════
# 5. Remove mode restore from loadWorkflowFromSelector
# ═══════════════════════════════════════════════════════════════
print("\n[5] Cleaning up loadWorkflowFromSelector...")

old_load_restore = '''// Restore mode + schedule
            const modeEl = document.getElementById('workflowMode');
            const schedEl = document.getElementById('workflowSchedule');
            const schedFields = document.getElementById('scheduleFields');
            if (modeEl) {
                modeEl.value = data.mode || 'once';
                if (schedFields) schedFields.style.display = modeEl.value === 'scheduled' ? 'block' : 'none';
            }
            if (schedEl) {
                schedEl.value = data.schedule || '';
            }'''

new_load_restore = '''// Update Schedule button badge with current mode/schedule
            const schedBadge = document.getElementById('schedBadge');
            if (schedBadge) {
                if (data.mode === 'scheduled' && data.schedule) {
                    schedBadge.textContent = '🔄';
                    schedBadge.style.color = '#22c55e';
                } else {
                    schedBadge.textContent = '';
                }
            }'''

if old_load_restore in html:
    html = html.replace(old_load_restore, new_load_restore, 1)
    changes += 1
    print("  OK — loadWorkflowFromSelector cleaned up")

# ═══════════════════════════════════════════════════════════════
# 6. Add openScheduleModal() and related functions
# ═══════════════════════════════════════════════════════════════
print("\n[6] Adding openScheduleModal() + helpers...")

# Insert before the "// Bindings" comment
marker = "// Bindings\n"

modal_code = '''// ═══════════════════════════════════════════════════════════════
// SCHEDULE MODAL — set per-workflow cron schedule
// ═══════════════════════════════════════════════════════════════
async function openScheduleModal() {
    // Get current workflow
    let name = document.getElementById('workflowName').value.trim();
    if (document.getElementById('workflowInputContainer').style.display === 'none') {
        name = document.getElementById('currentLoadedName').textContent.trim();
    }
    if (!name) { toast('Save or name the workflow first', 'error'); return; }
    
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
    
    // Build modal
    document.querySelectorAll('.modal-overlay').forEach(m => m.remove());
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    
    overlay.innerHTML = `
        <div class="modal" style="width: 500px;">
            <h2 style="margin-top:0; font-size:16px; display:flex; align-items:center; gap:8px;">
                <i class="fas fa-clock text-blue-400"></i> Schedule "${name}"
            </h2>
            <p style="font-size:12px; color:#94a3b8; margin-bottom:16px;">
                Choose how this workflow runs. One-shot workflows only run when you click Execute or POST to their webhook.
                Scheduled workflows run automatically via the cron dispatcher.
            </p>
            
            <div style="margin-bottom:16px;">
                <label style="display:block; font-size:11px; color:#94a3b8; text-transform:uppercase; margin-bottom:6px;">Mode</label>
                <select id="modalSchedMode" class="pro-input" style="width:100%; height:38px;">
                    <option value="once">▶ One-shot (manual / webhook only)</option>
                    <option value="scheduled">🔄 Scheduled (auto-runs on cron)</option>
                </select>
            </div>
            
            <div id="modalSchedFields" style="display:none; margin-bottom:16px;">
                <label style="display:block; font-size:11px; color:#94a3b8; text-transform:uppercase; margin-bottom:6px;">Cron Expression (UTC)</label>
                <input id="modalSchedCron" type="text" class="pro-input" placeholder="22 8 * * *" value="${currentSchedule || '0 9 * * *'}" style="width:100%; height:38px; font-family:ui-monospace,monospace;">
                <div style="font-size:10px; color:#64748b; margin-top:8px; line-height:1.8;">
                    <code style="color:#93c5fd;">0 9 * * *</code> — daily 09:00 UTC<br>
                    <code style="color:#93c5fd;">22 8 * * *</code> — daily 08:22 UTC<br>
                    <code style="color:#93c5fd;">0 6 * * 1-5</code> — weekdays 06:00 UTC<br>
                    <code style="color:#93c5fd;">0 */2 * * *</code> — every 2 hours<br>
                    <code style="color:#93c5fd;">*/10 * * * *</code> — every 10 minutes<br>
                    <code style="color:#93c5fd;">0 9 1 * *</code> — 1st of every month, 09:00 UTC
                </div>
                <div style="font-size:10px; color:#f59e0b; margin-top:8px;">
                    ⚠️ If the dispatcher runs late, the workflow will still execute — catch-up handles missed slots.
                </div>
            </div>
            
            <div class="modal-buttons" style="justify-content: space-between;">
                <button class="modal-btn secondary" id="modalSchedRemoveBtn" style="display:${currentMode === 'scheduled' ? 'block' : 'none'};">Remove Schedule</button>
                <div style="display:flex; gap:8px; margin-left:auto;">
                    <button class="modal-btn secondary" id="modalSchedCancelBtn">Cancel</button>
                    <button class="modal-btn primary" id="modalSchedSaveBtn">Save</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    
    const modeSel = document.getElementById('modalSchedMode');
    const schedFields = document.getElementById('modalSchedFields');
    const cronInput = document.getElementById('modalSchedCron');
    const removeBtn = document.getElementById('modalSchedRemoveBtn');
    
    // Initialize
    modeSel.value = currentMode;
    schedFields.style.display = currentMode === 'scheduled' ? 'block' : 'none';
    if (!currentSchedule) cronInput.value = '0 9 * * *';
    
    // Toggle schedule fields
    modeSel.addEventListener('change', () => {
        schedFields.style.display = modeSel.value === 'scheduled' ? 'block' : 'none';
        removeBtn.style.display = modeSel.value === 'scheduled' && currentMode === 'scheduled' ? 'block' : 'none';
    });
    
    // Cancel
    document.getElementById('modalSchedCancelBtn').addEventListener('click', () => overlay.remove());
    
    // Remove schedule
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
                toast('Schedule removed', 'success');
                overlay.remove();
                updateScheduleBadge('once', '');
                await refreshWorkflowList();
            } else {
                toast('Remove failed', 'error');
            }
        } catch (e) {
            toast('Error: ' + e.message, 'error');
        }
    });
    
    // Save
    document.getElementById('modalSchedSaveBtn').addEventListener('click', async () => {
        const newMode = modeSel.value;
        const newSchedule = newMode === 'scheduled' ? cronInput.value.trim() : '';
        
        // Validate cron if scheduled
        if (newMode === 'scheduled') {
            if (!newSchedule) { toast('Enter a cron expression', 'error'); return; }
            if (newSchedule.split(' ').length !== 5) {
                toast('Cron must have 5 fields (minute hour day month weekday)', 'error');
                return;
            }
        }
        
        try {
            const r = await fetch(`/workflows/${encodeURIComponent(name)}`);
            const wf = r.ok ? await r.json() : {};
            wf.mode = newMode;
            wf.schedule = newSchedule;
            
            const saveRes = await fetch(`/workflows/${encodeURIComponent(name)}`, {
                method: 'PUT',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify(wf)
            });
            if (saveRes.ok) {
                toast(newMode === 'scheduled' ? 'Scheduled: ' + newSchedule : 'Set to one-shot', 'success');
                overlay.remove();
                updateScheduleBadge(newMode, newSchedule);
                await refreshWorkflowList();
            } else {
                toast('Save failed', 'error');
            }
        } catch (e) {
            toast('Error: ' + e.message, 'error');
        }
    });
}

function updateScheduleBadge(mode, schedule) {
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
}

// Bindings
'''

if 'async function openScheduleModal' not in html:
    if marker in html:
        html = html.replace(marker, modal_code, 1)
        changes += 1
        print("  OK — openScheduleModal() + updateScheduleBadge() added")
    else:
        print("  FAIL — Bindings marker not found")
else:
    print("  SKIP — openScheduleModal already exists")

# ═══════════════════════════════════════════════════════════════
# 7. Update the dropdown to show scheduled badge without the old optgroup
# ═══════════════════════════════════════════════════════════════
print("\n[7] Fixing workflow dropdown...")

old_dropdown = '''if (data.workflows && data.workflows.length > 0) {
            const scheduled = data.workflows.filter(w => w.mode === 'scheduled');
            const once = data.workflows.filter(w => w.mode !== 'scheduled');
            
            if (scheduled.length > 0) {
                const schedGroup = document.createElement('optgroup');
                schedGroup.label = '🔄 Scheduled';
                scheduled.forEach(w => {
                    const opt = document.createElement('option');
                    opt.value = w.name;
                    opt.textContent = w.name + (w.schedule ? ` [${w.schedule}]` : '');
                    schedGroup.appendChild(opt);
                });
                selector.appendChild(schedGroup);
            }
            
            if (once.length > 0) {
                const onceGroup = document.createElement('optgroup');
                onceGroup.label = '▶ One-shot';
                once.forEach(w => {
                    const opt = document.createElement('option');
                    opt.value = w.name;
                    opt.textContent = w.name;
                    onceGroup.appendChild(opt);
                });
                selector.appendChild(onceGroup);
            }
        }'''

new_dropdown = '''if (data.workflows && data.workflows.length > 0) {
            data.workflows.forEach(w => {
                const opt = document.createElement('option');
                opt.value = w.name;
                opt.textContent = (w.mode === 'scheduled' ? '🔄 ' : '') + w.name + (w.schedule ? ` [${w.schedule}]` : '');
                selector.appendChild(opt);
            });
        }'''

if old_dropdown in html:
    html = html.replace(old_dropdown, new_dropdown, 1)
    changes += 1
    print("  OK — dropdown simplified with 🔄 prefix for scheduled")
else:
    print("  SKIP — dropdown pattern not matched")

# ═══════════════════════════════════════════════════════════════
# 8. Remove old scheduleCurrentWorkflow function (no longer called)
# ═══════════════════════════════════════════════════════════════
print("\n[8] Removing old scheduleCurrentWorkflow...")

old_fn_pattern = re.compile(
    r"async function scheduleCurrentWorkflow\(\) \{[\s\S]*?toast\([^;]*\);\s*\}",
    re.DOTALL
)

if old_fn_pattern.search(html):
    html = old_fn_pattern.sub(
        "// scheduleCurrentWorkflow deprecated — use openScheduleModal() instead",
        html, count=1
    )
    changes += 1
    print("  OK — deprecated scheduleCurrentWorkflow stubbed out")

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
print("\n[9] Writing...")

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print("  OK — wrote {} chars".format(len(html)))
print("  {} change(s) applied".format(changes))

# ═══════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════
print("\n[10] Verifying...")

final = open(HTML, 'r', encoding='utf-8').read()

checks = [
    ("Sidebar mode field removed",       'id="workflowMode"' not in final),
    ("Sidebar schedule field removed",   'id="workflowSchedule"' not in final),
    ("Schedule button uses modal",       'openScheduleModal()' in final),
    ("openScheduleModal defined",        'async function openScheduleModal' in final),
    ("updateScheduleBadge defined",      'function updateScheduleBadge' in final),
    ("Modal has cron input",             'modalSchedCron' in final),
    ("Modal has mode selector",          'modalSchedMode' in final),
    ("Badge element in button",          'id="schedBadge"' in final),
    ("Dropdown shows 🔄 prefix",         "🔄 ' + w.name" in final),
    ("Old schedule function stubbed",    'scheduleCurrentWorkflow deprecated' in final or 'scheduleCurrentWorkflow(' not in final),
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
    print()
    print("Next:")
    print("  git add public/index.html")
    print("  git commit -m 'Scheduler: modal UI inside Schedule button'")
    print("  git push origin main")
else:
    print("Review FAIL lines above")
    print("Backup at index.html.backup_schedmodal")