# -*- coding: utf-8 -*-
"""
MikeBot Notifier
Dedicated module for sending robust Telegram alerts.
"""
import os
import logging
import asyncio
import sys
import io
from telegram import Bot

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Notifier")

async def send_alert(message: str):
    """
    Send a robust alert to the admin's Telegram.
    Safe to use from any async context.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    user_id = os.environ.get("TELEGRAM_USER_ID") or "6656533875"  # Fallback to Mark's ID if missing
    
    if not token:
        print("❌ TELEGRAM ERROR: No TELEGRAM_BOT_TOKEN found in env")
        return False
        
    try:
        bot = Bot(token=token)
        await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
        logger.info(f"✅ Alert sent to {user_id}")
        return True
    except Exception as e:
        print(f"❌ TELEGRAM ERROR: {str(e)}")
        # In a real error handler bot, we would also log the traceback
        # traceback.format_exc()
        return False
