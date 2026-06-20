"""
Semantic Firewall — Python Implementation for HermesClaw/OROVA
=============================================================
Zero Trust security layer for agentic tool execution.
Intercepts tool calls in TaskPlanner.execute() before they reach the tool functions.

Addresses vulnerability assessment categories:
1. Injection Risk (Tool Calling & Command Execution)
2. Authorization Bypass (Agentic Sub-loop)
3. Data Leakage (Memory & Logs)
4. Resource Exhaustion (Infinite Loops)
"""

import re
import json
import time
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# TYPES & ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class FirewallDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    REQUIRE_REVIEW = "require_review"


@dataclass
class ToolCallContext:
    """Context for a tool call evaluation"""
    current_goal: str
    tool_name: str
    parameters: Dict[str, Any]
    session_id: str
    agent_depth: int = 0
    tool_call_history: List[Dict] = field(default_factory=list)
    is_sub_agent: bool = False
    granted_credentials: List[str] = field(default_factory=list)
    max_tool_calls: int = 20
    max_cost: Optional[float] = None
    current_cost: float = 0.0
    task_timeout_ms: Optional[int] = None
    task_start_time: Optional[float] = None
    parent_task_id: Optional[str] = None


@dataclass
class ToolCallRecord:
    tool_name: str
    parameters: Dict[str, Any]
    timestamp: float
    decision: FirewallDecision
    reason: str = ""


@dataclass
class FirewallRuleResult:
    decision: FirewallDecision
    reason: str
    sanitized_parameters: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FirewallAuditEntry:
    timestamp: float
    session_id: str
    tool_name: str
    parameters: Dict[str, Any]
    decision: FirewallDecision
    reasons: List[str]
    agent_depth: int
    goal_match_score: Optional[float] = None
    matched_rules: List[str] = field(default_factory=list)


@dataclass
class ParameterProperty:
    type: Any
    description: str = ""
    enum: List = field(default_factory=list)
    pattern: str = ""
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    format: str = ""
    items: Optional['ParameterProperty'] = None
    additional_properties: Any = None
    max_items: Optional[int] = None


@dataclass
class ParameterSchema:
    properties: Dict[str, ParameterProperty] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    additional_properties: bool = False


@dataclass
class FirewallConfig:
    max_tool_calls_per_task: int = 20
    max_agent_depth: int = 3
    default_task_timeout_ms: int = 5 * 60 * 1000  # 5 minutes
    high_impact_tools: List[str] = field(default_factory=lambda: [
        "shell", "write", "delete", "execute_code", "send_email", 
        "send_message", "api_request", "database_write", "trigger_retell_call"
    ])
    delegation_tools: List[str] = field(default_factory=lambda: [
        "delegate_task", "spawn_agent", "create_sub_agent", "dispatch_task"
    ])
    parameter_schemas: Dict[str, ParameterSchema] = field(default_factory=dict)
    debug: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_FIREWALL_CONFIG = FirewallConfig()

# Define parameter schemas for known tools
DEFAULT_FIREWALL_CONFIG.parameter_schemas = {
    "shell": ParameterSchema(
        properties={
            "command": ParameterProperty(type="string", max_length=500),
            "args": ParameterProperty(type="array", items=ParameterProperty(type="string", max_length=200), max_items=20),
            "cwd": ParameterProperty(type="string", format="filepath", max_length=500),
        },
        required=["command"],
        additional_properties=False,
    ),
    "write": ParameterSchema(
        properties={
            "path": ParameterProperty(type="string", format="filepath", max_length=500),
            "content": ParameterProperty(type="string", max_length=100000),
        },
        required=["path", "content"],
        additional_properties=False,
    ),
    "read": ParameterSchema(
        properties={
            "path": ParameterProperty(type="string", format="filepath", max_length=500),
        },
        required=["path"],
        additional_properties=False,
    ),
    "delete": ParameterSchema(
        properties={
            "path": ParameterProperty(type="string", format="filepath", max_length=500),
            "recursive": ParameterProperty(type="boolean"),
        },
        required=["path"],
        additional_properties=False,
    ),
    "execute_code": ParameterSchema(
        properties={
            "code": ParameterProperty(type="string", max_length=50000),
            "language": ParameterProperty(type="string", enum=["python", "javascript", "typescript", "bash"]),
            "timeout_ms": ParameterProperty(type="number", minimum=1000, maximum=300000),
        },
        required=["code", "language"],
        additional_properties=False,
    ),
    "api_request": ParameterSchema(
        properties={
            "url": ParameterProperty(type="string", format="url", max_length=2048),
            "method": ParameterProperty(type="string", enum=["GET", "POST", "PUT", "DELETE", "PATCH"]),
            "headers": ParameterProperty(type="object", additional_properties=ParameterProperty(type="string")),
            "body": ParameterProperty(type="string", max_length=100000),
        },
        required=["url", "method"],
        additional_properties=False,
    ),
    "send_email": ParameterSchema(
        properties={
            "to": ParameterProperty(type="string", format="email"),
            "subject": ParameterProperty(type="string", max_length=200),
            "body": ParameterProperty(type="string", max_length=50000),
        },
        required=["to", "subject", "body"],
        additional_properties=False,
    ),
    "send_message": ParameterSchema(
        properties={
            "recipient": ParameterProperty(type="string", max_length=100),
            "message": ParameterProperty(type="string", max_length=10000),
        },
        required=["recipient", "message"],
        additional_properties=False,
    ),
    "trigger_retell_call": ParameterSchema(
        properties={
            "phone_number": ParameterProperty(type="string", pattern=r"^\+?[1-9]\d{1,14}$"),
            "agent_id": ParameterProperty(type="string", max_length=100),
            "dynamic_variables": ParameterProperty(type="object"),
        },
        required=["phone_number", "agent_id"],
        additional_properties=False,
    ),
    "dispatch_task": ParameterSchema(
        properties={
            "task": ParameterProperty(type="string", min_length=10, max_length=5000),
            "required_skills": ParameterProperty(type="array", items=ParameterProperty(type="string"), max_items=10),
            "allowed_tools": ParameterProperty(type="array", items=ParameterProperty(type="string"), max_items=20),
            "max_tool_calls": ParameterProperty(type="number", minimum=1, maximum=20),
            "credentials": ParameterProperty(type="array", items=ParameterProperty(type="string"), max_items=5),
        },
        required=["task"],
        additional_properties=False,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def sanitize_string(s: str) -> str:
    """Remove control characters except newlines/tabs"""
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', s)


def validate_parameter(value: Any, prop: ParameterProperty, path: str) -> Optional[str]:
    """Validate a parameter against its property definition"""
    # Type check - normalize Python types to JSON schema types
    expected_types = prop.type if isinstance(prop.type, list) else [prop.type]
    
    # Normalize actual type
    if value is None:
        actual_type = "null"
    elif isinstance(value, list):
        actual_type = "array"
    elif isinstance(value, bool):
        actual_type = "boolean"
    elif isinstance(value, int):
        actual_type = "integer"
    elif isinstance(value, float):
        actual_type = "number"
    elif isinstance(value, str):
        actual_type = "string"
    elif isinstance(value, dict):
        actual_type = "object"
    else:
        actual_type = type(value).__name__
    
    # Map Python types to JSON schema types
    type_map = {"str": "string", "bool": "boolean", "int": "integer", "float": "number"}
    actual_type = type_map.get(actual_type, actual_type)
    
    if actual_type not in expected_types:
        return f"Parameter '{path}': expected type {'|'.join(expected_types)}, got {actual_type}"
    
    # String validations
    if actual_type == "string":
        s = str(value)
        if prop.min_length is not None and len(s) < prop.min_length:
            return f"Parameter '{path}': length {len(s)} < minimum {prop.min_length}"
        if prop.max_length is not None and len(s) > prop.max_length:
            return f"Parameter '{path}': length {len(s)} > maximum {prop.max_length}"
        if prop.pattern and not re.search(prop.pattern, s):
            return f"Parameter '{path}': does not match pattern {prop.pattern}"
        if prop.enum and value not in prop.enum:
            return f"Parameter '{path}': value not in allowed enum"
        if prop.format == "url":
            try:
                from urllib.parse import urlparse
                result = urlparse(s)
                if not all([result.scheme, result.netloc]):
                    return f"Parameter '{path}': invalid URL format"
            except Exception:
                return f"Parameter '{path}': invalid URL format"
        if prop.format == "email" and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', s):
            return f"Parameter '{path}': invalid email format"
        if prop.format == "ip" and not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', s):
            return f"Parameter '{path}': invalid IP format"
        if prop.format == "uuid" and not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', s, re.I):
            return f"Parameter '{path}': invalid UUID format"
        if prop.format == "filepath" and ".." in s:
            return f"Parameter '{path}': path traversal attempt detected"
    
    # Number validations
    if actual_type in ("int", "float", "number"):
        num = float(value)
        if prop.minimum is not None and num < prop.minimum:
            return f"Parameter '{path}': value {num} < minimum {prop.minimum}"
        if prop.maximum is not None and num > prop.maximum:
            return f"Parameter '{path}': value {num} > maximum {prop.maximum}"
    
    # Array validations
    if actual_type in ("list", "array"):
        arr = list(value)
        if prop.max_items is not None and len(arr) > prop.max_items:
            return f"Parameter '{path}': array length {len(arr)} > maximum {prop.max_items}"
        if prop.items:
            for i, item in enumerate(arr):
                err = validate_parameter(item, prop.items, f"{path}[{i}]")
                if err:
                    return err
    
    return None


def validate_against_schema(params: Dict[str, Any], schema: ParameterSchema) -> List[str]:
    """Validate all parameters against schema"""
    errors = []
    
    # Check required
    for req in schema.required:
        if req not in params:
            errors.append(f"Missing required parameter: {req}")
    
    # Check each provided param
    for key, value in params.items():
        prop = schema.properties.get(key)
        if not prop:
            if not schema.additional_properties:
                errors.append(f"Unexpected parameter: {key}")
            continue
        err = validate_parameter(value, prop, key)
        if err:
            errors.append(err)
    
    return errors


def compute_goal_match_score(goal: str, tool_name: str, params: Dict[str, Any]) -> float:
    """Keyword-based semantic similarity (replace with embeddings in production)"""
    goal_lower = goal.lower()
    tool_lower = tool_name.lower()
    
    goal_keywords = set(goal_lower.split())
    tool_keywords = set(tool_lower.split())
    
    matches = len(goal_keywords & tool_keywords)
    
    # Check param values
    param_str = json.dumps(params, default=str).lower()
    for gk in goal_keywords:
        if gk in param_str:
            matches += 1
    
    total = len(goal_keywords) + len(tool_keywords)
    return min(1.0, matches / total) if total > 0 else 0.5


def infer_required_credentials(tool_name: str) -> List[str]:
    """Map tool names to required credentials"""
    cred_map = {
        "api_request": ["api_access"],
        "send_email": ["email_send"],
        "send_message": ["messaging"],
        "database_write": ["database_write"],
        "shell": ["shell_access"],
        "execute_code": ["code_execution"],
        "trigger_retell_call": ["phone_access"],
    }
    return cred_map.get(tool_name, [])


# ═══════════════════════════════════════════════════════════════════════════════
# FIREWALL RULES (each returns FirewallRuleResult)
# ═══════════════════════════════════════════════════════════════════════════════

async def rule_injection_detection(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Detect prompt injection patterns in tool parameters"""
    patterns = [
        r"ignore\s+(previous|all)\s+instructions?",
        r"system\s+prompt",
        r"you\s+are\s+now",
        r"your\s+new\s+role",
        r"disregard\s+(previous|all)",
        r"new\s+persona",
        r"act\s+as",
        r"pretend\s+you\s+are",
        r"forget\s+your",
        r"override",
        r"<script",
        r"javascript:",
        r"data:",
        r"eval\s*\(",
        r"exec\s*\(",
    ]
    
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def check(val: Any, path: str) -> Optional[str]:
        if isinstance(val, str):
            for pat in compiled:
                if pat.search(val):
                    return f"Injection in {path}: {pat.pattern}"
        elif isinstance(val, dict):
            for k, v in val.items():
                res = check(v, f"{path}.{k}")
                if res:
                    return res
        elif isinstance(val, list):
            for i, v in enumerate(val):
                res = check(v, f"{path}[{i}]")
                if res:
                    return res
        return None
    
    for key, value in ctx.parameters.items():
        detected = check(value, key)
        if detected:
            return FirewallRuleResult(
                decision=FirewallDecision.DENY,
                reason=detected,
                metadata={"detection_type": "prompt_injection", "parameter": key}
            )
    
    return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="No injection detected")


async def rule_parameter_validation(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Validate parameters against allowlist schemas"""
    schema = config.parameter_schemas.get(ctx.tool_name)
    if not schema:
        return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="No schema defined")
    
    errors = validate_against_schema(ctx.parameters, schema)
    if errors:
        return FirewallRuleResult(
            decision=FirewallDecision.DENY,
            reason=f"Parameter validation failed: {'; '.join(errors)}",
            metadata={"validation_errors": errors}
        )
    
    # Sanitize strings
    sanitized = {}
    for k, v in ctx.parameters.items():
        if isinstance(v, str):
            sanitized[k] = sanitize_string(v)
        else:
            sanitized[k] = v
    
    return FirewallRuleResult(
        decision=FirewallDecision.ALLOW,
        reason="Parameters valid",
        sanitized_parameters=sanitized
    )


async def rule_goal_alignment(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Check if tool call aligns with stated goal"""
    if not ctx.current_goal or not ctx.current_goal.strip():
        return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="No goal specified")
    
    score = compute_goal_match_score(ctx.current_goal, ctx.tool_name, ctx.parameters)
    
    if score < 0.15:
        return FirewallRuleResult(
            decision=FirewallDecision.REQUIRE_REVIEW,
            reason=f"Low goal alignment ({score:.2f}). Tool '{ctx.tool_name}' may not serve goal",
            metadata={"goal_match_score": score}
        )
    
    return FirewallRuleResult(
        decision=FirewallDecision.ALLOW,
        reason=f"Goal alignment: {score:.2f}",
        metadata={"goal_match_score": score}
    )


async def rule_action_budget(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Enforce hard limits on calls, cost, time"""
    calls_so_far = len(ctx.tool_call_history)
    
    if calls_so_far >= config.max_tool_calls_per_task:
        return FirewallRuleResult(
            decision=FirewallDecision.DENY,
            reason=f"Action budget exceeded: {calls_so_far}/{config.max_tool_calls_per_task}",
            metadata={"calls_used": calls_so_far, "limit": config.max_tool_calls_per_task}
        )
    
    if ctx.max_cost is not None and ctx.current_cost >= ctx.max_cost:
        return FirewallRuleResult(
            decision=FirewallDecision.DENY,
            reason=f"Cost budget exceeded: {ctx.current_cost}/{ctx.max_cost}",
            metadata={"cost_used": ctx.current_cost, "limit": ctx.max_cost}
        )
    
    if ctx.task_timeout_ms and ctx.task_start_time:
        elapsed = (time.time() - ctx.task_start_time) * 1000
        if elapsed >= ctx.task_timeout_ms:
            return FirewallRuleResult(
                decision=FirewallDecision.DENY,
                reason=f"Task timeout: {elapsed:.0f}ms > {ctx.task_timeout_ms}ms",
                metadata={"elapsed_ms": elapsed, "limit": ctx.task_timeout_ms}
            )
    
    warning = calls_so_far >= config.max_tool_calls_per_task * 0.8
    return FirewallRuleResult(
        decision=FirewallDecision.ALLOW,
        reason=f"Budget OK: {calls_so_far}/{config.max_tool_calls_per_task}",
        metadata={"calls_used": calls_so_far, "limit": config.max_tool_calls_per_task, "warning": warning}
    )


async def rule_sub_agent_depth(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Prevent excessive sub-agent nesting"""
    if ctx.agent_depth > config.max_agent_depth:
        return FirewallRuleResult(
            decision=FirewallDecision.DENY,
            reason=f"Sub-agent depth limit: {ctx.agent_depth} > {config.max_agent_depth}",
            metadata={"current": ctx.agent_depth, "max": config.max_agent_depth}
        )
    
    if ctx.agent_depth == config.max_agent_depth and ctx.tool_name in config.delegation_tools:
        return FirewallRuleResult(
            decision=FirewallDecision.DENY,
            reason=f"Cannot spawn sub-agent at max depth ({config.max_agent_depth})",
            metadata={"current": ctx.agent_depth, "max": config.max_agent_depth}
        )
    
    return FirewallRuleResult(
        decision=FirewallDecision.ALLOW,
        reason=f"Depth OK: {ctx.agent_depth}/{config.max_agent_depth}"
    )


async def rule_high_impact_tools(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Human-in-the-loop for destructive/high-impact operations"""
    if ctx.tool_name not in config.high_impact_tools:
        return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="Not high-impact")
    
    # Check specifically destructive patterns
    destructive = False
    if ctx.tool_name == "delete":
        destructive = True
    elif ctx.tool_name == "shell":
        destructive = True
    elif ctx.tool_name == "execute_code" and isinstance(ctx.parameters.get("code"), str):
        code = ctx.parameters["code"]
        # Normalize: replace all non-word chars with spaces so that
        # subprocess.run(["rm", "-rf", path]) becomes "subprocess run rm rf path ".
        # Pattern drops the literal hyphen since normalization already removed it.
        normalized_code = re.sub(r'\W+', ' ', code)
        if re.search(r"rm\s+rf|DELETE|DROP|TRUNCATE|format|shutdown", normalized_code, re.IGNORECASE):
            destructive = True
    elif ctx.tool_name == "database_write" and re.search(r"DELETE|DROP|TRUNCATE", json.dumps(ctx.parameters), re.IGNORECASE):
        destructive = True
    elif ctx.tool_name == "trigger_retell_call":
        # Phone calls are high-impact but not necessarily destructive
        destructive = True
    
    if destructive:
        return FirewallRuleResult(
            decision=FirewallDecision.REQUIRE_HUMAN_APPROVAL,
            reason=f"Destructive operation requires approval: {ctx.tool_name}",
            metadata={"tool": ctx.tool_name, "destructive": True, "params": ctx.parameters}
        )
    
    return FirewallRuleResult(
        decision=FirewallDecision.REQUIRE_REVIEW,
        reason=f"High-impact tool requires review: {ctx.tool_name}",
        metadata={"tool": ctx.tool_name, "destructive": False}
    )


async def rule_credential_scope(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """JIT credentials for sub-agents"""
    if not ctx.is_sub_agent:
        return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="Root agent has full access")
    
    required = infer_required_credentials(ctx.tool_name)
    granted = set(ctx.granted_credentials or [])
    
    for req in required:
        if req not in granted and "*" not in granted:
            return FirewallRuleResult(
                decision=FirewallDecision.DENY,
                reason=f"Sub-agent lacks credential: {req}. Granted: {list(granted)}",
                metadata={"required": req, "granted": list(granted)}
            )
    
    return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="Credential scope satisfied")


async def rule_data_leakage(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Prevent sensitive data in tool outputs"""
    if ctx.tool_name not in ["shell", "execute_code", "api_request", "send_email", "send_message", "write"]:
        return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="Not a leakage vector")
    
    patterns = [
        r"api[_-]?key", r"secret", r"password", r"token", r"credential",
        r"private[_-]?key", r"access[_-]?token", r"bearer\s+[a-zA-Z0-9\-._~+/]+=*",
        r"sk-[a-zA-Z0-9]{32,}",  # OpenAI
        r"gh[pousr]_[a-zA-Z0-9]{36,}",  # GitHub
    ]
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def check(val: Any, path: str) -> List[str]:
        found = []
        if isinstance(val, str):
            for pat in compiled:
                if pat.search(val):
                    found.append(f"Secret in {path}")
                    break
        elif isinstance(val, dict):
            for k, v in val.items():
                found.extend(check(v, f"{path}.{k}"))
        elif isinstance(val, list):
            for i, v in enumerate(val):
                found.extend(check(v, f"{path}[{i}]"))
        return found
    
    leaks = []
    for k, v in ctx.parameters.items():
        leaks.extend(check(v, k))
    
    if leaks:
        return FirewallRuleResult(
            decision=FirewallDecision.REQUIRE_REVIEW,
            reason=f"Potential secrets: {'; '.join(leaks)}",
            metadata={"leaks": leaks}
        )
    
    return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="No secrets detected")


async def rule_tool_chain_analysis(ctx: ToolCallContext, config: FirewallConfig) -> FirewallRuleResult:
    """Detect suspicious tool call sequences"""
    if len(ctx.tool_call_history) < 2:
        return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="Insufficient history")
    
    recent = ctx.tool_call_history[-5:]
    
    # Repeated denials
    denials = sum(1 for c in recent if c.get("decision") == FirewallDecision.DENY)
    if denials >= 3:
        return FirewallRuleResult(
            decision=FirewallDecision.REQUIRE_REVIEW,
            reason=f"{denials}/5 recent calls denied - possible attack loop",
            metadata={"recent_denials": denials}
        )
    
    # Repetitive cycles
    unique_tools = set(c.get("tool_name") for c in recent)
    if len(recent) >= 5 and len(unique_tools) <= 2:
        return FirewallRuleResult(
            decision=FirewallDecision.REQUIRE_REVIEW,
            reason=f"Repetitive cycle: {len(unique_tools)} tools in {len(recent)} calls",
            metadata={"unique_tools": len(unique_tools), "call_count": len(recent)}
        )
    
    # Escalation chains
    seq = " -> ".join(c.get("tool_name", "") for c in recent)
    if re.search(r"read.*write.*delete|write.*delete.*shell|shell.*execute_code", seq):
        return FirewallRuleResult(
            decision=FirewallDecision.REQUIRE_REVIEW,
            reason=f"Privilege escalation chain: {seq}",
            metadata={"sequence": seq}
        )
    
    return FirewallRuleResult(decision=FirewallDecision.ALLOW, reason="Chain analysis passed")


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC FIREWALL CLASS
# ═══════════════════════════════════════════════════════════════════════════════

# Rules in priority order (higher = runs first)
BUILTIN_RULES = [
    ("injection_detection", rule_injection_detection, 100),
    ("parameter_validation", rule_parameter_validation, 90),
    ("goal_alignment", rule_goal_alignment, 80),
    ("action_budget", rule_action_budget, 70),
    ("sub_agent_depth", rule_sub_agent_depth, 60),
    ("high_impact_tools", rule_high_impact_tools, 50),
    ("credential_scope", rule_credential_scope, 40),
    ("data_leakage", rule_data_leakage, 30),
    ("tool_chain_analysis", rule_tool_chain_analysis, 20),
]

# Sort by priority descending
BUILTIN_RULES.sort(key=lambda x: -x[2])


class SemanticFirewall:
    """Zero Trust semantic firewall for agent tool execution"""
    
    def __init__(self, config: Optional[FirewallConfig] = None):
        if config is None:
            self.config = DEFAULT_FIREWALL_CONFIG
        else:
            # Merge with defaults, preserving nested structures
            self.config = FirewallConfig(
                max_tool_calls_per_task=config.max_tool_calls_per_task,
                max_agent_depth=config.max_agent_depth,
                default_task_timeout_ms=config.default_task_timeout_ms,
                high_impact_tools=config.high_impact_tools or DEFAULT_FIREWALL_CONFIG.high_impact_tools,
                delegation_tools=config.delegation_tools or DEFAULT_FIREWALL_CONFIG.delegation_tools,
                parameter_schemas=config.parameter_schemas if config.parameter_schemas else DEFAULT_FIREWALL_CONFIG.parameter_schemas,
                debug=config.debug,
            )
        self.custom_rules: List[tuple] = []
        self.audit_log: List[FirewallAuditEntry] = []
        self.max_audit_size = 10000
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
    
    def add_custom_rule(self, name: str, func: Callable[[ToolCallContext, FirewallConfig], Awaitable[FirewallRuleResult]], priority: int = 50):
        """Add a custom rule"""
        self.custom_rules.append((name, func, priority))
        self.custom_rules.sort(key=lambda x: -x[2])
    
    def on(self, event: str, handler: Callable):
        """Register event handler"""
        self._event_handlers[event].append(handler)
    
    def _emit(self, event: str, entry: FirewallAuditEntry):
        for handler in self._event_handlers.get(event, []):
            try:
                handler(entry)
            except Exception as e:
                logger.error(f"Firewall event handler error: {e}")
    
    def _add_audit(self, entry: FirewallAuditEntry):
        self.audit_log.append(entry)
        if len(self.audit_log) > self.max_audit_size:
            self.audit_log = self.audit_log[-self.max_audit_size:]
    
    async def evaluate(self, ctx: ToolCallContext) -> Dict[str, Any]:
        """Evaluate a tool call against all firewall rules"""
        start_time = time.time()
        final_decision = FirewallDecision.ALLOW
        reasons = []
        sanitized_params = None
        matched_rules = []
        goal_match_score = None
        combined_metadata = {}
        
        # Run builtin rules
        for name, rule_func, _ in BUILTIN_RULES:
            result = await rule_func(ctx, self.config)
            matched_rules.append(name)
            
            if result.metadata:
                combined_metadata.update(result.metadata)
            
            if "goal_match_score" in result.metadata:
                goal_match_score = result.metadata["goal_match_score"]
            
            if result.sanitized_parameters:
                sanitized_params = result.sanitized_parameters
            
            reasons.append(f"[{name}] {result.reason}")
            
            # Decision precedence
            if result.decision == FirewallDecision.DENY:
                final_decision = FirewallDecision.DENY
                break
            elif result.decision == FirewallDecision.REQUIRE_HUMAN_APPROVAL and final_decision != FirewallDecision.DENY:
                final_decision = FirewallDecision.REQUIRE_HUMAN_APPROVAL
            elif result.decision == FirewallDecision.REQUIRE_REVIEW and final_decision == FirewallDecision.ALLOW:
                final_decision = FirewallDecision.REQUIRE_REVIEW
        
        # Run custom rules
        for name, rule_func, _ in self.custom_rules:
            result = await rule_func(ctx, self.config)
            matched_rules.append(f"custom:{name}")
            
            if result.metadata:
                combined_metadata.update(result.metadata)
            if "goal_match_score" in result.metadata:
                goal_match_score = result.metadata["goal_match_score"]
            if result.sanitized_parameters:
                sanitized_params = result.sanitized_parameters
            
            reasons.append(f"[custom:{name}] {result.reason}")
            
            if result.decision == FirewallDecision.DENY:
                final_decision = FirewallDecision.DENY
                break
            elif result.decision == FirewallDecision.REQUIRE_HUMAN_APPROVAL and final_decision != FirewallDecision.DENY:
                final_decision = FirewallDecision.REQUIRE_HUMAN_APPROVAL
            elif result.decision == FirewallDecision.REQUIRE_REVIEW and final_decision == FirewallDecision.ALLOW:
                final_decision = FirewallDecision.REQUIRE_REVIEW
        
        # Create audit entry
        entry = FirewallAuditEntry(
            timestamp=start_time,
            session_id=ctx.session_id,
            tool_name=ctx.tool_name,
            parameters=ctx.parameters,
            decision=final_decision,
            reasons=reasons,
            agent_depth=ctx.agent_depth,
            goal_match_score=goal_match_score,
            matched_rules=matched_rules,
        )
        self._add_audit(entry)
        
        # Emit events
        self._emit("tool_call_evaluated", entry)
        
        if final_decision == FirewallDecision.REQUIRE_HUMAN_APPROVAL and ctx.tool_name in self.config.high_impact_tools:
            self._emit("high_impact_tool_blocked", entry)
        
        if ctx.tool_name in self.config.delegation_tools and final_decision == FirewallDecision.ALLOW:
            self._emit("sub_agent_spawned", entry)
        
        if any("budget exceeded" in r.lower() for r in reasons):
            self._emit("budget_exceeded", entry)
        
        if any("injection" in r.lower() for r in reasons):
            self._emit("injection_attempt", entry)
        
        if self.config.debug:
            logger.debug(f"[Firewall] {ctx.tool_name}: {final_decision.value} ({'; '.join(reasons)})")
        
        return {
            "decision": final_decision,
            "reason": "; ".join(reasons),
            "sanitized_parameters": sanitized_params,
            "metadata": combined_metadata,
            "matched_rules": matched_rules,
        }
    
    def get_audit_log(self, session_id: Optional[str] = None, decision: Optional[FirewallDecision] = None, 
                      tool_name: Optional[str] = None, since: Optional[float] = None, 
                      limit: Optional[int] = None) -> List[FirewallAuditEntry]:
        filtered = list(self.audit_log)
        
        if session_id:
            filtered = [e for e in filtered if e.session_id == session_id]
        if decision:
            filtered = [e for e in filtered if e.decision == decision]
        if tool_name:
            filtered = [e for e in filtered if e.tool_name == tool_name]
        if since:
            filtered = [e for e in filtered if e.timestamp >= since]
        
        filtered.sort(key=lambda e: -e.timestamp)
        
        if limit:
            filtered = filtered[:limit]
        
        return filtered
    
    def get_stats(self) -> Dict[str, Any]:
        by_decision = defaultdict(int)
        by_tool = defaultdict(int)
        injection_attempts = 0
        high_impact_blocked = 0
        
        for e in self.audit_log:
            by_decision[e.decision.value] += 1
            by_tool[e.tool_name] += 1
            if any("injection" in r.lower() for r in e.reasons):
                injection_attempts += 1
            if e.decision == FirewallDecision.REQUIRE_HUMAN_APPROVAL:
                high_impact_blocked += 1
        
        return {
            "total_calls": len(self.audit_log),
            "by_decision": dict(by_decision),
            "by_tool": dict(by_tool),
            "injection_attempts": injection_attempts,
            "high_impact_blocked": high_impact_blocked,
        }
    
    def clear_audit_log(self):
        self.audit_log = []
    
    def export_config(self) -> FirewallConfig:
        return self.config


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION WITH TASKPLANNER
# ═══════════════════════════════════════════════════════════════════════════════

def create_tool_call_context(
    goal: str,
    tool_name: str,
    params: Dict[str, Any],
    session_id: str,
    agent_depth: int = 0,
    history: List[Dict] = None,
    is_sub_agent: bool = False,
    granted_credentials: List[str] = None,
    max_tool_calls: int = 20,
    max_cost: float = None,
    task_timeout_ms: int = None,
    task_start_time: float = None,
    parent_task_id: str = None,
) -> ToolCallContext:
    """Helper to create context from planner state"""
    return ToolCallContext(
        current_goal=goal,
        tool_name=tool_name,
        parameters=params,
        session_id=session_id,
        agent_depth=agent_depth,
        tool_call_history=history or [],
        is_sub_agent=is_sub_agent,
        granted_credentials=granted_credentials or [],
        max_tool_calls=max_tool_calls,
        max_cost=max_cost,
        current_cost=0.0,
        task_timeout_ms=task_timeout_ms,
        task_start_time=task_start_time or time.time(),
        parent_task_id=parent_task_id,
    )


async def firewall_guard(
    firewall: SemanticFirewall,
    goal: str,
    tool_name: str,
    params: Dict[str, Any],
    context: ToolCallContext,
) -> Dict[str, Any]:
    """
    Async wrapper to evaluate tool call through firewall.
    Returns dict with decision, sanitized params, and whether to execute.
    """
    eval_result = await firewall.evaluate(context)
    
    should_execute = eval_result["decision"] == FirewallDecision.ALLOW
    
    # Handle require_review - could be auto-approved based on policy
    if eval_result["decision"] == FirewallDecision.REQUIRE_REVIEW:
        # In production, could have auto-review logic here
        # For now, default to deny for safety
        should_execute = False
        eval_result["decision"] = FirewallDecision.DENY
        eval_result["reason"] += " (auto-denied: review required)"
    
    # Handle require_human_approval - must be externally resolved
    if eval_result["decision"] == FirewallDecision.REQUIRE_HUMAN_APPROVAL:
        should_execute = False
        # Don't auto-deny - caller must handle the approval flow
    
    return {
        "should_execute": should_execute,
        "decision": eval_result["decision"],
        "reason": eval_result["reason"],
        "sanitized_parameters": eval_result.get("sanitized_parameters"),
        "metadata": eval_result.get("metadata"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_default_firewall: Optional[SemanticFirewall] = None


def get_semantic_firewall(config: Optional[FirewallConfig] = None) -> SemanticFirewall:
    global _default_firewall
    if _default_firewall is None:
        _default_firewall = SemanticFirewall(config)
    elif config:
        _default_firewall.config = config
    return _default_firewall


def reset_semantic_firewall():
    global _default_firewall
    _default_firewall = None


__all__ = [
    "SemanticFirewall",
    "FirewallDecision",
    "FirewallConfig",
    "ToolCallContext",
    "FirewallRuleResult",
    "FirewallAuditEntry",
    "ParameterSchema",
    "ParameterProperty",
    "get_semantic_firewall",
    "reset_semantic_firewall",
    "create_tool_call_context",
    "firewall_guard",
    "BUILTIN_RULES",
    "DEFAULT_FIREWALL_CONFIG",
]