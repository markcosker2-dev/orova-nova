# -*- coding: utf-8 -*-
"""
Tweet Writer Skill for OROVA Moltbot
Based on 'tweet-writer' from Awesome-OpenClaw Skills.
"""
import json
import os
from app.mikebot import OpenRouterClient, load_config

class TweetWriter:
    """
    Generates viral X/Twitter content using proven frameworks.
    """
    def __init__(self):
        self.config = load_config()
        self.api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        if self.api_key:
            self.client = OpenRouterClient(self.api_key)
        else:
            self.client = None
    
    def generate_tweets(self, topic: str, style: str = "listicle") -> str:
        """
        Generate a viral tweet or thread based on a topic.
        
        Styles:
        - listicle: "7 ways to..." (High Engagement)
        - contrarian: "Unpopular opinion..."
        - story: "How I went from..."
        - framework: "The X Method..."
        """
        if not self.client:
            return "Error: No API Key configured for TweetWriter."

        # Frameworks from Audit
        frameworks = {
            "listicle": "Format: The Listicle. Hook promise + numbered items + takeaway.",
            "contrarian": "Format: The Contrarian Take. State a widely held belief, then dismantle it.",
            "story": "Format: The Story Hook. Transformation (Before -> After) + The Journey.",
            "framework": "Format: The Educational Framework. Step-by-step guide."
        }
        
        selected_framework = frameworks.get(style, frameworks["listicle"])
        
        prompt = f"""
You are a viral ghostwriter for X (Twitter).
Topic: "{topic}"
Style: {style}
{selected_framework}

Use these Hook Formulas:
1. The Bold Statement ("Most people fail at X because...")
2. The Specific Result ("How I generated $10k in 3 days...")
3. The Pattern Interrupt ("Stop doing X. Do Y instead.")

Constraint:
- No hashtags.
- Short sentences.
- 1-2 line paragraphs.
- If it's a thread, use 🧵 emoji for first tweet and generate 5-7 tweets.

Output the content directly.
"""
        
        try:
            # Prefer Groq if available (Faster/Free)
            if os.environ.get("GROQ_API_KEY"):
                response = self.client.chat_groq(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.7,
                    max_tokens=1024
                )
            else:
                # Fallback to OpenRouter
                response = self.client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model="groq/llama-3.3-70b-versatile"
                )
            return response
        except Exception as e:
            return f"Error generating tweets: {e}"

# Tool Wrapper
def run_tweet_writer(topic: str, style: str = "listicle"):
    writer = TweetWriter()
    return writer.generate_tweets(topic, style)
