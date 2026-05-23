const http = require('http');

function req(path, headers, label) {
  return new Promise((resolve) => {
    const req = http.request({ hostname: '127.0.0.1', port: 18789, path, method: 'GET', headers, timeout: 5000 }, (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(d) });
        } catch {
          resolve({ status: res.statusCode, body: d });
        }
      });
    });
    req.on('error', e => resolve({ status: 'ERR', body: String(e) }));
    req.on('timeout', () => { req.destroy(); resolve({ status: 'TIMEOUT', body: 'timeout' }); });
    req.end();
  });
}

(async () => {
  const r1 = await req('/api/health', {}, 'NO_AUTH');
  console.log('NO_AUTH:', r1.status, r1.body);

  const r2 = await req('/api/health', { 'X-API-Key': 'wrong' }, 'WRONG_KEY');
  console.log('WRONG_KEY:', r2.status, r2.body);

  const r3 = await req('/api/health', { 'X-API-Key': 'nova_admin_2026' }, 'CORRECT_KEY');
  console.log('CORRECT_KEY:', r3.status, r3.body);

  console.log('ENV:', process.env.DASHBOARD_API_KEY);
  console.log('ENV_DEFAULT:', process.env.DASHBOARD_API_KEY || 'nova_admin_2026');
})();
