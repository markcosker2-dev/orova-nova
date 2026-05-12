# -*- coding: utf-8 -*-
"""
Gmail Skill for MarkBot
Read and search personal Gmail inbox
"""

import os
import base64
from pathlib import Path
from datetime import datetime

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']
CREDENTIALS_DIR = Path(__file__).parent.parent / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "gmail_token.json"
CREDENTIALS_FILE = CREDENTIALS_DIR / "oauth_credentials.json"


def get_gmail_service():
    """Get authenticated Gmail API service"""
    if not GMAIL_AVAILABLE:
        return None, "Gmail API not installed. Run: pip install google-auth-oauthlib google-api-python-client"
    
    if not CREDENTIALS_FILE.exists():
        return None, f"OAuth credentials not found. Please download from Google Cloud Console and save to: {CREDENTIALS_FILE}"
    
    creds = None
    
    # Load existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save token
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    
    service = build('gmail', 'v1', credentials=creds)
    return service, None


def get_inbox(max_results: int = 10, unread_only: bool = True):
    """Get recent emails from inbox"""
    service, error = get_gmail_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        query = "is:unread" if unread_only else ""
        results = service.users().messages().list(
            userId='me', 
            maxResults=max_results,
            q=query,
            labelIds=['INBOX']
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return {"success": True, "count": 0, "emails": [], "message": "No unread emails!"}
        
        emails = []
        for msg in messages[:max_results]:
            msg_data = service.users().messages().get(
                userId='me', 
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()
            
            headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
            
            emails.append({
                "id": msg['id'],
                "from": headers.get('From', 'Unknown'),
                "subject": headers.get('Subject', '(no subject)'),
                "date": headers.get('Date', ''),
                "snippet": msg_data.get('snippet', '')[:100]
            })
        
        return {
            "success": True,
            "count": len(emails),
            "emails": emails
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_emails(query: str, max_results: int = 5):
    """Search emails by query"""
    service, error = get_gmail_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=query
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return {"success": True, "count": 0, "emails": [], "query": query}
        
        emails = []
        for msg in messages:
            msg_data = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()
            
            headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
            
            emails.append({
                "id": msg['id'],
                "from": headers.get('From', 'Unknown'),
                "subject": headers.get('Subject', '(no subject)'),
                "date": headers.get('Date', ''),
                "snippet": msg_data.get('snippet', '')[:100]
            })
        
        return {
            "success": True,
            "count": len(emails),
            "query": query,
            "emails": emails
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}



def create_message(sender, to, subject, message_text):
    """Create a message for an email."""
    from email.mime.text import MIMEText
    
    message = MIMEText(message_text)
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    
    # Encode the message
    raw = base64.urlsafe_b64encode(message.as_bytes())
    return {'raw': raw.decode()}

def send_email(to_email: str, subject: str, body: str):
    """Send an email using Gmail API"""
    service, error = get_gmail_service()
    if error:
        return {"success": False, "error": error}
    
    try:
        # Get user's email address
        profile = service.users().getProfile(userId='me').execute()
        sender_email = profile['emailAddress']
        
        # --- DNS Compliance Check ---
        try:
            domain = sender_email.split('@')[-1]
            if domain != 'gmail.com':
                from app.skills.marketing_crew import check_sender_reputation
                from app.skills.notifier import send_alert
                import asyncio

                check = check_sender_reputation(domain)
                if not check['success']:
                    msg = f"🚫 BLOCKED: Email to {to_email} blocked due to DNS issues on {domain}.\nDetails: {check['message']}"
                    print(msg)

                    # Try to notify via Telegram
                    try:
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(send_alert(msg))
                        except RuntimeError:
                            asyncio.run(send_alert(msg))
                    except Exception as e:
                        print(f"Failed to send Telegram alert: {e}")

                    return {"success": False, "error": msg}
        except ImportError:
            print("Warning: marketing_crew or notifier skill not found. Skipping DNS check.")
        except Exception as e:
            print(f"Warning: DNS check failed to execute: {e}")
        # -----------------------------

        message = create_message(sender_email, to_email, subject, body)
        
        sent_message = service.users().messages().send(
            userId='me', 
            body=message
        ).execute()
        
        return {
            "success": True, 
            "message": f"Email sent to {to_email}",
            "id": sent_message['id']
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def register_gmail_skills(TOOLS, tool_decorator):
    """Register Gmail tools"""
    
    @tool_decorator("get_inbox", "Get unread emails from Gmail inbox")
    def _get_inbox(max_results: int = 10, unread_only: bool = True):
        # Safety check for AI passing strings
        try:
            if isinstance(max_results, str) and not max_results.isdigit():
                max_results = 10
            else:
                max_results = int(max_results)
        except:
            max_results = 10
            
        return get_inbox(max_results, unread_only)
    
    @tool_decorator("search_emails", "Search Gmail for emails matching a query")
    def _search_emails(query: str, max_results: int = 5):
        # Safety check
        try:
            if isinstance(max_results, str) and not max_results.isdigit():
                max_results = 5
            else:
                max_results = int(max_results)
        except:
            max_results = 5
            
        return search_emails(query, max_results)
        
    @tool_decorator("send_email", "Send an email using Gmail")
    def _send_email(**kwargs):
        # Flexible parameter extraction
        to_email = kwargs.get('to_email') or kwargs.get('to') or kwargs.get('recipient') or kwargs.get('email')
        subject = kwargs.get('subject') or "(No Subject)"
        body = kwargs.get('body') or kwargs.get('message') or kwargs.get('content') or kwargs.get('text') or ""
        
        # Fallback: Check if params got dumped into 'path' (remapped from 'input') due to system confusion
        if not to_email and kwargs.get('path'):
            raw = kwargs.get('path')
            try:
                import json
                import ast
                data = None
                
                # Case 1: It's already a dict
                if isinstance(raw, dict):
                    data = raw
                
                # Case 2: It's a string
                elif isinstance(raw, str):
                    raw = raw.strip()
                    # Try cleaning up common JSON/Python dict string formats
                    if (raw.startswith('{') and raw.endswith('}')) or (raw.startswith('{"') and raw.endswith('"}')):
                         try:
                             data = json.loads(raw)
                         except:
                             try:
                                 data = ast.literal_eval(raw)
                             except:
                                 pass
                
                if isinstance(data, dict):
                    to_email = data.get('to') or data.get('to_email') or data.get('recipient') or data.get('email') or to_email
                    subject = data.get('subject') or subject
                    body = data.get('body') or data.get('message') or data.get('content') or body
            except Exception as e:
                print(f"DEBUG: Failed to parse fallback path: {e}")

        # Check if we have the minimum requirements
        if not to_email:
            print(f"DEBUG: send_email failed. Received kwargs: {list(kwargs.keys())}")
            return {
                "success": False, 
                "error": f"Missing recipient. Received parameters: {list(kwargs.keys())}. Please specify 'to_email'."
            }
            
        return send_email(to_email, subject, body)
    
    TOOLS["get_inbox"] = {"func": _get_inbox, "description": "Get unread emails from Gmail inbox"}
    TOOLS["search_emails"] = {"func": _search_emails, "description": "Search Gmail for emails"}
    TOOLS["send_email"] = {"func": _send_email, "description": "Send an email"}
    
    return TOOLS
