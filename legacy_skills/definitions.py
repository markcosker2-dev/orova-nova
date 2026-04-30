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
