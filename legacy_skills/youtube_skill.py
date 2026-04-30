# -*- coding: utf-8 -*-
"""
YouTube Summarizer Skill for MarkBot
Extract and summarize content from YouTube videos
"""

import os
import re
from pathlib import Path

# Try to import youtube_transcript_api
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_AVAILABLE = True
except ImportError:
    TRANSCRIPT_AVAILABLE = False


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats"""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # Maybe it's just the ID
    if len(url) == 11 and re.match(r'^[a-zA-Z0-9_-]+$', url):
        return url
    
    return None


def get_transcript(video_id: str, language: str = 'en'):
    """Get the transcript/captions from a YouTube video
    
    Args:
        video_id: YouTube video ID or URL
        language: Preferred language code (default 'en')
    """
    if not TRANSCRIPT_AVAILABLE:
        return {
            "success": False,
            "error": "youtube_transcript_api not installed. Run: pip install youtube-transcript-api"
        }
    
    # Extract ID if URL was passed
    vid_id = extract_video_id(video_id) or video_id
    
    try:
        # Try to get transcript in preferred language
        transcript_list = YouTubeTranscriptApi.list_transcripts(vid_id)
        
        try:
            transcript = transcript_list.find_transcript([language])
        except:
            # Fall back to any available transcript
            transcript = transcript_list.find_generated_transcript([language, 'en'])
        
        transcript_data = transcript.fetch()
        
        # Combine all text
        full_text = " ".join([entry['text'] for entry in transcript_data])
        
        # Calculate duration
        total_duration = sum(entry.get('duration', 0) for entry in transcript_data)
        
        return {
            "success": True,
            "video_id": vid_id,
            "language": transcript.language,
            "duration_seconds": int(total_duration),
            "word_count": len(full_text.split()),
            "transcript": full_text[:8000]  # Limit to prevent token overflow
        }
        
    except Exception as e:
        error_msg = str(e)
        if "disabled" in error_msg.lower():
            return {"success": False, "error": "Transcripts are disabled for this video"}
        elif "not found" in error_msg.lower():
            return {"success": False, "error": "Video not found or no captions available"}
        return {"success": False, "error": error_msg}


def summarize_video(url: str):
    """Get a video transcript ready for summarization
    
    The AI can then read the transcript and provide a summary.
    
    Args:
        url: YouTube video URL or ID
    """
    result = get_transcript(url)
    
    if not result.get("success"):
        return result
    
    # Return transcript with instructions for AI
    return {
        "success": True,
        "video_id": result["video_id"],
        "duration_seconds": result["duration_seconds"],
        "word_count": result["word_count"],
        "transcript": result["transcript"],
        "instruction": "Please summarize this video transcript in a clear, concise way. Highlight the main points and key takeaways."
    }


def register_youtube_skills(TOOLS, tool_decorator):
    """Register YouTube tools"""
    
    @tool_decorator("youtube_transcript", "Get transcript from YouTube video")
    def _youtube_transcript(**kwargs):
        url = kwargs.get('url') or kwargs.get('video') or kwargs.get('link') or kwargs.get('video_id')
        language = kwargs.get('language') or kwargs.get('lang') or 'en'
        
        if not url:
            return {"success": False, "error": "Missing 'url' parameter"}
        
        return get_transcript(url, language)
    
    @tool_decorator("summarize_youtube", "Summarize a YouTube video")
    def _summarize_youtube(**kwargs):
        url = kwargs.get('url') or kwargs.get('video') or kwargs.get('link') or kwargs.get('video_id')
        
        if not url:
            return {"success": False, "error": "Missing 'url' parameter (YouTube link)"}
        
        return summarize_video(url)
    
    TOOLS["youtube_transcript"] = {"func": _youtube_transcript, "description": "Get YouTube video transcript"}
    TOOLS["summarize_youtube"] = {"func": _summarize_youtube, "description": "Summarize YouTube video"}
    
    return TOOLS
