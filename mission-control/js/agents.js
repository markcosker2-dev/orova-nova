// Agent button wiring for Mission Control
document.addEventListener('click', async function (e) {
    const el = e.target;
    if (!el) return;
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
                showToast('❌ Failed to queue agent', 'error');
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
            return `<div class="agent-queue-item"><div style="flex:1"><strong>${name}</strong> — ${esc(goal)}</div><div class="status">${esc(status)}</div></div>`;
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

// Start polling every 2.5s
function startAgentMonitoring() {
    fetchAndRenderQueue();
    fetchAndRenderLogs();
    setInterval(fetchAndRenderQueue, 2500);
    setInterval(fetchAndRenderLogs, 2500);
}

// Launch when DOM ready
document.addEventListener('DOMContentLoaded', function () { startAgentMonitoring(); });
