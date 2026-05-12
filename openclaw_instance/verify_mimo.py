import asyncio
import os
import logging
from app.core.ai_client import UnifiedAIClient
from app.core.config import cfg

# Set up logging to see the AI client's internal messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mimo_brain():
    print("\n🧠 --- MiMo v2 Pro Connection Test ---")
    print(f"📡 Endpoint: {cfg.mimo_base_url}")
    print(f"🎟️ API Key Present: {bool(cfg.mimo_api_key)}")
    
    client = UnifiedAIClient()
    
    # Verify Initialization
    if not client.mimo_client:
        print("❌ FAILED: MiMo client did not initialize correctly. Check MIMO_API_KEY in .env")
        return

    # Test Chat
    print("\n💬 Sending test request to MiMo v2 Pro...")
    try:
        # Prompt Nova to identify herself with the new brain
        response = await client.chat(
            messages="Who is OROVA and what is your current brain model?",
            role="reasoner"
        )
        
        print("\n✅ SUCCESS! MiMo responded:")
        print(f"--------------------------------------------------")
        print(response.content)
        print(f"--------------------------------------------------")
        
        if "MiMo" in response.content or "v2" in response.content or "Xiaomi" in response.content:
            print("\n🟢 VERIFIED: The AI has correctly identified its new MiMo architecture.")
        else:
            print("\n🟡 NOTE: The AI responded, but didn't explicitly mention MiMo. This is normal for some models.")
            
    except Exception as e:
        print(f"\n❌ ERROR during chat: {e}")

if __name__ == "__main__":
    asyncio.run(test_mimo_brain())
