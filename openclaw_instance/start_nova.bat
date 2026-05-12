@echo off
color 0A
cls

echo.
echo  ================================================================
echo  ^|                                                              ^|
echo  ^|     ::::    :::  ::::::::  :::     :::    :::                ^|
echo  ^|     :+:+:   :+: :+:    :+: :+:     :+:  :+: :+:             ^|
echo  ^|     :+:+:+  +:+ +:+    +:+ +:+     +:+ +:+   +:+            ^|
echo  ^|     +#+ +:+ +#+ +#+    +:+ +#+     +#++#++:++#++:            ^|
echo  ^|     +#+  +#+#+# +#+    +#+  +#+   +#+ +#+     +#+            ^|
echo  ^|     #+#   #+#+# #+#    #+# #+#  #+#  #+#     #+#            ^|
echo  ^|     ###    ####  ########   #####   ###     ###              ^|
echo  ^|                                                              ^|
echo  ^|     OROVA AUTONOMOUS CEO - ANTIGRAVITY EDITION               ^|
echo  ^|     Claude Opus 4.6 ^| Kimi K2 ^| Groq ^| OpenRouter          ^|
echo  ^|                                                              ^|
echo  ================================================================
echo.

echo  [1/4] Updating Dependencies...
echo  ---------------------------------------------------------------
pip install -q --upgrade anthropic[vertex] google-cloud-aiplatform 2>nul
pip install -q --upgrade python-telegram-bot playwright beautifulsoup4 openai groq google-generativeai python-dotenv ddgs tavily-python agentmail 2>nul
echo  [OK] Dependencies updated.
echo.

echo  [2/4] Installing Browser Engine...
echo  ---------------------------------------------------------------
playwright install chromium 2>nul
echo  [OK] Chromium ready.
echo.

echo  [3/4] Model Chain Status
echo  ---------------------------------------------------------------
echo  [PRIMARY]    Claude Opus 4.6   (Vertex AI / Antigravity)
echo  [FALLBACK 1] Kimi K2            (NVIDIA API)
echo  [FALLBACK 2] Groq Llama 3.3    (API)
echo  [EMERGENCY]  OpenRouter Free   (API)
echo.

echo  [4/4] Skill Arsenal (28 Tools)
echo  ---------------------------------------------------------------
echo  SEARCH:      find_leads, read_webpage, browse_agent, google_search
echo  RESEARCH:    deep_research, research_lead, analyze_competitor
echo  CONTENT:     write_content, optimize_post, compare_competitors
echo  GMAIL:       get_inbox, send_email, search_emails
echo  AGENTMAIL:   create_inbox, send_outreach, check_replies, reply_to_email
echo  CALENDAR:    get_today, get_week, create_event, update_event, delete_event
echo  SALES:       get_orova_prompt, advanced_browser
echo  SHEETS:      append_to_sheet, create_new_sheet
echo  APPROVAL:    request_approval, list_pending
echo.

echo  ================================================================
echo  ^|  NOVA IS ONLINE. ALL SYSTEMS GO.                             ^|
echo  ================================================================
echo.
python app/main.py
pause
