"""
Phase 8: Scale & Monitoring
Auto-scaling, observability, alerting, error tracking, performance monitoring.
"""
import os
import logging
import asyncio
import json
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
import traceback

logger = logging.getLogger(__name__)

@dataclass
class Metric:
    """Base metric class for Prometheus-style metrics."""
    name: str
    value: float
    timestamp: str = None
    labels: Dict[str, str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.labels is None:
            self.labels = {}
    
    def to_prometheus(self) -> str:
        """Convert to Prometheus format."""
        label_str = ",".join([f'{k}="{v}"' for k, v in self.labels.items()])
        if label_str:
            return f'{self.name}{{{label_str}}} {self.value}'
        return f'{self.name} {self.value}'

class MetricsCollector:
    """Collect and export Prometheus-style metrics with guardrails against cardinality explosion."""
    MAX_LABEL_KEYS = 1000
    
    def __init__(self):
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.timestamps: Dict[str, str] = {}
    
    def increment_counter(self, name: str, value: float = 1, labels: Dict = None):
        """Increment counter metric."""
        key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
        self.counters[key] += value
        self.timestamps[key] = datetime.utcnow().isoformat()
    
    def set_gauge(self, name: str, value: float, labels: Dict = None):
        """Set gauge metric."""
        key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
        self.gauges[key] = value
        self.timestamps[key] = datetime.utcnow().isoformat()
    
    def record_histogram(self, name: str, value: float, labels: Dict = None):
        """Record histogram value with maximum label cardinality protection."""
        key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
        if key not in self.histograms and len(self.histograms) >= self.MAX_LABEL_KEYS:
            logger.warning(
                f"[Metrics] Histogram key cap ({self.MAX_LABEL_KEYS}) reached. "
                f"Dropping high-cardinality key: {key[:80]}"
            )
            return
        self.histograms[key].append(value)
        if len(self.histograms[key]) > 1000:
            self.histograms[key] = self.histograms[key][-1000:]
    
    def get_histogram_stats(self, name: str, labels: Dict = None) -> Dict:
        """Get statistics for histogram."""
        key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
        values = self.histograms.get(key, [])
        
        if not values:
            return {}
        
        sorted_vals = sorted(values)
        return {
            "min": min(sorted_vals),
            "max": max(sorted_vals),
            "avg": sum(sorted_vals) / len(sorted_vals),
            "p50": sorted_vals[len(sorted_vals) // 2],
            "p95": sorted_vals[int(len(sorted_vals) * 0.95)],
            "p99": sorted_vals[int(len(sorted_vals) * 0.99)],
            "count": len(sorted_vals),
        }
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Counters
        for key, value in self.counters.items():
            name, labels_json = key.split(":", 1)
            labels = json.loads(labels_json)
            metric = Metric(name=f"{name}_total", value=value, labels=labels)
            lines.append(metric.to_prometheus())
        
        # Gauges
        for key, value in self.gauges.items():
            name, labels_json = key.split(":", 1)
            labels = json.loads(labels_json)
            metric = Metric(name=name, value=value, labels=labels)
            lines.append(metric.to_prometheus())
        
        return "\n".join(lines)

@dataclass
class Alert:
    """Alert rule and state."""
    name: str
    condition: Callable
    severity: str  # critical, warning, info
    message_template: str
    threshold: float = None
    duration_seconds: int = 60  # Alert triggers after duration
    triggered_at: Optional[str] = None
    notified: bool = False

class AlertManager:
    """Manage alert rules and trigger notifications using bounded history collections."""
    MAX_HISTORY = 500
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=self.MAX_HISTORY)
    
    def register_alert(self, alert: Alert):
        """Register an alert rule."""
        self.alerts[alert.name] = alert
    
    async def evaluate_all(self, metrics: MetricsCollector) -> List[Dict]:
        """Evaluate all alert rules and return triggered alerts."""
        triggered = []
        
        for name, alert in self.alerts.items():
            try:
                is_triggered = alert.condition(metrics)
                
                if is_triggered and not alert.notified:
                    alert.triggered_at = datetime.utcnow().isoformat()
                    alert.notified = True
                    
                    triggered_alert = {
                        "name": alert.name,
                        "severity": alert.severity,
                        "message": alert.message_template,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    triggered.append(triggered_alert)
                    self.alert_history.append(triggered_alert)
                    
                    logger.warning(f"[ALERT] {alert.severity.upper()}: {alert.name} - {alert.message_template}")
                
                elif not is_triggered and alert.notified:
                    alert.notified = False
                    logger.info(f"[ALERT] {alert.name} - RESOLVED")
            
            except Exception as e:
                logger.error(f"[ALERT] Error evaluating {name}: {e}")
        
        return triggered

class ErrorTracker:
    """Lightweight error tracking and reporting with memory boundaries."""
    MAX_GROUPS = 200
    
    def __init__(self, max_errors: int = 1000):
        self.errors: List[Dict] = []
        self.max_errors = max_errors
        self.error_groups: Dict[str, List[Dict]] = {}
    
    def capture_exception(self, exc: Exception, context: Dict = None, level: str = "error"):
        """Capture and log an exception."""
        
        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "context": context or {},
            "level": level,
        }
        
        self.errors.append(error_entry)
        
        fingerprint = f"{error_entry['type']}:{error_entry['message'][:100]}"
        
        # Evict oldest group when cap is hit
        if fingerprint not in self.error_groups and len(self.error_groups) >= self.MAX_GROUPS:
            oldest_key = next(iter(self.error_groups))
            del self.error_groups[oldest_key]
            logger.debug(f"[ErrorTracker] Evicted oldest error group: {oldest_key}")
            
        if fingerprint not in self.error_groups:
            self.error_groups[fingerprint] = []
        self.error_groups[fingerprint].append(error_entry)
        
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
        
        logger.log(
            logging.ERROR if level == "error" else logging.WARNING,
            f"[ERROR] {type(exc).__name__}: {str(exc)[:200]}"
        )
    
    def get_error_summary(self) -> Dict:
        """Get summary of recent errors."""
        if not self.errors:
            return {"total_errors": 0, "unique_errors": 0}
        
        cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_errors = [
            e for e in self.errors
            if datetime.fromisoformat(e["timestamp"]) > cutoff
        ]
        
        return {
            "total_errors_24h": len(recent_errors),
            "unique_errors": len(self.error_groups),
            "top_errors": sorted(
                [(fp, len(errs)) for fp, errs in self.error_groups.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }

class PerformanceProfiler:
    """Profile function execution times using fast O(1) deques to limit memory growth."""
    
    def __init__(self):
        self.profiles: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
    
    def profile_sync(self, func_name: str):
        """Decorator for synchronous function profiling."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    return func(*args, **kwargs)
                finally:
                    duration = time.time() - start
                    self.profiles[func_name].append(duration)
            return wrapper
        return decorator
    
    def profile_async(self, func_name: str):
        """Decorator for async function profiling."""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                start = time.time()
                try:
                    return await func(*args, **kwargs)
                finally:
                    duration = time.time() - start
                    self.profiles[func_name].append(duration)
            return wrapper
        return decorator
    
    def get_stats(self, func_name: str) -> Dict:
        """Get performance statistics for a function."""
        times = list(self.profiles.get(func_name, []))
        
        if not times:
            return {"function": func_name, "calls": 0}
        
        sorted_times = sorted(times)
        return {
            "function": func_name,
            "calls": len(times),
            "min_ms": min(times) * 1000,
            "max_ms": max(times) * 1000,
            "avg_ms": (sum(times) / len(times)) * 1000,
            "p50_ms": sorted_times[len(times) // 2] * 1000,
            "p95_ms": sorted_times[int(len(times) * 0.95)] * 1000,
            "p99_ms": sorted_times[int(len(times) * 0.99)] * 1000,
        }
    
    def get_all_stats(self) -> List[Dict]:
        """Get stats for all profiled functions."""
        return [self.get_stats(name) for name in self.profiles.keys()]

class AutoScalingConfig:
    """Auto-scaling configuration for deployment platforms."""
    
    RENDER_CONFIG = {
        "service_name": "orova-nova",
        "plan": "free",
        "scaling": {
            "min_instances": 1,
            "max_instances": 1,
            "cpu_threshold_percent": 80,
            "memory_threshold_percent": 80,
            "scale_up_delay_seconds": 60,
            "scale_down_delay_seconds": 300,
        },
        "autoscaling_enabled": False,
    }
    
    @staticmethod
    def get_deployment_config() -> Dict:
        """Get deployment configuration."""
        return {
            "platform": "render",
            "config": AutoScalingConfig.RENDER_CONFIG,
            "upgrade_path": [
                {"plan": "free", "cost": "$0", "instances": 1, "cpu": "0.25", "memory": "512MB"},
                {"plan": "starter", "cost": "$12", "instances": 1, "cpu": "1", "memory": "1GB"},
                {"plan": "standard", "cost": "$25", "instances": 2, "cpu": "2", "memory": "2GB"},
                {"plan": "pro", "cost": "$50", "instances": 3, "cpu": "4", "memory": "4GB"},
            ],
        }

class Runbook:
    """Runbook for operational procedures."""
    
    HIGH_MEMORY_USAGE = {
        "title": "High Memory Usage Alert",
        "description": "Memory usage has exceeded 80% of available",
        "steps": [
            "1. SSH into the instance: `render service connect OROVA`",
            "2. Check running processes: `ps aux | grep python`",
            "3. Review memory usage: `free -h` and `top`",
            "4. Check for memory leaks in recent code changes",
            "5. If necessary, restart: `restart` (Render CLI)",
            "6. Monitor for 1 hour - if repeats, review app code",
        ],
        "prevention": [
            "- Enable memory monitoring in /health endpoint",
            "- Profile long-running async tasks",
            "- Implement request timeouts (30s max)",
            "- Use SQLite connection pooling",
        ],
    }
    
    HIGH_ERROR_RATE = {
        "title": "High Error Rate Alert",
        "description": "Error rate > 5% in last 5 minutes",
        "steps": [
            "1. Check recent logs: `render logs --tail 100`",
            "2. Identify error pattern: group by error type",
            "3. Check if related to recent deployment",
            "4. If recent deploy: rollback with `render deploy --revert`",
            "5. If persistent: check third-party API status",
            "6. Review app/core/ai_client.py circuit breaker status",
        ],
        "prevention": [
            "- Implement exponential backoff for API calls",
            "- Add circuit breakers for third-party dependencies",
            "- Use Sentry/error tracking for early detection",
            "- Set up synthetic monitoring for /health endpoint",
        ],
    }
    
    DATABASE_CORRUPTION = {
        "title": "SQLite Database Corruption",
        "description": "Database appears corrupted or locked",
        "steps": [
            "1. Check if database is locked: `lsof | grep app/data/db.sqlite`",
            "2. Restore from Google Drive backup",
            "3. If Drive backup unavailable, restore from Google Sheets",
            "4. Restart application",
            "5. Monitor database integrity with PRAGMA integrity_check",
        ],
        "prevention": [
            "- Automatic 6-hour backups to Google Drive",
            "- Weekly integrity checks",
            "- Use WAL mode for SQLite",
            "- Regular database maintenance",
        ],
    }
    
    TELEGRAM_WEBHOOK_FAILED = {
        "title": "Telegram Webhook Failed",
        "description": "Messages not being received from Telegram",
        "steps": [
            "1. Verify webhook URL is correct: check RENDER_EXTERNAL_URL env var",
            "2. Test webhook: curl https://your-url.onrender.com/telegram",
            "3. Check /health endpoint for queue status",
            "4. Re-register webhook in main.py lifespan function",
            "5. Verify TELEGRAM_BOT_TOKEN is correct",
        ],
        "prevention": [
            "- Verify webhook during startup",
            "- Implement webhook signature verification",
            "- Add retry logic for webhook registration",
            "- Monitor /telegram endpoint for errors",
        ],
    }

class ObservabilityDashboard:
    """unified observability dashboard data."""
    
    def __init__(self, metrics: MetricsCollector, errors: ErrorTracker, 
                 profiler: PerformanceProfiler, alerts: AlertManager):
        self.metrics = metrics
        self.errors = errors
        self.profiler = profiler
        self.alerts = alerts
    
    async def get_dashboard_data(self) -> Dict:
        """Get complete dashboard data."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "status": "operational",
                "uptime_hours": 0,
            },
            "metrics": {
                "prometheus_export": self.metrics.export_prometheus(),
                "gauges": dict(self.metrics.gauges),
            },
            "errors": self.errors.get_error_summary(),
            "performance": self.profiler.get_all_stats(),
            "alerts": {
                "active": [a for a in self.alerts.alerts.values() if a.notified],
                "history": list(self.alerts.alert_history),
            },
        }

metrics_collector = MetricsCollector()
alert_manager = AlertManager()
error_tracker = ErrorTracker()
profiler = PerformanceProfiler()
observability = ObservabilityDashboard(metrics_collector, error_tracker, profiler, alert_manager)

def _make_error_rate_condition(tracker: ErrorTracker, window: int = 100, threshold: int = 5):
    """Explicitly binds closure scope parameter references for condition checking."""
    def condition(m: MetricsCollector) -> bool:
        return len(tracker.errors[-window:]) > threshold
    return condition

def register_default_alerts(tracker: ErrorTracker = error_tracker):
    """Register common alerts."""
    
    alert_manager.register_alert(Alert(
        name="high_error_rate",
        condition=_make_error_rate_condition(tracker),
        severity="critical",
        message_template="Error rate is high. Check logs immediately.",
        duration_seconds=300,
    ))
    
    alert_manager.register_alert(Alert(
        name="circuit_breaker_open",
        condition=lambda m: False,
        severity="warning",
        message_template="AI provider circuit breaker is open. Service degraded.",
        duration_seconds=60,
    ))
    
    logger.info("[ALERTS] Registered 2 default alert rules")

register_default_alerts()
