import httpx

# Test 1 — no key (should be 403)
try:
    r = httpx.get('http://127.0.0.1:18790/api/health')
    print('NO_AUTH:', r.status_code)
except Exception as e:
    print('NO_AUTH_EX:', e)

# Test 2 — wrong key (should be 403)
try:
    r = httpx.get('http://127.0.0.1:18790/api/health', headers={'X-API-Key': 'wrong'})
    print('WRONG_KEY:', r.status_code)
except Exception as e:
    print('WRONG_KEY_EX:', e)

# Test 3 — correct key (should be 200)
# Use: nova_admin_2026
try:
    r = httpx.get('http://127.0.0.1:18790/api/health', headers={'X-API-Key': 'nova_admin_2026'})
    print('CORRECT_KEY:', r.status_code, r.json())
except Exception as e:
    print('CORRECT_KEY_EX:', e)

# Test 4 — env var check
import os
print('ENV:', repr(os.getenv('DASHBOARD_API_KEY')))
print('ENV_DEFAULT:', repr(os.getenv('DASHBOARD_API_KEY', 'nova_admin_2026')))
