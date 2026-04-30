# -*- coding: utf-8 -*-
"""
Calendar Skill for MarkBot
Manage Google Calendar events
"""

import os
from pathlib import Path
from datetime import datetime, timedelta

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 
          'https://www.googleapis.com/auth/calendar.events']
CREDENTIALS_DIR = Path(__file__).parent.parent / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "calendar_token.json"
CREDENTIALS_FILE = CREDENTIALS_DIR / "oauth_credentials.json"


def get_calendar_service():
    """Get authenticated Calendar API service"""
    if not CALENDAR_AVAILABLE:
        return None, "Calendar API not installed. Run: pip install google-auth-oauthlib google-api-python-client"
    
    if not CREDENTIALS_FILE.exists():
        return None, f"OAuth credentials not found. Please download from Google Cloud Console and save to: {CREDENTIALS_FILE}"
    
    creds = None
    
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    
    service = build('calendar', 'v3', credentials=creds)
    return service, None


def get_today_events():
    """Get today's calendar events"""
    service, error = get_calendar_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        end_of_day = now.replace(hour=23, minute=59, second=59).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return {"success": True, "count": 0, "events": [], "message": "No events today!"}
        
        formatted = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            formatted.append({
                "summary": event.get('summary', '(No title)'),
                "start": start,
                "location": event.get('location', ''),
                "id": event['id']
            })
        
        return {
            "success": True,
            "date": now.strftime("%Y-%m-%d"),
            "count": len(formatted),
            "events": formatted
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_week_events():
    """Get this week's calendar events"""
    service, error = get_calendar_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        now = datetime.utcnow()
        end_of_week = now + timedelta(days=7)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=end_of_week.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime',
            maxResults=20
        ).execute()
        
        events = events_result.get('items', [])
        
        formatted = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            formatted.append({
                "summary": event.get('summary', '(No title)'),
                "start": start,
                "location": event.get('location', '')
            })
        
        return {
            "success": True,
            "count": len(formatted),
            "events": formatted
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_event(summary: str, start_time: str, duration_minutes: int = 60, description: str = ""):
    """Create a calendar event
    
    Args:
        summary: Event title
        start_time: ISO format datetime or "tomorrow 2pm", "next monday 10am"
        duration_minutes: How long the event is
        description: Optional description
    """
    service, error = get_calendar_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        # Parse start_time
        from dateutil import parser as date_parser
        start_dt = date_parser.parse(start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Manila'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Manila'},
        }
        
        created = service.events().insert(calendarId='primary', body=event).execute()
        
        return {
            "success": True,
            "message": f"Event created: {summary}",
            "event_id": created.get('id'),
            "start": start_dt.isoformat()
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_event(event_id: str, summary: str = None, start_time: str = None, duration_minutes: int = None):
    """Update an existing calendar event
    
    Args:
        event_id: The ID of the event to update
        summary: New event title (optional)
        start_time: New start time (optional)
        duration_minutes: New duration (optional)
    """
    service, error = get_calendar_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        # Get existing event
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        # Update fields if provided
        if summary:
            event['summary'] = summary
        
        if start_time:
            from dateutil import parser as date_parser
            start_dt = date_parser.parse(start_time)
            event['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Manila'}
            
            # Update end time based on duration
            dur = duration_minutes if duration_minutes else 60
            end_dt = start_dt + timedelta(minutes=dur)
            event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Manila'}
        
        updated = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        
        return {
            "success": True,
            "message": f"Event updated: {updated.get('summary')}",
            "event_id": updated.get('id')
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_event(event_id: str):
    """Delete a calendar event
    
    Args:
        event_id: The ID of the event to delete
    """
    service, error = get_calendar_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        
        return {
            "success": True,
            "message": f"Event deleted successfully"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def register_calendar_skills(TOOLS, tool_decorator):
    """Register Calendar tools"""
    
    @tool_decorator("get_today", "Get today's calendar events")
    def _get_today(**kwargs):
        return get_today_events()
    
    @tool_decorator("get_week", "Get this week's calendar events")  
    def _get_week(**kwargs):
        return get_week_events()
    
    @tool_decorator("create_event", "Create a calendar event")
    def _create_event(**kwargs):
        # Flexible parameter extraction (like send_email)
        summary = kwargs.get('summary') or kwargs.get('title') or kwargs.get('name') or kwargs.get('event')
        start_time = kwargs.get('start_time') or kwargs.get('start') or kwargs.get('time') or kwargs.get('when')
        duration_minutes = kwargs.get('duration_minutes') or kwargs.get('duration') or 60
        
        # Fallback: Check if params got dumped into 'path'
        if not summary and kwargs.get('path'):
            raw = kwargs.get('path')
            try:
                import json
                import ast
                data = None
                if isinstance(raw, dict):
                    data = raw
                elif isinstance(raw, str):
                    raw = raw.strip()
                    if raw.startswith('{') and raw.endswith('}'):
                        try:
                            data = json.loads(raw)
                        except:
                            try:
                                data = ast.literal_eval(raw)
                            except:
                                pass
                if isinstance(data, dict):
                    summary = data.get('summary') or data.get('title') or data.get('name') or summary
                    start_time = data.get('start_time') or data.get('start') or data.get('time') or data.get('when') or start_time
                    duration_minutes = data.get('duration_minutes') or data.get('duration') or duration_minutes
            except:
                pass
        
        if not summary or not start_time:
            return {"success": False, "error": f"Missing required fields. Got: {list(kwargs.keys())}. Need 'summary' and 'start_time'."}
        
        # Safety check for duration
        try:
            if isinstance(duration_minutes, str) and not duration_minutes.isdigit():
                duration_minutes = 60
            else:
                duration_minutes = int(duration_minutes)
        except:
            duration_minutes = 60
            
        return create_event(summary, start_time, duration_minutes)
    
    @tool_decorator("update_event", "Update an existing calendar event")
    def _update_event(**kwargs):
        event_id = kwargs.get('event_id') or kwargs.get('id')
        summary = kwargs.get('summary') or kwargs.get('title')
        start_time = kwargs.get('start_time') or kwargs.get('start') or kwargs.get('time')
        duration_minutes = kwargs.get('duration_minutes') or kwargs.get('duration')
        
        if not event_id:
            return {"success": False, "error": "Missing event_id. Use get_today or get_week to find event IDs."}
        
        return update_event(event_id, summary, start_time, duration_minutes)
    
    @tool_decorator("delete_event", "Delete a calendar event")
    def _delete_event(**kwargs):
        event_id = kwargs.get('event_id') or kwargs.get('id')
        
        if not event_id:
            return {"success": False, "error": "Missing event_id. Use get_today or get_week to find event IDs."}
        
        return delete_event(event_id)
    
    TOOLS["get_today"] = {"func": _get_today, "description": "Get today's calendar events"}
    TOOLS["get_week"] = {"func": _get_week, "description": "Get this week's calendar events"}
    TOOLS["create_event"] = {"func": _create_event, "description": "Create a calendar event"}
    TOOLS["update_event"] = {"func": _update_event, "description": "Update a calendar event"}
    TOOLS["delete_event"] = {"func": _delete_event, "description": "Delete a calendar event"}
    
    return TOOLS
