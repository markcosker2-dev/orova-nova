import os
import requests
import sys

# Force UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Grab from diagnose_ai output or hardcode for test
# The user's key was printed masked as nvapi-wIDWZ0chY...
# I'll try to read from .env if possible, otherwise I'll ask user.
# But I can just import from .env using python-dotenv

from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")

if not api_key:
    # Fallback: try to find it in .env manually
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("NVIDIA_API_KEY="):
                    api_key = line.strip().split("=")[1]
                    break
    except:
        pass

if not api_key:
    print("❌ NVIDIA_API_KEY not found")
    sys.exit(1)

print(f"🔑 Testing NVIDIA API Key: {api_key[:10]}...")

url = "https://integrate.api.nvidia.com/v1/models"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json"
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        models = response.json().get("data", [])
        print(f"✅ Found {len(models)} models:")
        for m in models:
            print(f"   - {m['id']}")
    else:
        print(f"❌ Failed: {response.text}")

except Exception as e:
    print(f"❌ Error: {e}")
