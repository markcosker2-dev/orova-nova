import os
import asyncio
import json
import logging
import sys
from dotenv import load_dotenv
from app.skills.definitions import TOOLS

# Force UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_groq_with_tools():
    print("Testing Groq Llama 3.3 with TOOLS...")
    
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("❌ GROQ_API_KEY not set")
        return

    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=key)
        
        # Simple test: ask for something that requires a tool
        messages = [
            {"role": "system", "content": "You are a helpful assistant with access to tools."},
            {"role": "user", "content": "Search for 'best pizza in New York' on Google."}
        ]
        
        # Tools are defined in definitions.py - passing them directly
        print(f"Sending request with {len(TOOLS)} tools defined...")
        
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=1000
        )
        
        print("\nResponse received:")
        choice = response.choices[0]
        msg = choice.message
        
        if msg.tool_calls:
            print("✅ Tool Calls:")
            for tc in msg.tool_calls:
                print(f"   - {tc.function.name}({tc.function.arguments})")
        else:
            print(f"⚠️ No tool calls. Content: {msg.content}")
            
    except Exception as e:
        print(f"❌ Groq Failed with Tools: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_groq_with_tools())
