import os
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
# Reads the key from the environment - never hardcode a live credential.
try:
    r = httpx.get('http://127.0.0.1:18790/api/health', headers={'X-API-Key': os.getenv('DASHBOARD_API_KEY', '')})
    print('CORRECT_KEY:', r.status_code, r.json())
except Exception as e:
    print('CORRECT_KEY_EX:', e)

# Test 4 — env var check
import os
print('ENV:', repr(os.getenv('DASHBOARD_API_KEY')))
print('ENV_SET:', bool(os.getenv('DASHBOARD_API_KEY')))
