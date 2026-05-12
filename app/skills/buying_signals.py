"""
OROVA Nova — Buying Signal Monitor
Detects companies that are actively buying: hiring, raising funds, expanding.
These are hot leads — they have budget and urgency.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SIGNALS_FILE = os.getenv("OROVA_SIGNALS_FILE", "/opt/orova/data/buying_signals.json")


class BuyingSignalMonitor:
    """
    Monitors for buying signals using free data sources.
    Signals: hiring, funding, expansion, new office, technology changes.
    """

    SIGNAL_QUERIES = {
        "hiring": [
            '{vertical} company hiring sales',
            '{vertical} business looking for marketing manager',
            '{vertical} company expanding team'
        ],
        "funding": [
            '{vertical} company raises funding',
            '{vertical} startup series A',
            '{vertical} business received investment'
        ],
        "expansion": [
            '{vertical} company new office',
            '{vertical} business expanding to new location',
            '{vertical} company opening second location'
        ],
        "pain": [
            '{vertical} company needs more customers',
            '{vertical} business struggling with leads',
            '{vertical} company looking for marketing help'
        ]
    }

    def __init__(self):
        self.file = SIGNALS_FILE
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.file):
            with open(self.file, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {"signals": [], "last_scan": None}
            self._save()

    def _save(self):
        with open(self.file, "w") as f:
            json.dump(self.data, f, indent=2)

    async def scan(self, vertical: str = "HVAC", location: str = "United States") -> List[Dict]:
        """
        Scan for buying signals in a vertical.
        Uses DuckDuckGo search (free, no API key needed).
        """
        signals = []

        for signal_type, queries in self.SIGNAL_QUERIES.items():
            for query_template in queries:
                query = query_template.format(vertical=vertical, location=location)

                try:
                    results = await self._search(query)
                    for result in results:
                        signal = {
                            "type": signal_type,
                            "vertical": vertical,
                            "query": query,
                            "title": result.get("title", ""),
                            "url": result.get("href", ""),
                            "snippet": result.get("body", ""),
                            "detected_at": datetime.utcnow().isoformat(),
                            "score": self._score_signal(signal_type, result)
                        }
                        signals.append(signal)

                except Exception as e:
                    logger.warning(f"[SIGNALS] Search failed for '{query}': {e}")

        # Save signals
        self.data["signals"].extend(signals)
        self.data["last_scan"] = datetime.utcnow().isoformat()
        self._save()

        # Keep only last 500 signals
        self.data["signals"] = self.data["signals"][-500:]
        self._save()

        logger.info(f"[SIGNALS] Found {len(signals)} buying signals for {vertical}")
        return signals

    async def _search(self, query: str) -> List[Dict]:
        """Search using DuckDuckGo (free)."""
        try:
            from duckduckgo_search import DDGS

            def search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=5))

            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, search)

        except ImportError:
            logger.warning("[SIGNALS] duckduckgo-search not installed")
            return []
        except Exception as e:
            logger.warning(f"[SIGNALS] Search error: {e}")
            return []

    def _score_signal(self, signal_type: str, result: Dict) -> int:
        """Score a buying signal (0-100)."""
        scores = {
            "hiring": 70,      # Hiring = growing = has budget
            "funding": 90,     # Just got money = ready to spend
            "expansion": 80,   # Expanding = needs marketing
            "pain": 85         # Actively looking = hot lead
        }

        base = scores.get(signal_type, 50)
        text = json.dumps(result).lower()

        # Boost for luxury/premium keywords
        luxury = ["luxury", "premium", "high-end", "award", "best"]
        for word in luxury:
            if word in text:
                base += 10
                break

        return min(100, base)

    def get_hot_leads(self, min_score: int = 75) -> List[Dict]:
        """Get signals that represent hot leads."""
        hot = [s for s in self.data["signals"] if s.get("score", 0) >= min_score]
        hot.sort(key=lambda s: s.get("score", 0), reverse=True)
        return hot

    def get_recent(self, hours: int = 24) -> List[Dict]:
        """Get signals from the last N hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return [s for s in self.data["signals"] if s.get("detected_at", "") >= cutoff]

    def get_summary(self) -> Dict:
        """Get signal monitoring summary."""
        signals = self.data["signals"]
        by_type = {}
        for s in signals:
            t = s.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_signals": len(signals),
            "by_type": by_type,
            "hot_leads": len(self.get_hot_leads()),
            "last_scan": self.data.get("last_scan"),
            "recent_24h": len(self.get_recent(24))
        }


# Global instance
signals = BuyingSignalMonitor()
