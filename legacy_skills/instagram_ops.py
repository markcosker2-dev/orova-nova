# -*- coding: utf-8 -*-
"""
Instagram Operations Skill
Wrapper for instagrapi to allow safe liking/commenting.
"""

import os
import time
from typing import Dict, Any, Optional

class InstagramManager:
    """
    Wrapper for instagrapi to allow liking/commenting safely.
    """
    def __init__(self):
        self.client = None
        self.username = os.environ.get("INSTAGRAM_USERNAME")
        self.password = os.environ.get("INSTAGRAM_PASSWORD")
        self.is_logged_in = False

        # Check if instagrapi is available
        try:
            from instagrapi import Client
            self.Client = Client
        except ImportError:
            self.Client = None
            # Do not print on init to avoid spamming logs if not used
            pass

    def login(self) -> Dict[str, Any]:
        """Login to Instagram"""
        if not self.Client:
            return {"success": False, "error": "instagrapi not installed. Run: pip install instagrapi"}

        if not self.username or not self.password:
            return {"success": False, "error": "INSTAGRAM_USERNAME or INSTAGRAM_PASSWORD not set"}

        try:
            if not self.client:
                self.client = self.Client()

            self.client.login(self.username, self.password)
            self.is_logged_in = True
            return {"success": True, "message": f"Logged in as {self.username}"}
        except Exception as e:
            return {"success": False, "error": f"Instagram Login Failed: {str(e)}"}

    def _ensure_login(self) -> Dict[str, Any]:
        if self.is_logged_in:
            return {"success": True}
        return self.login()

    def like_media(self, media_id: str) -> Dict[str, Any]:
        """Like a media item by ID"""
        res = self._ensure_login()
        if not res["success"]:
            return res

        try:
            self.client.media_like(media_id)
            return {"success": True, "message": f"Liked media {media_id}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def comment_media(self, media_id: str, text: str) -> Dict[str, Any]:
        """Comment on a media item"""
        res = self._ensure_login()
        if not res["success"]:
            return res

        try:
            comment = self.client.media_comment(media_id, text)
            return {
                "success": True,
                "message": f"Commented on {media_id}",
                "comment_pk": getattr(comment, 'pk', 'unknown')
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_user_medias(self, username: str, amount: int = 5) -> Dict[str, Any]:
        """Get recent media for a user (useful to find media_id)"""
        res = self._ensure_login()
        if not res["success"]:
            return res

        try:
            # Check if username is actually a URL
            if "instagram.com" in username:
                username = username.split("instagram.com/")[1].split("/")[0]

            user_id = self.client.user_id_from_username(username)
            medias = self.client.user_medias(user_id, amount=amount)

            result = []
            for m in medias:
                result.append({
                    "id": m.id,
                    "pk": m.pk,
                    "code": m.code,
                    "caption": m.caption_text[:50] + "..." if m.caption_text else "",
                    "url": f"https://instagram.com/p/{m.code}"
                })

            return {"success": True, "medias": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Global instance
instagram_manager = InstagramManager()
