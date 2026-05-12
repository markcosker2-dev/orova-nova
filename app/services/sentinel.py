"""
Sentinel Guardian Health Monitoring Service for OROVA OpenClaw
Monitors external service health endpoints with graceful degradation
"""

import json
import time
import threading
import requests
import logging
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    GREEN = "green"    # All healthy
    YELLOW = "yellow"  # 1 service degraded
    RED = "red"        # 2+ services down
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    name: str
    status: bool
    latency_ms: int
    last_checked: str
    error_message: Optional[str] = None


@dataclass
class SystemHealthReport:
    overall_status: str
    services: List[ServiceHealth]
    last_updated: str
    healthy_count: int
    total_services: int


class SentinelGuardian:
    """
    Sentinel Guardian Health Monitoring Service
    Runs in background thread, monitors external services every 5 minutes
    """

    CHECK_INTERVAL = 300  # 5 minutes in seconds
    REQUEST_TIMEOUT = 10  # seconds
    MAX_RETRIES = 2
    HEALTH_FILE = "system_health.json"

    # Monitored service endpoints
    MONITORED_SERVICES = [
        {
            "name": "groq_api",
            "url": "https://api.groq.com/openai/v1/models",
            "method": "GET",
            "headers": {"Authorization": "Bearer dummy"}
        },
        {
            "name": "gemini_api",
            "url": "https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta",
            "method": "GET"
        },
        {
            "name": "render_health",
            "url": "https://status.render.com/api/v2/status.json",
            "method": "GET"
        },
        {
            "name": "openai_api",
            "url": "https://api.openai.com/v1/models",
            "method": "GET",
            "headers": {"Authorization": "Bearer dummy"}
        },
        {
            "name": "telegram_bot",
            "url": "https://api.telegram.org/bot/getMe",
            "method": "GET"
        }
    ]

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_report: Optional[SystemHealthReport] = None
        self._session = self._create_session()
        logger.info("Sentinel Guardian initialized")

    def _create_session(self) -> requests.Session:
        """Create requests session with retry policy"""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _check_single_service(self, service_config: Dict) -> ServiceHealth:
        """Check health of a single service"""
        start_time = time.perf_counter()
        status = False
        error_msg = None

        try:
            headers = service_config.get("headers", {})
            response = self._session.request(
                method=service_config["method"],
                url=service_config["url"],
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
                allow_redirects=True
            )
            # Accept 2xx and 401/403 as healthy (authentication is expected for private endpoints)
            status = 200 <= response.status_code < 500
            if not status:
                error_msg = f"HTTP {response.status_code}: {response.reason}"

        except requests.exceptions.Timeout:
            error_msg = "Request timed out"
        except requests.exceptions.ConnectionError:
            error_msg = "Connection failed"
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)}"
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception(f"Unexpected error checking {service_config['name']}")

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return ServiceHealth(
            name=service_config["name"],
            status=status,
            latency_ms=latency_ms,
            last_checked=datetime.utcnow().isoformat() + "Z",
            error_message=error_msg
        )

    def _calculate_overall_status(self, results: List[ServiceHealth]) -> HealthStatus:
        """Calculate overall system health status"""
        failed = sum(1 for r in results if not r.status)

        if failed == 0:
            return HealthStatus.GREEN
        elif failed == 1:
            return HealthStatus.YELLOW
        else:
            return HealthStatus.RED

    def _run_check_cycle(self) -> None:
        """Execute full health check cycle"""
        try:
            logger.debug("Running Sentinel health check cycle")
            results = []

            for service in self.MONITORED_SERVICES:
                try:
                    result = self._check_single_service(service)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to check {service['name']}: {e}")
                    results.append(ServiceHealth(
                        name=service["name"],
                        status=False,
                        latency_ms=0,
                        last_checked=datetime.utcnow().isoformat() + "Z",
                        error_message=f"Check failed: {str(e)}"
                    ))

            overall_status = self._calculate_overall_status(results)
            healthy_count = sum(1 for r in results if r.status)

            report = SystemHealthReport(
                overall_status=overall_status.value,
                services=results,
                last_updated=datetime.utcnow().isoformat() + "Z",
                healthy_count=healthy_count,
                total_services=len(results)
            )

            with self._lock:
                self._last_report = report

            self._write_health_report(report)
            logger.info(f"Sentinel health check complete. Status: {overall_status.value}, {healthy_count}/{len(results)} healthy")

        except Exception as e:
            logger.critical(f"Sentinel health check cycle failed: {e}", exc_info=True)

    def _write_health_report(self, report: SystemHealthReport) -> None:
        """Write health report to JSON file safely"""
        try:
            with open(self.HEALTH_FILE, "w") as f:
                json.dump(asdict(report), f, indent=2)
        except IOError as e:
            logger.error(f"Failed to write health report: {e}")
        except Exception as e:
            logger.error(f"Unexpected error writing health report: {e}")

    def _background_loop(self) -> None:
        """Main background monitoring loop"""
        logger.info("Sentinel Guardian background thread started")

        # Run initial check immediately on startup
        self._run_check_cycle()

        while self._running:
            try:
                time.sleep(self.CHECK_INTERVAL)
                if self._running:
                    self._run_check_cycle()
            except Exception as e:
                logger.critical(f"Error in Sentinel background loop: {e}", exc_info=True)
                # Sleep for short time before retrying to avoid spamming
                time.sleep(30)

        logger.info("Sentinel Guardian background thread stopped")

    def start(self) -> None:
        """Start the Sentinel monitoring service in background thread"""
        if self._running:
            logger.warning("Sentinel Guardian is already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._background_loop,
            daemon=True,
            name="SentinelGuardian"
        )
        self._thread.start()
        logger.info("Sentinel Guardian started successfully")

    def stop(self) -> None:
        """Stop the Sentinel monitoring service gracefully"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Sentinel Guardian stopped")

    def get_latest_report(self) -> Optional[SystemHealthReport]:
        """Get the latest health report (thread-safe)"""
        with self._lock:
            return self._last_report

    def run_manual_check(self) -> SystemHealthReport:
        """Run an immediate manual health check"""
        self._run_check_cycle()
        return self.get_latest_report()


# Global singleton instance
_sentinel_instance = None
_sentinel_lock = threading.Lock()


def get_sentinel() -> SentinelGuardian:
    """Get or create global Sentinel Guardian instance"""
    global _sentinel_instance
    with _sentinel_lock:
        if _sentinel_instance is None:
            _sentinel_instance = SentinelGuardian()
    return _sentinel_instance


def start_sentinel() -> None:
    """Initialize and start Sentinel Guardian monitoring service"""
    try:
        sentinel = get_sentinel()
        sentinel.start()
        logger.info("Sentinel Guardian health monitoring service started")
    except Exception as e:
        logger.critical(f"Failed to start Sentinel Guardian: {e}", exc_info=True)
        # Do not propagate error - Sentinel failure should not crash main app


def stop_sentinel() -> None:
    """Stop Sentinel Guardian monitoring service"""
    try:
        sentinel = get_sentinel()
        sentinel.stop()
    except Exception as e:
        logger.error(f"Error stopping Sentinel Guardian: {e}")
