# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Telegram Notification System
Sends alerts to Telegram chat for high-score leads and safety triggers.
"""

import os
import logging
import telebot

logger = logging.getLogger(__name__)

# Telegram settings from environment
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

bot = None
if TELEGRAM_BOT_TOKEN:
    try:
        bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
        logger.info("Telegram bot initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Telegram bot: {e}")
else:
    logger.warning("TELEGRAM_BOT_TOKEN not set, notifications disabled")

def send_telegram_alert(message: str):
    """Send a message to the configured Telegram chat."""
    if not bot or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured, skipping alert")
        return

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        logger.info("Telegram alert sent")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

def alert_high_score_lead(business_name: str, score: float, vertical: str):
    """Alert for leads with score >9 (out of 10)."""
    if score > 9:
        message = f"🚨 **High-Score Lead Alert**\n\nBusiness: {business_name}\nScore: {score}/10\nVertical: {vertical}\n\nImmediate action recommended!"
        send_telegram_alert(message)

def alert_safety_trigger(trigger_type: str, details: str):
    """Alert for safety switch triggers."""
    message = f"⚠️ **Safety Switch Triggered**\n\nType: {trigger_type}\nDetails: {details}\n\nReview immediately!"
    send_telegram_alert(message)