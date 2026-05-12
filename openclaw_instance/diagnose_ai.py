# -*- coding: utf-8 -*-
"""
OROVA — Nova AI Client Diagnostic Tool
Run this on the AWS EC2 instance to diagnose why all AI providers are failing.
Usage: python diagnose_ai.py
"""

import os
import sys
import asyncio
import logging

# Force UTF-8 stdout for Windows emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load env
from dotenv import load_dotenv
load_dotenv()


async def test_claude():
    """Test Claude Opus via Vertex AI."""
    print("\n🔵 Testing Claude Opus 4.6 (Vertex AI)...")
    try:
        from anthropic import AnthropicVertex
        project_id = os.getenv("GCP_PROJECT_ID", "orova-484613")
        region = os.getenv("CLAUDE_REGION", "us-east5")
        
        client = AnthropicVertex(project_id=project_id, region=region)
        print(f"   Project: {project_id} | Region: {region}")
        
        response = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'Claude OK' and nothing else."}]
        )
        
        text = response.content[0].text
        print(f"   ✅ CLAUDE OK: {text}")
        return True
    except Exception as e:
        print(f"   ❌ CLAUDE FAILED: {e}")
        if "credentials" in str(e).lower() or "auth" in str(e).lower():
            print("   💡 FIX: Set GOOGLE_APPLICATION_CREDENTIALS to a valid service account JSON")
            print("   💡 FIX: Run 'gcloud auth application-default login' on this machine")
        elif "not found" in str(e).lower() or "404" in str(e):
            print("   💡 FIX: Enable the Anthropic API on Vertex AI in GCP Console")
        elif "permission" in str(e).lower():
            print("   💡 FIX: Grant the service account 'Vertex AI User' role")
        return False


async def test_nvidia():
    """Test NVIDIA Llama 3.3 via NVIDIA API."""
    print("\n🟢 Testing NVIDIA Llama 3.3...")
    try:
        from openai import AsyncOpenAI
        key = os.getenv("NVIDIA_API_KEY")
        if not key:
            print("   ❌ NVIDIA_API_KEY not set in .env")
            return False
        
        print(f"   Key: {key[:10]}...{key[-4:]}")
        client = AsyncOpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")
        
        response = await client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": "Say 'NVIDIA OK' and nothing else."}],
            max_tokens=50
        )
        
        text = response.choices[0].message.content
        print(f"   ✅ NVIDIA OK: {text}")
        return True
    except Exception as e:
        print(f"   ❌ NVIDIA FAILED: {e}")
        if "401" in str(e) or "invalid" in str(e).lower():
            print("   💡 FIX: NVIDIA API key may be expired. Get a new one at build.nvidia.com")
        elif "model" in str(e).lower():
            print("   💡 FIX: Model 'meta/llama-3.3-70b-instruct' may be unavailable")
        return False


async def test_groq():
    """Test Groq Llama."""
    print("\n🟡 Testing Groq Llama 3.3...")
    try:
        from groq import AsyncGroq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            print("   ❌ GROQ_API_KEY not set in .env")
            return False
        
        print(f"   Key: {key[:10]}...{key[-4:]}")
        client = AsyncGroq(api_key=key)
        
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Say 'Groq OK' and nothing else."}],
            max_tokens=50
        )
        
        text = response.choices[0].message.content
        print(f"   ✅ GROQ OK: {text}")
        return True
    except Exception as e:
        print(f"   ❌ GROQ FAILED: {e}")
        if "401" in str(e) or "invalid" in str(e).lower():
            print("   💡 FIX: Groq API key may be expired. Get a new one at console.groq.com")
        elif "rate" in str(e).lower():
            print("   💡 FIX: Groq free tier rate limited. Wait or upgrade.")
        return False


async def test_openrouter():
    """Test OpenRouter."""
    print("\n🟠 Testing OpenRouter (Emergency)...")
    try:
        from openai import AsyncOpenAI
        key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        base = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        
        if not key:
            print("   ❌ No OpenRouter key found")
            return False
        
        print(f"   Key: {key[:10]}...{key[-4:]}")
        client = AsyncOpenAI(
            api_key=key,
            base_url=base,
            default_headers={"HTTP-Referer": "https://orova.ai", "X-Title": "OROVA-Diagnostic"}
        )
        
        response = await client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=[{"role": "user", "content": "Say 'OpenRouter OK' and nothing else."}],
            max_tokens=50
        )
        
        text = response.choices[0].message.content
        print(f"   ✅ OPENROUTER OK: {text}")
        return True
    except Exception as e:
        print(f"   ❌ OPENROUTER FAILED: {e}")
        if "401" in str(e) or "invalid" in str(e).lower():
            print("   💡 FIX: OpenRouter key expired. Get a new one at openrouter.ai")
        elif "limit" in str(e).lower() or "quota" in str(e).lower():
            print("   💡 FIX: Free tier quota exhausted. Add credits at openrouter.ai/credits")
        return False


async def main():
    print("="*60)
    print("🔍 NOVA AI CLIENT DIAGNOSTIC")
    print("="*60)
    print(f"Working directory: {os.getcwd()}")
    print(f".env loaded: {os.path.exists('.env')}")
    
    # Check env file
    env_vars = ["GCP_PROJECT_ID", "NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
                "GOOGLE_APPLICATION_CREDENTIALS", "TELEGRAM_BOT_TOKEN"]
    
    print("\n📋 Environment Variables:")
    for var in env_vars:
        val = os.getenv(var)
        if val:
            print(f"   ✅ {var} = {val[:15]}...")
        else:
            print(f"   ❌ {var} = NOT SET")
    
    # Test each provider
    results = {}
    results["Claude Opus 4.6"] = await test_claude()
    results["NVIDIA Llama 3.3"] = await test_nvidia()
    results["Groq Llama 3.3"] = await test_groq()
    results["OpenRouter"] = await test_openrouter()
    
    # Summary
    print("\n" + "="*60)
    print("📊 DIAGNOSTIC SUMMARY")
    print("="*60)
    
    working = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, ok in results.items():
        status = "✅ ONLINE" if ok else "❌ OFFLINE"
        print(f"   {status} — {name}")
    
    print(f"\n   {working}/{total} providers working")
    
    if working == 0:
        print("\n   🚨 CRITICAL: All providers are down!")
        print("   Actions needed:")
        print("   1. Check .env file has valid API keys")
        print("   2. For Claude: ensure GCP credentials are configured")
        print("   3. For others: regenerate expired API keys")
    elif working < total:
        print(f"\n   ⚠️ {total - working} provider(s) need attention, but Nova can operate.")
    else:
        print("\n   🎉 All systems operational!")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
