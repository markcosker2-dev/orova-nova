import requests
import json
import sys

def test_chat():
    url = "http://localhost:8080/api/chat"
    payload = {"message": "Hello Nova, say VERIFICATION SUCCESS if you can hear me"}
    headers = {"Content-Type": "application/json"}
    
    print(f"[*] Testing {url}...")
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"[+] Status Code: {response.status_code}")
        print(f"[+] Response: {response.text}")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    test_chat()
