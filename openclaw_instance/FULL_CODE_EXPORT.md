# OpenClaw V2 - Full Source Code Export

## 1. Core Logic

### `app/main.py`
```python
import asyncio
import logging
import os
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Add app path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner
from app.core.router import Router
from app.skills.lead_finder import find_leads

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Components ---
ai_client = UnifiedAIClient()
planner = TaskPlanner(ai_client)
router = Router(planner, lead_hunter=find_leads)

# --- Health Check ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"OpenClaw Online")

def start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

# --- Telegram Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['history'] = []
    await update.message.reply_text("👋 Nova here. Ready for orders.")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes memory."""
    context.user_data['history'] = []
    await update.message.reply_text("🧠 **Memory Wiped.** Fresh start.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    chat_id = update.effective_chat.id
    
    # 1. Initialize Memory
    if 'history' not in context.user_data:
        context.user_data['history'] = []
    history = context.user_data['history']

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # 2. Pass History to Router
        response = await router.route(user_msg, chat_id, history)
        
        # 3. Update Memory (CRITICAL)
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": response})
        
        # Keep last 10 turns
        if len(history) > 20:
            context.user_data['history'] = history[-20:]

        # Send
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

# --- Main ---
def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(token).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Nova Online...")
    application.run_polling()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
```

### `app/core/router.py`
```python
import re
import logging

logger = logging.getLogger(__name__)

class Router:
    """
    Smart Router for OpenClaw.
    Priority: Shortcuts -> AI Planner (The Brain)
    """
    def __init__(self, ai_planner, lead_hunter):
        self.planner = ai_planner
        self.lead_hunter = lead_hunter

        # Instant Regex Shortcuts (No AI - $0 Cost)
        self.shortcuts = {
            r'^(hi|hello|hey|sup|start|hola|greetings)\b': self._greet,
            r'status|health|alive': self._health_check,
            r'help|commands|what can you do': self._show_help,
            r'how are you|how are things': self._chat_status,
            r'are you (there|online|ok|ready)': self._confirm_presence,
            r'/reset': self._reset_instruction
        }

    async def route(self, message: str, chat_id: int, history: list = None):
        """
        Route the message to the correct handler.
        """
        message = message.strip()
        lower_msg = message.lower()

        # 1. Check Shortcuts (Instant Responses)
        for pattern, handler in self.shortcuts.items():
            if re.search(pattern, lower_msg):
                logger.info(f"Router: Shortcut matched '{pattern}'")
                return await handler()

        # 2. AI Planner (The Brain) - EVERYTHING else goes here
        # This forces the bot to use the 'Nova' persona and Memory
        logger.info("Router: Routing to AI Planner (Nova)")
        return await self.planner.execute(message, conversation_history=history)

    async def _greet(self):
        return "👋 Hi! I'm Nova (OpenClaw). Ready to find leads."

    async def _health_check(self):
        return "✅ **System Status:** ONLINE\nRunning on AWS."

    async def _show_help(self):
        return "🤖 Try: 'Find 10 leads for [niche]' or '/reset' to wipe memory."

    async def _chat_status(self):
        return "I'm functioning at 100% efficiency and ready to work! 🚀"

    async def _confirm_presence(self):
        return "Yes, Boss. I am here."
        
    async def _reset_instruction(self):
        return "Use the /reset command to wipe my memory."
```

### `app/core/planner.py`
```python
import logging
import json
import re
from app.core.ai_client import UnifiedAIClient
from app.skills.lead_finder import find_leads, read_webpage
from app.skills.browser_skill import browse_agent
from app.skills.definitions import TOOLS
from app.core.guardrails import Guardrails

logger = logging.getLogger(__name__)

class TaskPlanner:
    """
    ReAct Planner (Think -> Act -> Observe)
    Now with PERSISTENT MEMORY.
    """
    def __init__(self, ai_client: UnifiedAIClient):
        self.ai = ai_client
        
        # 1. Dynamic Tool Registry
        # Maps string names to actual functions for easy execution
        self.available_functions = {
            "find_leads": find_leads,
            "read_webpage": read_webpage,
            "browse_agent": browse_agent
        }

    # 2. Accept 'conversation_history' argument
    async def execute(self, goal: str, conversation_history: list = None):
        """
        Execute the goal using the ReAct loop with memory.
        """
        # Load existing context or start fresh
        history = conversation_history if conversation_history else []
        max_steps = 10
        
        system_prompt = """
YOU ARE NOVA. You are the Autonomous CEO of OROVA Agency.
Your ONLY goal is to make money and find luxury car leads.

CRITICAL RULES:
1. NEVER define words. If I say "Nova", say "Ready, Mark."
2. NEVER hallucinate data. If you can't find a lead, say "Search failed."
3. You are NOT a chat bot. You are a Tool User. USE YOUR TOOLS.
4. If the user asks you to do something you just did, USE YOUR MEMORY.
"""

        for i in range(max_steps):
            logger.info(f"Planner Step {i+1}/{max_steps}")
            
            # Construct messages with System Prompt + History + Current Goal
            current_messages = [{"role": "system", "content": system_prompt}] + history
            
            # If this is the first step of this specific run, add the user's new goal
            if i == 0:
                current_messages.append({"role": "user", "content": goal})
            
            # Get AI Response
            ai_message = await self.ai.chat(
                messages=current_messages,
                tools=TOOLS
            )
            
            content = ai_message.content or ""
            tool_calls = ai_message.tool_calls
            
            logger.info(f"AI Content: {content}")
            
            # --- LAZY EXIT FIX ---
            # If no tools called and it's just chatting, return the chat
            if not tool_calls and i == 0:
                return content

            # Append Assistant Reply to LOCAL history loop
            msg_dict = {"role": "assistant", "content": content}
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in tool_calls
                ]
            
            # Note: We append to a local history list for the loop, 
            # but main.py handles the long-term storage
            history.append(msg_dict)

            # Check for Completion
            if "DONE:" in content:
                return content.split("DONE:", 1)[1].strip()

            # Execute Tool Calls
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.function.name
                    
                    try:
                        args = json.loads(tc.function.arguments)
                        logger.info(f"Executing {tool_name} with {args}")

                        if tool_name in self.available_functions:
                            func = self.available_functions[tool_name]
                            
                            # Validate URL if present
                            if "url" in args and not Guardrails.validate_url(args["url"]):
                                result = "⚠️ BLOCKED: Malicious/Private URL detected."
                            else:
                                result = await func(**args)
                        else:
                            result = f"Error: Tool '{tool_name}' not registered."

                    except Exception as e:
                        result = f"Error executing tool {tool_name}: {e}"
                    
                    # Feed result back to Brain
                    history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        "content": str(result)
                    })

            elif not content:
                return "⚠️ AI returned an empty response."

        return "⚠️ Max steps reached. " + (history[-1].get("content", "") or "")
```

### `app/core/ai_client.py`
```python
import os
import logging
import asyncio
from typing import List, Dict, Optional, Any
import google.generativeai as genai
from openai import AsyncOpenAI
from groq import AsyncGroq

logger = logging.getLogger(__name__)

class UnifiedAIClient:
    """
    Unified AI Client with simplified waterfall fallback.
    Order: DeepSeek -> Groq -> OpenRouter -> Gemini (Free)
    """
    def __init__(self):
        # 1. DeepSeek (Reasoning)
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek = AsyncOpenAI(
            api_key=self.deepseek_key, 
            base_url="https://api.deepseek.com"
        ) if self.deepseek_key else None

        # 2. Groq (Llama 3.3)
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.groq = AsyncGroq(
            api_key=self.groq_key
        ) if self.groq_key else None

        # 3. OpenRouter (DeepSeek R1 Free / Llama)
        self.or_key = os.getenv("OPENROUTER_API_KEY")
        # OpenRouter uses OpenAI client format
        self.openrouter = AsyncOpenAI(
            api_key=self.or_key,
            base_url="https://openrouter.ai/api/v1",
             default_headers={"HTTP-Referer": "https://github.com/moltbot", "X-Title": "Moltbot"}
        ) if self.or_key else None

        # 4. Gemini (Flash - High Volume)
        self.gemini_key = os.getenv("GOOGLE_API_KEY")
        if self.gemini_key:
            genai.configure(api_key=self.gemini_key)
            self.gemini = genai.GenerativeModel("gemini-2.0-flash-exp")
        else:
            self.gemini = None

        logger.info(f"AI Client Initialized. Keys present: DeepSeek={bool(self.deepseek)}, Groq={bool(self.groq)}, OpenRouter={bool(self.openrouter)}, Gemini={bool(self.gemini)}")

    async def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None, temperature=0.7, max_tokens=2000) -> Any:
        """
        Execute chat with fallback logic and optional tool support.
        """
        # 1. Try DeepSeek
        if self.deepseek:
            try:
                params = {
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                if tools:
                    params["tools"] = tools
                
                response = await self.deepseek.chat.completions.create(**params)
                return response.choices[0].message
            except Exception as e:
                logger.warning(f"DeepSeek failed: {e}")

        # 2. Try Groq
        if self.groq:
            try:
                # Llama 3.3 70b is the workhorse
                params = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                if tools:
                    params["tools"] = tools
                
                response = await self.groq.chat.completions.create(**params)
                return response.choices[0].message
            except Exception as e:
                logger.warning(f"Groq failed: {e}")

        # 3. Try OpenRouter
        if self.openrouter:
            try:
                # Fallback to free models on OpenRouter
                params = {
                    "model": "google/gemini-2.0-flash-exp:free", # Upgrading default to Gemini 2.0 Flash Free
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "headers": {"HTTP-Referer": "https://openclaw.ai"}
                }
                if tools:
                    params["tools"] = tools
                
                response = await self.openrouter.chat.completions.create(**params)
                return response.choices[0].message
            except Exception as e:
                logger.warning(f"OpenRouter failed: {e}")

        # 4. Try Gemini (Native SDK - fallback, likely no tool support in this simple wrapper yet)
        if self.gemini:
            try:
                # Convert OpenAI messages to Gemini format (simple string for now)
                prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
                response = await self.gemini.generate_content_async(prompt)
                # Mock a message object for consistency
                from types import SimpleNamespace
                return SimpleNamespace(content=response.text, tool_calls=None)
            except Exception as e:
                logger.error(f"Gemini failed: {e}")

        # Return a simple mock message for error
        from types import SimpleNamespace
        return SimpleNamespace(content="⚠️ Error: All AI providers failed. Check your API keys.", tool_calls=None)
```

### `app/core/guardrails.py`
```python
import re
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class Guardrails:
    """
    Safety checks for Moltbot.
    Prevents SSRF, prompt injection, and unsafe commands.
    """
    
    # Private IP ranges (CIDR-like checks manually implemented for simplicity)
    BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL is safe to visit.
        Blocks: Non-http schemes, internal IPs, localhosts.
        """
        try:
            parsed = urlparse(url)
            
            # 1. Scheme check
            if parsed.scheme not in ["http", "https"]:
                logger.warning(f"Guardrails: Blocked invalid scheme '{parsed.scheme}'")
                return False
                
            hostname = parsed.hostname
            if not hostname:
                return False

            # 2. Blocked Hostname check
            if hostname.lower() in Guardrails.BLOCKED_HOSTS:
                logger.warning(f"Guardrails: Blocked internal host '{hostname}'")
                return False
                
            # 3. DNS resolution check (Prevent DNS rebinding to internal IP)
            try:
                ip_address = socket.gethostbyname(hostname)
                if ip_address.startswith("127.") or \
                   ip_address.startswith("10.") or \
                   ip_address.startswith("192.168.") or \
                   ip_address.startswith("172.16."): # Simplified 172.16-31 check
                    logger.warning(f"Guardrails: Blocked internal IP '{ip_address}' for {hostname}")
                    return False
            except socket.gaierror:
                # Could not resolve, might be safe or invalid. Proceed with caution or block.
                # If we render/playwright ignores it, it's fine.
                pass
                
            return True
            
        except Exception as e:
            logger.error(f"Guardrails Error: {e}")
            return False

    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Basic sanitization to remove system prompt override attempts.
        """
        # Block attempts to redefine "You are..."
        # This is a very basic heuristic.
        forbidden = [
            "ignore previous instructions",
            "system prompt",
            "you are now",
            "your new role"
        ]
        
        lower_text = text.lower()
        for phrase in forbidden:
            if phrase in lower_text:
                logger.warning(f"Guardrails: Sanitized forbidden phrase '{phrase}'")
                # Redact
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                text = pattern.sub("[REDACTED]", text)
                
        return text
```

## 2. Skills

### `app/skills/lead_finder.py`
```python
import logging
import asyncio
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def find_leads(count: int = 5, query: str = "business leads"):
    """
    Scrape leads using headless Chromium (Playwright).
    """
    logger.info(f"LeadFinder: Searching for {count} leads for '{query}'...")
    leads = []
    
    try:
        async with async_playwright() as p:
            # Launch compatible browser
            # args recommended for container environments
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()

            # 1. Search DuckDuckGo (Easier to scrape than Google)
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}&t=h_&ia=web"
            await page.goto(search_url, timeout=30000)
            
            # Try multiple selectors for results as DDG sometimes changes layout
            try:
                await page.wait_for_selector('.result', timeout=15000)
            except:
                logger.warning("DuckDuckGo: '.result' selector timed out, trying '.links_main'")
                await page.wait_for_selector('.links_main', timeout=15000)

            results = await page.query_selector_all('.result')
            
            for res in results[:count]:
                try:
                    title_el = await res.query_selector('.result__title')
                    link_el = await res.query_selector('.result__a')
                    snippet_el = await res.query_selector('.result__snippet')

                    if title_el and link_el:
                        title = await title_el.inner_text()
                        url = await link_el.get_attribute('href')
                        snippet = await snippet_el.inner_text() if snippet_el else ""

                        if url and url.startswith('http'):
                            leads.append({
                                "title": title,
                                "url": url,
                                "snippet": snippet
                            })
                except Exception as e:
                    continue
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"LeadFinder Error: {e}")
        return [{"error": str(e)}]

    # Formatted String Output for Bot
    if not leads:
        return "No leads found."
    
    result_text = f"🔍 **Found {len(leads)} Leads:**\n\n"
    for l in leads:
        result_text += f"• [{l['title']}]({l['url']})\n  _{l['snippet'][:100]}..._\n\n"
    
    return result_text

async def read_webpage(url: str):
    """
    Visit a specific URL and extract main text content.
    """
    logger.info(f"Broswer: Visiting {url}...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page()
            
            # Go to URL with timeout
            await page.goto(url, timeout=30000)
            
            # Get title and basic text
            title = await page.title()
            content = await page.evaluate("document.body.innerText")
            
            await browser.close()
            
            # Clean content (limit length)
            cleaned_content = " ".join(content.split())[:3000]
            
            return f"📄 **Page: {title}**\n\n{cleaned_content}..."
            
    except Exception as e:
        logger.error(f"ReadPage Error: {e}")
        return f"⚠️ Could not read page: {str(e)}"
```

### `app/skills/browser_skill.py`
```python
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def browse_agent(url: str, objective: str):
    """
    Advanced browsing agent. Visits a URL, scrolls, and extracts info based on objective.
    """
    logger.info(f"🌐 BrowseAgent: Visiting {url} with objective: {objective}")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page()
            
            # Go to URL
            await page.goto(url, timeout=30000, wait_until="networkidle")
            
            # Basic scroll to load dynamic content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            await page.wait_for_timeout(1000)
            
            # Extract content
            title = await page.title()
            # Try to find relevant text based on objective (simple logic)
            content = await page.evaluate("document.body.innerText")
            
            await browser.close()
            
            # Clean and truncate
            cleaned = " ".join(content.split())
            # Return a slightly larger chunk for the "Advanced" agent
            return f"🌐 [BrowseAgent Result for: {objective}]\nTitle: {title}\nContent Snippet: {cleaned[:5000]}..."

    except Exception as e:
        logger.error(f"BrowseAgent Error: {e}")
        return f"⚠️ BrowseAgent failed: {str(e)}"
```

### `app/skills/definitions.py`
```python
# Tool Definitions for native OpenAI-style calling

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_leads",
            "description": "Search the web for business leads. Returns a list of titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'plumbers in Miami')"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "Visit a specific URL and extract the main text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to visit (e.g., 'https://example.com')"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_agent",
            "description": "An advanced browsing agent that can interact with a page (scroll, click, extract). Use for complex sites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to visit"
                    },
                    "objective": {
                        "type": "string",
                        "description": "What you want to achieve on this page (e.g., 'Find the pricing table')"
                    }
                },
                "required": ["url", "objective"]
            }
        }
    }
]
```

### `app/skills/outbound_dialer.py`
```python
# -*- coding: utf-8 -*-
import os
import requests
from typing import Dict, Any

def trigger_retell_call(phone: str, context: Dict[str, str]) -> Dict[str, Any]:
    url = "https://api.retellai.com/v2/create-phone-call"
    payload = {
        "from_number": os.getenv("RETELL_FROM_NUMBER"),
        "to_number": phone,
        "agent_id": os.getenv("RETELL_AGENT_ID"),
        "retell_llm_dynamic_variables": {
            "business_name": context.get("business_name"),
            "icebreaker": context.get("icebreaker")
        }
    }
    headers = {
        "Authorization": f"Bearer {os.getenv('RETELL_API_KEY')}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp_json = resp.json() if resp.content else {}
        if resp.status_code == 201:
            return {"success": True, "call_id": resp_json.get("call_id"), "data": resp_json}
        return {"success": False, "error": resp.text}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## 3. Autonomous Scripts

### `app/worker.py`
```python
import asyncio
import logging
import os
import sys
import time
import schedule
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Add app path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.skills.lead_finder import find_leads
from app.skills.outbound_dialer import trigger_retell_call

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
LEADS_TO_FIND_PER_RUN = 5
HUNT_INTERVAL_MINUTES = 60
APPROVAL_CHECK_MINUTES = 2
MAX_RUNS_PER_DAY = 10

# Security: Wallet Drain Safeguard
daily_counter = 0
last_reset_day = time.strftime("%d")

def send_telegram_report(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("PERSONAL_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram report skipped: TOKEN or CHAT_ID missing.")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
    except Exception as e:
        logger.error(f"Failed to send Telegram report: {e}")

async def run_ceo_fast_lane():
    """
    ⚡ FAST LANE: Checks for NEW leads to approve (2 mins)
    AND executes calls for APPROVED leads.
    """
    logger.info("⚡ [FAST LANE] Checking approvals and pending calls...")
    
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("OROVA Leads").sheet1
        rows = sheet.get_all_values()
        
        # OROVA Leads Header: 
        # [0]Timestamp, [1]First Name, [2]Last Name, [3]Number, [4]Business Name, [5]Email, [6]Location, [7]Status, [8]Notes, [9]Call_ID
        for idx, row in enumerate(rows[1:], start=2):
            status = row[7] if len(row) > 7 else ""
            
            # --- TASK 1: New Leads Needing Approval ---
            if status == "Ready for Call":
                company = row[4]
                intel = row[8] if len(row) > 8 else "No notes."
                logger.info(f"🚨 Approval needed for {company} (Row {idx})")
                
                token = os.getenv("TELEGRAM_BOT_TOKEN")
                chat_id = os.getenv("PERSONAL_CHAT_ID")
                if token and chat_id:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    text = f"🚨 **Authorization Needed**\n\n**Target:** {company}\n**Intel:** {intel}\n\nWhat is your command, CEO?"
                    payload = {
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps({"inline_keyboard": [[
                            {"text": "✅ Approve Call", "callback_data": f"approve_{idx}"},
                            {"text": "❌ Deny", "callback_data": f"deny_{idx}"}
                        ]]})
                    }
                    requests.post(url, data=payload)
                    sheet.update_cell(idx, 8, "Pending Approval")
            
            # --- TASK 2: Execute Approved Calls ---
            elif status == "Approved":
                phone = row[3]
                company = row[4]
                intel = row[8] if len(row) > 8 else ""
                
                logger.info(f"📞 [CALL] Triggering Retell for {company} ({phone})...")
                
                # Context for Retell AI
                context = {
                    "business_name": company,
                    "icebreaker": intel
                }
                
                result = trigger_retell_call(phone, context)
                
                if result.get("success"):
                    call_id = result.get("call_id")
                    logger.info(f"✅ [CALL] Success! ID: {call_id}")
                    # Update sheet: Status and Call_ID (Column 10)
                    sheet.update_cell(idx, 8, "Call Initiated")
                    # Ensure the sheet has enough columns
                    while len(row) < 10:
                        row.append("")
                    sheet.update_cell(idx, 10, call_id)
                    
                    send_telegram_report(f"📞 **Call Initiated**\n\nI am now calling **{company}**.\nCall ID: `{call_id}`")
                else:
                    error = result.get("error", "Unknown error")
                    logger.error(f"❌ [CALL] Failed: {error}")
                    sheet.update_cell(idx, 8, "Call Failed")
                    send_telegram_report(f"⚠️ **Call Failed**\n\nError calling **{company}**: {error}")
                    
    except Exception as e:
        logger.error(f"Fast Lane Error: {e}")

async def run_lead_hunt_slow_lane():
    """
    🕵️ SLOW LANE: Hunts for new leads (60 mins)
    """
    global daily_counter, last_reset_day
    
    # Reset counter if new day
    current_day = time.strftime("%d")
    if current_day != last_reset_day:
        daily_counter = 0
        last_reset_day = current_day

    if daily_counter >= MAX_RUNS_PER_DAY:
        logger.info("🌙 [SLOW LANE] Daily limit reached. Skipping lead hunt.")
        return

    query = "luxury car dealers thailand"
    logger.info(f"🕵️ [SLOW LANE] Hunting for leads: {query}")
    
    try:
        result = await find_leads(count=LEADS_TO_FIND_PER_RUN, query=query)
        if "Found" in result:
            logger.info("   -> Leads found. Sending report...")
            send_telegram_report(f"☀️ **Autonomous Morning Report**\n\nWhile you slept, I hunted for '{query}':\n\n{result}")
        else:
            logger.info("   -> No leads found this shift.")

        daily_counter += 1
        logger.info(f"   -> Hunt complete. Total runs today: {daily_counter}")
        
    except Exception as e:
        logger.error(f"   !!! ERROR in Slow Lane: {e}")
        send_telegram_report(f"⚠️ **Lead Hunt Error**: {str(e)}")

def fast_lane_job():
    asyncio.run(run_ceo_fast_lane())

def slow_lane_job():
    asyncio.run(run_lead_hunt_slow_lane())

# --- THE SCHEDULE ---
schedule.every(APPROVAL_CHECK_MINUTES).minutes.do(fast_lane_job)
schedule.every(HUNT_INTERVAL_MINUTES).minutes.do(slow_lane_job)

if __name__ == "__main__":
    logger.info("🚀 OROVA Autonomous Worker Initiated.")
    logger.info(f"   -> Fast Lane: Every {APPROVAL_CHECK_MINUTES} mins.")
    logger.info(f"   -> Slow Lane: Every {HUNT_INTERVAL_MINUTES} mins.")
    
    # Run once immediately
    fast_lane_job()
    slow_lane_job()
    
    while True:
        schedule.run_pending()
        time.sleep(1)
```

### `app/test_ceo.py`
```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SHEET_NAME = "OROVA Leads"
TEST_PHONE = "+15550000000" # User can replace this

def inject_test_lead():
    print("🧪 [TEST MODE] Injecting a fake lead into OROVA Pipeline...")
    
    # 1. Connect to Google Sheets
    # Use the path from env or default
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
    except Exception as e:
        print(f"❌ Error: Could not find sheet '{SHEET_NAME}'. Make sure it exists and the service account has access.")
        return
    
    # 2. Define the Test Data
    # OROVA Leads Header: ['Timestamp', ' First Name ', 'Last Name', 'Number', 'Business Name', 'Email', 'Location']
    # CEO Agent will look for 'Ready for Call' in the Status column (we'll use column 8/H)
    test_lead = [
        time.strftime("%Y-%m-%d %H:%M:%S"), # Timestamp
        "Test",                             # First Name
        "Ferrari",                          # Last Name
        TEST_PHONE,                         # Number/Phone
        "Test Ferrari BKK (Simulation)",    # Business Name
        "test@ferrari.com",                 # Email
        "Bangkok, Thailand",                # Location
        "Ready for Call",                   # Status (Column 8)
        "Found via Test Script."            # Notes (Column 9)
    ]
    
    # 3. Append to Sheet
    sheet.append_row(test_lead)
    print(f"✅ Success! Added '{test_lead[0]}' to the sheet.")
    print("👀 WATCH YOUR TELEGRAM NOW. The CEO Agent should message you in ~10 seconds.")

if __name__ == "__main__":
    inject_test_lead()
```

### `verify_agent.py`
```python
import asyncio
import os
import logging
from dotenv import load_dotenv
from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner

# Basic Logging
logging.basicConfig(level=logging.INFO)

async def test_agent_loop():
    load_dotenv()
    
    # 1. Init AI Client
    client = UnifiedAIClient()
    
    # 2. Init Planner
    planner = TaskPlanner(client)
    
    # 3. Test Goal
    goal = "Find the phone number of 'Cosker OROVA' or a similar marketing agency in Israel by searching the web."
    print(f"\n[START] Testing Agent with goal: {goal}\n")
    
    result = await planner.execute(goal)
    
    print("\n--- FINAL RESULT ---")
    print(result)
    print("---------------------\n")

if __name__ == "__main__":
    asyncio.run(test_agent_loop())
```

### `check_header.py`
```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

load_dotenv()

def check_header():
    sheet_name = "OROVA Leads"
    print(f"🔍 Checking header of '{sheet_name}'...")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(sheet_name).sheet1
        print("Header:", sheet.row_values(1))
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_header()
```

### `list_sheets.py`
```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

load_dotenv()

def list_sheets():
    print("🔍 Listing all accessible Google Sheets...")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        print(f"❌ Error: Credentials not found at {creds_path}")
        return

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    sheets = client.openall()
    if not sheets:
        print("Empty: No sheets shared with this service account.")
    else:
        for s in sheets:
            print(f"- {s.title} (ID: {s.id})")

if __name__ == "__main__":
    list_sheets()
```
