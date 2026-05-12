import re
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class Guardrails:
    """
    Safety checks for Moltbot.
    Prevents SSRF, prompt injection, and unsafe commands.
    """
    
    # Private IP ranges (CIDR-like checks manually implemented for simplicity)
    BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL is safe to visit.
        Blocks: Non-http schemes, internal IPs, localhosts.
        """
        try:
            parsed = urlparse(url)
            
            # 1. Scheme check
            if parsed.scheme not in ["http", "https"]:
                logger.warning(f"Guardrails: Blocked invalid scheme '{parsed.scheme}'")
                return False
                
            hostname = parsed.hostname
            if not hostname:
                return False

            # 2. Blocked Hostname check
            if hostname.lower() in Guardrails.BLOCKED_HOSTS:
                logger.warning(f"Guardrails: Blocked internal host '{hostname}'")
                return False
                
            # 3. DNS resolution check (Prevent DNS rebinding to internal IP)
            try:
                ip_address = socket.gethostbyname(hostname)
                if ip_address.startswith("127.") or \
                   ip_address.startswith("10.") or \
                   ip_address.startswith("192.168.") or \
                   ip_address.startswith("172.16."): # Simplified 172.16-31 check
                    logger.warning(f"Guardrails: Blocked internal IP '{ip_address}' for {hostname}")
                    return False
            except socket.gaierror:
                # Could not resolve, might be safe or invalid. Proceed with caution or block.
                # If we render/playwright ignores it, it's fine.
                pass
                
            return True
            
        except Exception as e:
            logger.error(f"Guardrails Error: {e}")
            return False

    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Basic sanitization to remove system prompt override attempts.
        """
        # Block attempts to redefine "You are..."
        # This is a very basic heuristic.
        forbidden = [
            "ignore previous instructions",
            "system prompt",
            "you are now",
            "your new role"
        ]
        
        lower_text = text.lower()
        for phrase in forbidden:
            if phrase in lower_text:
                logger.warning(f"Guardrails: Sanitized forbidden phrase '{phrase}'")
                # Redact
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                text = pattern.sub("[REDACTED]", text)
                
        return text
