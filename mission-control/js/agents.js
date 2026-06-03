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
