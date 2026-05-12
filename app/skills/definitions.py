# Tool Definitions for Nova AI - Antigravity Edition
# Claude Opus 4.6 | Gemini 3 Pro | Gemini 3 Flash

TOOLS = [
    # ─── SEARCH & BROWSE ─────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "find_leads",
            "description": "Search the web for business leads. Returns a list of titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query (e.g., 'plumbers in Miami')"},
                    "count": {"type": "integer", "description": "Number of results to return (default 5)"}
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
                    "url": {"type": "string", "description": "The full URL to visit"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_agent",
            "description": "Advanced browsing agent that can interact with a page (scroll, click, extract).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to visit"},
                    "objective": {"type": "string", "description": "What you want to achieve on this page"}
                },
                "required": ["url", "objective"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "Perform a Google search (scraper) to find information when other methods fail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "limit": {"type": "integer", "description": "Number of results (default 5)"}
                },
                "required": ["query"]
            }
        }
    },
    # ─── RESEARCH & INTELLIGENCE ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": "Run autonomous multi-step research on a topic. Searches multiple queries, reads pages, and compiles a report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to research"},
                    "depth": {"type": "string", "description": "Research depth: quick, standard, or deep"}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_lead",
            "description": "Deep-dive a specific lead URL: extract info, score 1-10 for OROVA fit, suggest outreach.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The lead's website URL to research"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_competitor",
            "description": "Analyze a competitor's online presence, ads, messaging, and strategy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "The competitor company name"}
                },
                "required": ["company_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_competitors",
            "description": "Compare multiple competitors side-by-side.",
            "parameters": {
                "type": "object",
                "properties": {
                    "companies": {"type": "string", "description": "Comma-separated company names to compare"}
                },
                "required": ["companies"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_seo_audit",
            "description": "Run a technical and on-page SEO audit of a website. Checks score, speed, and mobile-readiness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to audit"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_retell_call",
            "description": "Trigger an AI voice call (Retell AI) to a lead for intro or voicemail drop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Recipient phone number"},
                    "context": {
                        "type": "object",
                        "properties": {
                            "business_name": {"type": "string"},
                            "icebreaker": {"type": "string"}
                        }
                    }
                },
                "required": ["phone", "context"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_ai_image",
            "description": "Generate an AI image for marketing content or Instagram posts. Uses brand guidelines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Detailed visual prompt for the image"},
                    "platform": {"type": "string", "description": "Platform to pull guidelines for (default: instagram)"}
                },
                "required": ["prompt"]
            }
        }
    },
    # ─── CONTENT & SOCIAL ────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "write_content",
            "description": "Generate marketing content: email, blog, newsletter, social post, or sales script.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The content topic"},
                    "content_type": {"type": "string", "description": "Type: email, blog, newsletter, social, script"}
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_post",
            "description": "Optimize a social media post for a specific platform's algorithm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The post text to optimize"},
                    "platform": {"type": "string", "description": "Platform: twitter, linkedin, instagram, facebook"}
                },
                "required": ["text"]
            }
        }
    },
    # ─── GMAIL ───────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_inbox",
            "description": "Get unread emails from Gmail inbox",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer"},
                    "unread_only": {"type": "boolean"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email using Gmail",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["to_email", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search Gmail for emails matching a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query (e.g., 'from:john subject:meeting')"}
                },
                "required": ["query"]
            }
        }
    },
    # ─── CALENDAR ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_today",
            "description": "Get today's calendar events",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create a calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title"},
                    "start_time": {"type": "string", "description": "ISO format or natural language"},
                    "duration_minutes": {"type": "integer"}
                },
                "required": ["summary", "start_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_week",
            "description": "Get this week's calendar events.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_event",
            "description": "Update an existing calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event ID to update"},
                    "summary": {"type": "string", "description": "New title"},
                    "start_time": {"type": "string", "description": "New start time"}
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Delete a calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event ID to delete"}
                },
                "required": ["event_id"]
            }
        }
    },
    # ─── OROVA SALES ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_orova_prompt",
            "description": "Get the master OROVA sales script for a specific lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_name": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "advanced_browser",
            "description": "Powerful browser agent for complex tasks. Navigates and performs deep extraction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The target URL"},
                    "objective": {"type": "string", "description": "What to achieve on the site"}
                },
                "required": ["url", "objective"]
            }
        }
    },
    # ─── GOOGLE SHEETS ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "append_to_sheet",
            "description": "Append rows of data to a Google Sheet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {"type": "string", "description": "Name of the Google Sheet"},
                    "rows": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                        "description": "List of rows to append."
                    }
                },
                "required": ["sheet_name", "rows"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_new_sheet",
            "description": "Create a new Google Sheet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_name": {"type": "string"}
                },
                "required": ["sheet_name"]
            }
        }
    },
    # ─── APPROVAL WORKFLOW ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": "Request Mark's approval before executing a critical action. Sends a Telegram message for Mark to approve or reject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "What action needs approval (e.g., 'Send 50 cold emails')"},
                    "details": {"type": "string", "description": "Details about the action"}
                },
                "required": ["action", "details"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending",
            "description": "List all pending approval requests.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    # ─── AGENTMAIL (Nova's Own Email) ─────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_inbox",
            "description": "Create a new AgentMail inbox for Nova. Returns the inbox email address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username for the inbox (default: nova-orova)"},
                    "display_name": {"type": "string", "description": "Display name (default: Nova | OROVA)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_outreach",
            "description": "Send an email from Nova's own AgentMail inbox. Use this for cold outreach instead of Mark's Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body text"}
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_replies",
            "description": "Check Nova's AgentMail inbox for new messages and replies from leads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max messages to return (default: 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reply_to_email",
            "description": "Reply to a specific email in Nova's inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The message ID to reply to"},
                    "body": {"type": "string", "description": "Reply text"}
                },
                "required": ["message_id", "body"]
            }
        }
    },
    # ─── FOLLOW-UP SEQUENCES (Quill) ───────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generate_sequence",
            "description": "Generate a multi-step follow-up email sequence for a prospect. Types: cold_intro, warm_followup, re_engage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prospect": {"type": "object", "description": "Prospect dict with keys: first_name, company, industry, location, email"},
                    "sequence_type": {"type": "string", "description": "Sequence type: cold_intro, warm_followup, or re_engage"}
                },
                "required": ["prospect"]
            }
        }
    },
    # ─── PROPOSAL GENERATION (Closer) ──────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generate_proposal",
            "description": "Generate a Grand Slam Offer proposal for a prospect. Tiers: starter ($1,500/mo), growth ($3,500/mo), empire ($7,500/mo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "Target company name"},
                    "contact_name": {"type": "string", "description": "Contact person name"},
                    "industry": {"type": "string", "description": "Business vertical/industry"},
                    "tier": {"type": "string", "description": "Pricing tier: starter, growth, or empire"},
                    "pain_points": {"type": "array", "items": {"type": "string"}, "description": "List of identified pain points"},
                    "audit_findings": {"type": "string", "description": "SEO/competitor audit results to include"}
                },
                "required": ["company", "contact_name", "industry"]
            }
        }
    },
    # ─── PERFORMANCE DASHBOARD (Sentinel) ──────────────────────────
    {
        "type": "function",
        "function": {
            "name": "weekly_report",
            "description": "Generate the OROVA CEO Pulse weekly performance report with pipeline metrics.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_metric",
            "description": "Increment a performance metric counter. Metrics: leads_found, emails_sent, replies_received, meetings_booked, calls_made, proposals_sent, content_created.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string", "description": "Metric to increment"},
                    "increment": {"type": "integer", "description": "Amount to add (default 1)"}
                },
                "required": ["metric_name"]
            }
        }
    },
    # ─── AGENT DISPATCH (Nova) ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "dispatch_task",
            "description": "Route a task to the correct specialized sub-agent (Atlas, Pixel, Quill, Hawk, Closer, Sentinel, Echo, Oracle, Viper).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "Description of the task to route"}
                },
                "required": ["task_description"]
            }
        }
    },
    # ─── STEALTH SCRAPING (Viper) ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "stealth_search",
            "description": "Search the web using anti-bot stealth mode (Scrapling). Bypasses Cloudflare and other protections. Use for sites that block regular scrapers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "count": {"type": "integer", "description": "Number of results (default 10)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stealth_extract",
            "description": "Visit a URL with full anti-bot bypass and extract contact info (phones, emails, owner names). Use for protected sites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Target URL to extract from"},
                    "selectors": {"type": "string", "description": "Optional CSS selectors (comma-separated)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_scrape",
            "description": "Scrape multiple URLs in parallel with stealth anti-bot bypass. Max 20 URLs per run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "string", "description": "Comma-separated list of URLs to scrape"},
                    "objective": {"type": "string", "description": "What to extract from each page"}
                },
                "required": ["urls"]
            }
        }
    },
    # ─── DRIP CAMPAIGNS (Quill) ───────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_drip_campaign",
            "description": "Generate a multi-step email drip campaign. Types: cold_intro_drip (5 emails), nurture_7day (3 emails), re_engage_30day (2 emails), post_meeting (2 emails).",
            "parameters": {
                "type": "object",
                "properties": {
                    "prospect": {
                        "type": "object",
                        "description": "Prospect dict with keys: first_name, company, industry, location, email",
                        "properties": {
                            "first_name": {"type": "string"},
                            "company": {"type": "string"},
                            "industry": {"type": "string"},
                            "location": {"type": "string"},
                            "email": {"type": "string"}
                        }
                    },
                    "sequence_type": {"type": "string", "description": "Sequence: cold_intro_drip, nurture_7day, re_engage_30day, post_meeting"}
                },
                "required": ["prospect"]
            }
        }
    },
    # ─── COPYWRITING (Quill) ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "write_cold_email",
            "description": "Generate a cold email using marketing psychology frameworks (AIDA, PAS, BAB, StoryBrand, 4Ps).",
            "parameters": {
                "type": "object",
                "properties": {
                    "prospect": {"type": "string", "description": "Company or prospect name"},
                    "framework": {"type": "string", "description": "Framework: aida, pas, bab, story_brand, 4ps (default: pas)"},
                    "industry": {"type": "string", "description": "Target industry"},
                    "offer": {"type": "string", "description": "What you're offering"}
                },
                "required": ["prospect"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_ad_copy",
            "description": "Generate platform-optimized ad copy using marketing frameworks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "offer": {"type": "string", "description": "The offer to advertise"},
                    "platform": {"type": "string", "description": "Platform: facebook, google, linkedin, instagram"},
                    "industry": {"type": "string", "description": "Target industry"},
                    "framework": {"type": "string", "description": "Framework: aida, pas, bab, 4ps"}
                },
                "required": ["offer"]
            }
        }
    },
    # ─── ANALYTICS (Oracle) ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "pipeline_report",
            "description": "Generate a comprehensive pipeline analytics report: full funnel metrics, conversion rates, trends, and recommendations.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "conversion_analysis",
            "description": "Analyze conversion rates at each pipeline stage with industry benchmarks (Lead→Email, Email→Reply, Reply→Meeting).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "roi_calculator",
            "description": "Calculate ROI, ROAS, and estimated pipeline value. Provide spend and revenue for actual ROI, or call with no args for pipeline estimate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spend": {"type": "number", "description": "Total marketing spend in USD"},
                    "revenue": {"type": "number", "description": "Total revenue generated in USD"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_client_ads",
            "description": "Monitor a client's Meta Ad Account performance (spend, leads, CPL) and check for budget drain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "integer"},
                    "ad_account_id": {"type": "string", "description": "Meta Ad Account ID (e.g., '1234567890')"},
                    "access_token": {"type": "string"},
                    "cpl_threshold": {"type": "number", "description": "Maximum allowed Cost Per Lead before warning (default 50.0)"}
                },
                "required": ["client_id", "ad_account_id", "access_token"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pause_meta_campaign",
            "description": "Emergency pause of a Meta Ad Campaign to prevent further budget loss.",
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_id": {"type": "string", "description": "ID of the campaign to pause"},
                    "access_token": {"type": "string"}
                },
                "required": ["campaign_id", "access_token"]
            }
        }
    },
    # ─── PIPELINE ORCHESTRATION ───────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "run_pipeline",
            "description": "Execute a multi-step autonomous pipeline. Pipelines: full_outreach (find→research→draft), morning_report (replies→analytics→report), competitor_blitz (find→audit→compare), lead_enrich (extract→research→save).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_name": {"type": "string", "description": "Pipeline: full_outreach, morning_report, competitor_blitz, lead_enrich"},
                    "params": {"type": "string", "description": "Optional JSON override params"}
                },
                "required": ["pipeline_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_pipelines",
            "description": "List all available multi-step pipelines with descriptions and steps.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]


