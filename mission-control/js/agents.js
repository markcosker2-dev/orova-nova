// Agent button wiring for Mission Control
document.addEventListener('click', async function (e) {
    const el = e.target;
    if (!el) return;
    if (el.classList && el.classList.contains('config-agent')) {
        // Config = run this agent with a custom goal
        const agent = el.dataset.agent || 'nova';
        const goal = prompt(`Custom goal for ${agent}:`, `Find 5 new leads in our target niche`);
        if (!goal || !goal.trim()) return;
        showToast(`🔁 Queued ${agent} with custom goal...`, 'info');
        try {
            const res = await apiFetch('/api/agents/run', {
                method: 'POST',
                body: JSON.stringify({ agent: agent, goal: goal.trim() })
            });
            if (res && res.status === 'queued') showToast(`✅ ${agent} queued (${res.task_id})`, 'success');
            else showToast('❌ Failed to queue agent — check your dashboard key', 'error');
        } catch (err) {
            showToast('❌ Agent run failed', 'error');
        }
        return;
    }
    if (el.classList && el.classList.contains('run-agent')) {
        const agent = el.dataset.agent || 'nova';
        showToast(`🔁 Queued ${agent}...`, 'info');
        try {
            const res = await apiFetch('/api/agents/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent: agent, goal: `Execute default routine for ${agent}` })
            });
            if (res && res.status === 'queued') {
                showToast(`✅ ${agent} queued (${res.task_id})`, 'success');
            } else {
                showToast('❌ Failed to queue — click again and enter your DASHBOARD_API_KEY when prompted', 'error');
            }
        } catch (err) {
            console.warn('Agent run failed', err);
            showToast('❌ Agent run failed', 'error');
        }
    }
});

// Polling and rendering for queue and logs
async function fetchAndRenderQueue() {
    try {
        const res = await apiFetch('/api/agents/queue');
        const listEl = document.getElementById('agent-queue-list');
        if (!res || res.status !== 'ok' || !listEl) return;
        const q = res.queue || [];
        if (q.length === 0) { listEl.innerHTML = '<div class="agent-queue-item">No recent tasks</div>'; return; }
        listEl.innerHTML = q.slice(0,20).map(function (item) {
            const name = item.agent || 'agent';
            const id = item.task_id || '';
            const status = item.status || 'queued';
            const goal = (item.goal || '').slice(0,60);
            let actions = '';
            if (status === 'queued') actions = `<button class="btn-tertiary btn-cancel" data-task="${id}">Cancel</button>`;
            if (status === 'failed') actions = `<button class="btn-secondary btn-retry" data-task="${id}">Retry</button>`;
            return `<div class="agent-queue-item"><div style="flex:1"><strong>${name}</strong> — ${esc(goal)}</div><div style="display:flex;gap:8px;align-items:center"><div class="status">${esc(status)}</div>${actions}</div></div>`;
        }).join('');
    } catch (e) { console.warn('Queue fetch failed', e); }
}

async function fetchAndRenderLogs() {
    try {
        const res = await apiFetch('/api/agents/logs');
        const listEl = document.getElementById('agent-logs-list');
        if (!res || res.status !== 'ok' || !listEl) return;
        const logs = res.logs || [];
        if (logs.length === 0) { listEl.innerHTML = '<div class="log-line">No logs yet</div>'; return; }
        listEl.innerHTML = logs.slice(-80).reverse().map(function (l) {
            const ts = l.ts || l.ts || '';
            const msg = l.msg || l.message || JSON.stringify(l).slice(0,220);
            return `<div class="log-line">${esc(ts)} — ${esc(msg)}</div>`;
        }).join('');
    } catch (e) { console.warn('Logs fetch failed', e); }
}

// Poll every 10s (2.5s was ~2,900 req/hour per tab — starves the
// free-tier backend that also runs the agent), and never from hidden tabs
function startAgentMonitoring() {
    fetchAndRenderQueue();
    fetchAndRenderLogs();
    setInterval(function () { if (!document.hidden) fetchAndRenderQueue(); }, 10000);
    setInterval(function () { if (!document.hidden) fetchAndRenderLogs(); }, 10000);
}

// Launch when DOM ready
document.addEventListener('DOMContentLoaded', function () { startAgentMonitoring(); });

// Global handler for cancel/retry buttons inside queue
document.addEventListener('click', async function (e) {
    const el = e.target;
    if (!el) return;
    if (el.classList && el.classList.contains('btn-cancel')) {
        const task = el.dataset.task;
        if (!task) return;
        showToast('✋ Cancelling...', 'info');
        const res = await apiFetch('/api/agents/cancel', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: task })
        });
        if (res && res.status === 'ok') showToast('✅ Cancelled', 'success'); else showToast('❌ Cancel failed', 'error');
        await fetchAndRenderQueue();
    }
    if (el.classList && el.classList.contains('btn-retry')) {
        const task = el.dataset.task;
        if (!task) return;
        showToast('↻ Retrying...', 'info');
        const res = await apiFetch('/api/agents/retry', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: task })
        });
        if (res && res.status === 'queued') showToast('✅ Retry queued', 'success'); else showToast('❌ Retry failed', 'error');
        await fetchAndRenderQueue();
    }
});
