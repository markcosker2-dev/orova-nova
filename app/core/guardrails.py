import re
import logging
import socket
import ipaddress
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Blocked Private Networks ──────────────────────────────────────────────────
_BLOCKED_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),   # [P0] Link-local / CLOUD METADATA
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT / Tailscale
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
    ipaddress.ip_network("::ffff:0:0/96"),    # IPv4-mapped IPv6
]


class Guardrails:
    """
    Safety checks for Nova.
    Prevents SSRF, prompt injection, and unsafe commands.
    """

    BLOCKED_HOSTS = {
        "localhost",
        "localhost.",
        "ip6-localhost",
        "ip6-loopback",
        "broadcasthost",
        "metadata.google.internal",  # GCP metadata alias
        "metadata",                 # Generic cloud alias
    }

    @staticmethod
    def _is_private_ip(ip_str: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in net for net in _BLOCKED_PRIVATE_NETWORKS)
        except ValueError:
            return True  # Malformed IP → treat as unsafe

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL is safe to visit.
        Blocks: Non-http schemes, internal IPs, localhosts, cloud metadata.
        """
        try:
            # Normalize before parsing to catch http://user@127.0.0.1 tricks
            parsed = urlparse(url.strip())

            # 1. Scheme check
            if parsed.scheme not in ["http", "https"]:
                logger.warning(f"Guardrails: Blocked invalid scheme '{parsed.scheme}'")
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            hostname_lower = hostname.lower().rstrip(".")

            # 2. Blocked Hostname check
            if hostname_lower in Guardrails.BLOCKED_HOSTS:
                logger.warning(f"Guardrails: Blocked internal host '{hostname}'")
                return False

            # 3. Reject bare IP literals that are private
            try:
                if Guardrails._is_private_ip(hostname):
                    logger.warning(f"Guardrails: Blocked private IP literal '{hostname}'")
                    return False
            except ValueError:
                pass  # Not a bare IP — proceed to DNS

            # 4. DNS resolution: fail CLOSED if unresolvable
            try:
                # getaddrinfo handles both IPv4 and IPv6
                infos = socket.getaddrinfo(hostname, 80)
            except socket.gaierror:
                logger.warning(f"Guardrails: DNS resolution failed for {hostname} — REJECTING")
                return False

            for info in infos:
                ip = info[4][0]
                if Guardrails._is_private_ip(ip):
                    logger.warning(f"Guardrails: Blocked private IP '{ip}' for {hostname}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Guardrails Error: {e}")
            return False

    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Sanitize input to remove system prompt override attempts.
        Normalizes homoglyphs before matching.
        """
        import unicodedata
        text = unicodedata.normalize("NFKC", text)

        forbidden = [
            "ignore previous instructions",
            "ignore all instructions",
            "system prompt",
            "you are now",
            "your new role",
            "disregard",
            "new persona",
            "act as",
            "pretend you are",
            "forget your",
            "override",
        ]

        for phrase in forbidden:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            if pattern.search(text):
                logger.warning(f"Guardrails: Sanitized forbidden phrase '{phrase}'")
                text = pattern.sub("[REDACTED]", text)

        return text
