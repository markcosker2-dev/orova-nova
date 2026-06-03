async function requestSessionToken(ttl) {
    ttl = ttl || 3600;
    const apiKey = localStorage.getItem('NOVA_API_KEY') || 'nova_admin_2026';
    try {
        const res = await fetch((window.location.origin === 'null' || window.location.protocol === 'file:') ? 'http://localhost:18789' : window.location.origin + '/api/keys/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({ ttl: ttl })
        });
        const j = await res.json();
        if (j && j.status === 'ok' && j.token) {
            localStorage.setItem('NOVA_SESSION_TOKEN', j.token);
            showToast('Session token stored', 'success');
            return j.token;
        }
        showToast('Failed to obtain session token', 'error');
        return null;
    } catch (e) {
        console.warn('Session token request failed', e);
        showToast('Token request error', 'error');
        return null;
    }
}

window.requestSessionToken = requestSessionToken;