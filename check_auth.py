import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

expected = os.getenv("DASHBOARD_API_KEY")
result = os.getenv("DASHBOARD_API_KEY", "")
print("raw env  :", repr(expected))
print("with fallback:", repr(result))
print("raw len  :", len(expected) if expected else 0)
print("fallback len:", len(result))
