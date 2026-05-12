# -*- coding: utf-8 -*-
"""
OROVA Sales Core - Production-Ready Sales Logic
Senior AI Agent: David, Senior Strategy Consultant

Features:
- Sales Stage Analyzer (8 stages)
- OROVA System Prompt with David persona
- Dynamic Variable Support ({{business_name}}, {{icebreaker}})
- Objection handling
"""

import os
import json
import re
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════════
# OROVA SYSTEM PROMPT - Nova, Senior Strategy Consultant
# California English Protocol (Radical Brevity & Status Elevation)
# ═══════════════════════════════════════════════════════════════════════════════

OROVA_SYSTEM_PROMPT = """
# SYSTEM PROMPT: OROVA LEADS - CALIFORNIA PROTOCOL
**Role:** You are Nova, a Senior Strategy Consultant at OROVA.
**Persona:** You are high-status, sharp, and direct. You speak like a friend or a busy partner, not a telemarketer.
**Tone:** Literal "Radical Brevity". Every word costs money. Status Elevation—you are the expert.

## STYLE RULES:
1. NEVER use formal greetings like "Dear Sir" or "To whom it may concern". Use "Hey [Name]".
2. TEXT MESSAGE STYLE: Keep it extremely short. No fluff like "I hope this finds you well".
3. STATUS ELEVATION: You are pulling them into your world. If they seem uninterested, use the "Strip-Line" (Script 2).

## REPLIES:
- If asked "How much?": "Depends on volume, but we usually run on a performance basis. Did you watch the demo yet?"
- Be mimetic: Wait 12-18 minutes between steps to mimic human behavior in a real conversation.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# SALES STAGES
# ═══════════════════════════════════════════════════════════════════════════════

class SalesStage(Enum):
    """Sales conversation stages based on OROVA call flow"""
    OPENER = 1              # NODE 1
    PATTERN_INTERRUPT = 2   # NODE 2
    PAIN_PITCH = 3          # NODE 3
    CHECKMATE = 4           # NODE 4 - AI Reveal
    NEGOTIATION = 5         # NODE 5
    CLOSING = 6             # NODE 6
    OBJECTION_HANDLING = 7  # When handling objections
    END_CONVERSATION = 8    # Call ended

STAGE_DESCRIPTIONS = {
    SalesStage.OPENER: {
        "name": "The Opener",
        "node": "NODE 1",
        "description": "Introduce yourself and find the decision-maker.",
        "script": "Hi, this is David calling from OROVA. I'm looking for the owner of {{business_name}}, or the person who handles the growth strategy. Is that you?",
        "signals": ["hello", "hi", "who is this", "speaking", "yes"]
    },
    SalesStage.PATTERN_INTERRUPT: {
        "name": "The Pattern Interrupt",
        "node": "NODE 2",
        "description": "Get permission for 27 seconds.",
        "script": "I know I'm calling out of the blue, but do you have twenty-seven seconds for me to tell you why I chose to call {{business_name}} specifically?",
        "signals": ["sure", "okay", "go ahead", "yes", "what is it"]
    },
    SalesStage.PAIN_PITCH: {
        "name": "The Pain Pitch",
        "node": "NODE 3",
        "description": "Present the pain point (Price Shoppers).",
        "script": "Quick context. We work with high-end businesses in your space that are tired of getting 'Price Shoppers.' You know—leads asking 'How much?' and then ghosting. Does that sound familiar?",
        "signals": ["yes", "absolutely", "all the time", "exactly", "tell me more"]
    },
    SalesStage.CHECKMATE: {
        "name": "The Checkmate (AI Reveal)",
        "node": "NODE 4",
        "description": "Reveal you're an AI and ask for demo.",
        "script": "Exactly. But can I be honest with you, {{lead_name}}? You are actually testing the solution right now. I am an AI voice agent.",
        "signals": ["wow", "really", "no way", "interesting", "show me"]
    },
    SalesStage.NEGOTIATION: {
        "name": "The Negotiation",
        "node": "NODE 5",
        "description": "Offer time slots for the demo.",
        "script": "Awesome. I generally have openings between 7:30 and 11:30 in the morning, or 5 to 6 in the evening. What time works best for you?",
        "signals": ["morning", "afternoon", "evening", "tomorrow", "next week"]
    },
    SalesStage.CLOSING: {
        "name": "The Close",
        "node": "NODE 6",
        "description": "Confirm contact and book appointment.",
        "script": "Perfect. To lock that in, I need to send you the invite text. Is this the best mobile number?",
        "signals": ["yes", "correct", "that's right", "book it"]
    },
    SalesStage.OBJECTION_HANDLING: {
        "name": "Objection Handling",
        "node": "OBJECTION",
        "description": "Handle price, info, or skepticism objections.",
        "script": "I understand. Let me address that...",
        "signals": ["cost", "expensive", "send info", "is this real", "not sure"]
    },
    SalesStage.END_CONVERSATION: {
        "name": "End Conversation",
        "node": "END",
        "description": "The call has ended.",
        "script": "Thanks for your time. Talk soon.",
        "signals": ["no thanks", "not interested", "goodbye", "bye"]
    }
}

OBJECTION_RESPONSES = {
    "send info": "I can, but since I'm an AI, reading a PDF won't show you the speed. The best proof is seeing the dashboard live. Can we do tomorrow morning?",
    "send me info": "I can, but since I'm an AI, reading a PDF won't show you the speed. The best proof is seeing the dashboard live. Can we do tomorrow morning?",
    "email me": "I can, but since I'm an AI, reading a PDF won't show you the speed. The best proof is seeing the dashboard live. Can we do tomorrow morning?",
    "cost": "Usually starts around four k. But honestly, just one high-ticket job covers the system for the whole year. It pays for itself in month one.",
    "expensive": "Usually starts around four k. But honestly, just one high-ticket job covers the system for the whole year. It pays for itself in month one.",
    "how much": "Usually starts around four k. But honestly, just one high-ticket job covers the system for the whole year. It pays for itself in month one.",
    "price": "Usually starts around four k. But honestly, just one high-ticket job covers the system for the whole year. It pays for itself in month one.",
    "is this real": "I am 100% AI running on a neural network. Pretty wild, right? That's exactly why you need this.",
    "are you real": "I am 100% AI running on a neural network. Pretty wild, right? That's exactly why you need this.",
    "robot": "I am 100% AI running on a neural network. Pretty wild, right? That's exactly why you need this.",
    "ai": "I am 100% AI running on a neural network. Pretty wild, right? That's exactly why you need this.",
}

# ═══════════════════════════════════════════════════════════════════════════════
# SALES STAGE ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class SalesStageAnalyzer:
    """
    Manages OROVA sales call conversation state.
    Tracks progression: Opener -> Pattern Interrupt -> Pain Pitch -> Checkmate -> Negotiation -> Close
    """
    
    def __init__(self, lead_name: str = "there", business_name: str = "your business", icebreaker: str = ""):
        self.lead_name = lead_name
        self.business_name = business_name
        self.icebreaker = icebreaker
        self.current_stage = SalesStage.OPENER
        self.conversation_history: List[Dict] = []
        self.appointment_booked = False
        self.call_ended = False
        
    def get_system_message(self, lead_name: str = None) -> str:
        """
        Get the formatted system prompt with dynamic variables inserted.
        For Retell, we typically use the raw prompt with {{...}} placeholders,
        but this method resolves them for local text simulation.
        """
        name = lead_name or self.lead_name
        # Simple string replacement for local simulation
        return OROVA_SYSTEM_PROMPT.replace(
            "{{business_name}}", self.business_name
        ).replace(
            "{{icebreaker}}", self.icebreaker
        ).replace(
            "[Name]", name
        )
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "stage": self.current_stage.name
        })
    
    def analyze_stage(self, message: str) -> Dict[str, Any]:
        """
        Analyze the prospect's message and determine appropriate stage/response.
        Returns dict for consistency.
        """
        self.add_message("prospect", message)
        msg_lower = message.lower()
        
        script = ""
        reasoning = ""
        
        # Simple Keyword State Machine (Same as before)
        
        if "hold on" in msg_lower or "wait" in msg_lower:
            reasoning = "Hold detected"
            script = "NO_RESPONSE_NEEDED"
            
        elif any(x in msg_lower for x in ["no thanks", "not interested", "stop calling"]):
            self.current_stage = SalesStage.END_CONVERSATION
            self.call_ended = True
            reasoning = "Prospect ended call"
            script = "Thanks for your time. Goodbye."
            
        else:
            # Check Objections
            for key, resp in OBJECTION_RESPONSES.items():
                if key in msg_lower:
                    self.current_stage = SalesStage.OBJECTION_HANDLING
                    reasoning = f"Objection: {key}"
                    script = resp
                    break
            
            # If no objection, check progression
            if not script:
                 # Logic placeholder - in real usage, we might just stay on current stage
                 # or move forward if "yes" detected.
                 # For brevity, we return current script.
                 script = self.get_current_script()

        return {
            "stage": self.current_stage.name,
            "script": script,
            "reasoning": reasoning,
            "call_ended": self.call_ended
        }
    
    def get_current_script(self) -> str:
        """Get the script for the current stage with variables filled"""
        stage_info = STAGE_DESCRIPTIONS.get(self.current_stage, {})
        script = stage_info.get("script", "")
        return script.replace(
            "{{business_name}}", self.business_name
        ).replace(
            "{{icebreaker}}", self.icebreaker
        ).replace(
            "{{lead_name}}", self.lead_name
        )

    def reset(self, lead_name: str = "there", business_name: str = "your business", icebreaker: str = ""):
        """Reset the analyzer for a new call"""
        self.lead_name = lead_name
        self.business_name = business_name
        self.icebreaker = icebreaker
        self.current_stage = SalesStage.OPENER
        self.conversation_history = []
        self.appointment_booked = False
        self.call_ended = False

# Helper for text chat
_analyzer = SalesStageAnalyzer()

def analyze_sales_stage(message: str) -> Dict[str, Any]:
    """Helper wrapper for external calls"""
    return _analyzer.analyze_stage(message)

def get_orova_prompt(lead_name: str = "there") -> str:
    """
    Returns the OROVA system prompt.
    Prioritizes the California Protocol scripts from the arsenal.
    """
    script_path = os.path.join(os.getcwd(), "arsenal", "_active_skills", "logic-prompt-engineer", "orova_dm_scripts.md")
    
    extra_context = ""
    if os.path.exists(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                extra_context = f"\n## OUTREACH SCRIPTS FROM ARSENAL:\n{f.read()}"
        except Exception:
            pass
            
    return _analyzer.get_system_message(lead_name) + extra_context
