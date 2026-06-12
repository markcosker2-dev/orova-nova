async function requestSessionToken(ttl) {
    ttl = ttl || 3600;
    let dashboardSecret = localStorage.getItem('OROVA_DASHBOARD_SECRET');
    if (!dashboardSecret) {
        dashboardSecret = prompt('Enter your dashboard secret to request a new session token:');
        if (!dashboardSecret) {
            showToast('Dashboard secret is required to issue a session token.', 'error');
            return null;
        }
        localStorage.setItem('OROVA_DASHBOARD_SECRET', dashboardSecret);
    }

    const baseUrl = (window.location.origin === 'null' || window.location.protocol === 'file:')
        ? 'http://localhost:18789'
        : window.location.origin;

    try {
        const res = await fetch(`${baseUrl}/api/keys/new`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Dashboard-Secret': dashboardSecret },
            body: JSON.stringify({ ttl: ttl })
        });
        const j = await res.json();
        if (j && j.status === 'ok' && j.token) {
            localStorage.setItem('OROVA_SESSION_TOKEN', j.token);
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