
from duckduckgo_search import DDGS
import json

def search():
    print("Testing DDGS Sync...")
    try:
        results = list(DDGS().text("test search", max_results=5))
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search()
