# Semantic Firewall — HermesClaw Security Layer

## Overview

The **Semantic Firewall** is a dedicated security validation layer that sits between an AI agent's "Thought" process and its "Tool Execution" capabilities. It implements a **Zero Trust** architecture for agentic systems, addressing the vulnerability categories identified in the HermesClaw security assessment:

1. **Injection Risk** (Tool Calling & Command Execution)
2. **Authorization Bypass** (Agentic Sub-loop)
3. **Data Leakage** (Memory & Logs)
4. **Resource Exhaustion** (Infinite Loops)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AGENT THOUGHT                            │
│  (LLM generates tool call intent)                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SEMANTIC FIREWALL                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ Injection   │ │ Parameter   │ │ Goal        │ │ Action    │ │
│  │ Detection   │ │ Validation  │ │ Alignment   │ │ Budget    │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ Sub-agent   │ │ High-Impact │ │ Credential  │ │ Data      │ │
│  │ Depth Limit │ │ Tool HITL   │ │ Scope (JIT) │ │ Leakage   │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Tool Chain Anomaly Detection                   ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TOOL EXECUTION                              │
│  (Only if firewall decision = ALLOW)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation

```typescript
import { SemanticFirewall, getSemanticFirewall, FirewallIntegration, getFirewallIntegration } from './runtime/semantic-firewall';
```

The firewall is available as a singleton or can be instantiated directly for custom configurations.

---

## Quick Start

```typescript
import { getSemanticFirewall, ToolCallContext } from './runtime/semantic-firewall';

// Get the default firewall instance
const firewall = getSemanticFirewall({ debug: true });

// Create a tool call context
const context: ToolCallContext = {
  currentGoal: 'Read the user configuration file and parse JSON',
  toolName: 'read',
  parameters: { path: '/home/user/config.json' },
  sessionId: 'session-123',
  agentDepth: 0,
  toolCallHistory: [],
  isSubAgent: false,
  maxToolCalls: 20,
};

// Evaluate the tool call
const result = await firewall.evaluate(context);

if (result.decision === 'allow') {
  // Execute the tool with sanitized parameters
  const params = result.sanitizedParameters || context.parameters;
  await executeTool(context.toolName, params);
} else {
  console.log(`Blocked: ${result.reason}`);
}
```

---

## Configuration

### FirewallConfig

```typescript
interface FirewallConfig {
  /** Maximum tool calls per task (default: 20) */
  maxToolCallsPerTask: number;
  
  /** Maximum sub-agent depth (default: 3) */
  maxAgentDepth: number;
  
  /** Default task timeout in milliseconds (default: 5 minutes) */
  defaultTaskTimeoutMs: number;
  
  /** High-impact tools requiring Human-in-the-Loop */
  highImpactTools: string[];
  
  /** Tools that can spawn sub-agents */
  delegationTools: string[];
  
  /** Allowed parameter schemas for validation */
  parameterSchemas: Record<string, ParameterSchema>;
  
  /** Enable debug logging */
  debug: boolean;
}
```

### Default Configuration

```typescript
const DEFAULT_FIREWALL_CONFIG = {
  maxToolCallsPerTask: 20,
  maxAgentDepth: 3,
  defaultTaskTimeoutMs: 5 * 60 * 1000, // 5 minutes
  highImpactTools: [
    'shell',           // arbitrary command execution
    'write',           // file system writes
    'delete',          // file deletion
    'execute_code',    // code execution
    'send_email',      // external communication
    'send_message',    // messaging
    'api_request',     // network requests
    'database_write',  // data modification
  ],
  delegationTools: [
    'delegate_task',
    'spawn_agent',
    'create_sub_agent',
  ],
  parameterSchemas: { /* ... */ },
  debug: false,
};
```

### Custom Configuration

```typescript
const firewall = new SemanticFirewall({
  maxToolCallsPerTask: 15,
  maxAgentDepth: 2,
  defaultTaskTimeoutMs: 3 * 60 * 1000, // 3 minutes
  highImpactTools: ['shell', 'delete', 'execute_code', 'custom_dangerous_tool'],
  delegationTools: ['delegate_task'],
  debug: true,
});
```

---

## Security Rules

### 1. Injection Detection (Priority: 100)

Detects potential indirect prompt injection in tool parameters.

**Patterns detected:**
- `ignore previous instructions`
- `system prompt`
- `you are now`
- `your new role`
- `disregard previous`
- `new persona`
- `act as`
- `pretend you are`
- `forget your`
- `override`
- `<script>` tags
- `javascript:` URLs
- `eval()` / `exec()` calls

**Decision:** `deny`

---

### 2. Parameter Schema Validation (Priority: 90)

Validates tool parameters against allowlist schemas with strict typing.

**Validations:**
- Required parameters present
- No unexpected parameters (when `additionalProperties: false`)
- Type checking (string, number, array, boolean)
- String length limits (`minLength`, `maxLength`)
- Regex pattern matching
- Enum value validation
- Format validation (URL, email, IP, UUID, filepath)
- Path traversal prevention (`../`)
- Number range validation (`minimum`, `maximum`)
- Array size limits (`maxItems`)

**Bonus:** String sanitization (removes control characters)

**Decision:** `deny` on validation failure, `allow` with sanitized parameters on success

---

### 3. Goal Alignment Check (Priority: 80)

Ensures tool calls align with the agent's stated goal using keyword-based semantic similarity.

**Threshold:** Score < 0.15 triggers review

**Decision:** `require_review` on misalignment, `allow` on alignment

**Note:** In production, replace with embedding-based similarity using a smaller model.

---

### 4. Action Budget Enforcement (Priority: 70)

Enforces hard limits on:
- Maximum tool calls per task
- Cost budget (tokens/credits)
- Task timeout

**Warning:** Emits warning at 80% budget utilization

**Decision:** `deny` when exceeded

---

### 5. Sub-Agent Depth Limit (Priority: 60)

Prevents excessive sub-agent nesting (default max: 3).

**Decision:** `deny` when depth exceeded or delegation attempted at max depth

---

### 6. High-Impact Tool Human-in-the-Loop (Priority: 50)

Requires human approval for destructive operations.

**Destructive tools (require approval):**
- `delete` - file deletion
- `shell` - arbitrary command execution
- `execute_code` with destructive patterns (`rm -rf`, `DELETE`, `DROP`, `TRUNCATE`)
- `database_write` with destructive SQL

**Non-destructive high-impact tools (require review):**
- `api_request`, `send_email`, `send_message`, `write`

**Decision:** `require_human_approval` (destructive) or `require_review` (non-destructive)

---

### 7. Credential Scope Enforcement / JIT (Priority: 40)

Implements Just-in-Time credentials for sub-agents.

**Decision:** `deny` if sub-agent lacks required credentials

**Credential mapping:**
- `api_request` → `api_access`
- `send_email` → `email_send`
- `send_message` → `messaging`
- `database_write` → `database_write`
- `shell` → `shell_access`
- `execute_code` → `code_execution`

---

### 8. Data Leakage Prevention (Priority: 30)

Prevents sensitive data exposure via tool outputs.

**Detected patterns:**
- API keys (`api_key`, `secret`, `token`, `credential`)
- Private keys (`private_key`, `access_token`)
- Bearer tokens
- OpenAI-style keys (`sk-...`)
- GitHub tokens (`ghp_...`, `gho_...`, etc.)

**Decision:** `require_review`

---

### 9. Tool Chain Anomaly Detection (Priority: 20)

Detects suspicious sequences:
- **Repeated denials:** 3+ denials in last 5 calls → possible attack loop
- **Repetitive cycles:** 5 calls alternating between ≤2 tools → possible infinite loop
- **Escalation patterns:** `read → write → delete` or `shell → execute_code` chains

**Decision:** `require_review`

---

## Firewall Decisions

| Decision | Meaning | Execution |
|----------|---------|-----------|
| `allow` | Tool call approved | Execute immediately |
| `require_review` | Needs automated review | Execute if review passes |
| `require_human_approval` | Needs human approval | Pause and wait for human |
| `deny` | Tool call blocked | Do not execute |

**Precedence:** `deny` > `require_human_approval` > `require_review` > `allow`

---

## Integration with HermesClaw

### Using FirewallIntegration

```typescript
import { getFirewallIntegration, FirewallIntegrationConfig } from './runtime/firewall-integration';
import { GatewayManager } from './electron/gateway/manager';

const config: FirewallIntegrationConfig = {
  enableForRpc: true,
  enableForAgentTools: true,
  firewallConfig: { debug: true },
  toolNameMapping: {
    'agent_read': 'read',
    'agent_write': 'write',
    'agent_shell': 'shell',
  },
  onHumanApprovalRequired: async (context, reason) => {
    // Show UI dialog to user
    return await showApprovalDialog(context, reason);
  },
  onReviewRequired: async (context, reason) => {
    // Automated review logic
    return await automatedReview(context, reason);
  },
};

const integration = getFirewallIntegration(config);

// Set gateway manager for RPC protection
const gatewayManager = new GatewayManager();
integration.setGatewayManager(gatewayManager);

// Create agent session
const session = integration.createSession({
  sessionId: 'agent-session-1',
  goal: 'Analyze the codebase and generate documentation',
  maxToolCalls: 20,
});

// Evaluate tool calls
const result = await integration.evaluateToolCall({
  sessionId: 'agent-session-1',
  toolName: 'read',
  parameters: { path: '/project/src/main.ts' },
});

if (result.shouldExecute) {
  await executeTool(result.toolName, result.sanitizedParameters);
}

// Spawn sub-agent with limited permissions
const subSession = await integration.spawnSubAgent({
  parentSessionId: 'agent-session-1',
  subSessionId: 'sub-agent-1',
  goal: 'Extract API endpoints from route files',
  allowedTools: ['read', 'grep'],
  grantedCredentials: ['file_read'],
  maxToolCalls: 10,
});
```

### Protected RPC Calls

```typescript
// RPC calls that go through the firewall
const result = await integration.firewallRpc({
  sessionId: 'agent-session-1',
  method: 'tools.read',
  rpcParams: { path: '/project/config.json' },
});
```

---

## Audit & Monitoring

### Audit Log

```typescript
// Get all audit entries for a session
const logs = firewall.getAuditLog({ sessionId: 'session-123' });

// Filter by decision
const denied = firewall.getAuditLog({ decision: 'deny' });

// Filter by tool
const shellCalls = firewall.getAuditLog({ toolName: 'shell' });

// Recent entries with limit
const recent = firewall.getAuditLog({ since: Date.now() - 3600000, limit: 100 });
```

### Statistics

```typescript
const stats = firewall.getStats();
/*
{
  totalCalls: 150,
  byDecision: {
    allow: 120,
    deny: 5,
    require_human_approval: 10,
    require_review: 15,
  },
  byTool: {
    read: 50,
    write: 30,
    shell: 20,
    ...
  },
  injectionAttempts: 2,
  highImpactBlocked: 10,
}
```
```

---

## Events

```typescript
firewall.on('tool-call-evaluated', (entry) => {
  // Every tool call evaluation
  metrics.increment('firewall.evaluated');
});

firewall.on('high-impact-tool-blocked', (entry) => {
  // High-impact tool required approval
  alerting.notify('high-impact-blocked', entry);
});

firewall.on('sub-agent-spawned', (entry) => {
  // Sub-agent delegation approved
  metrics.increment('firewall.sub_agent_spawned');
});

firewall.on('budget-exceeded', (entry) => {
  // Action budget exceeded
  alerting.notify('budget-exceeded', entry);
});

firewall.on('injection-attempt', (entry) => {
  // CRITICAL: Injection attempt detected
  alerting.critical('INJECTION_ATTEMPT', entry);
  // Consider automatic session termination
});
```

---

## Extending with Custom Rules

```typescript
firewall.addRule({
  id: 'custom-pii-detection',
  name: 'PII Detection',
  description: 'Detects personally identifiable information in tool outputs',
  priority: 25, // Between data leakage and tool chain
  toolNames: ['write', 'send_email', 'api_request'],
  async evaluate(context) {
    const piiPatterns = [
      /\b\d{3}-\d{2}-\d{4}\b/, // SSN
      /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/, // Credit card
      /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/, // Email
    ];
    
    for (const [key, value] of Object.entries(context.parameters)) {
      if (typeof value === 'string') {
        for (const pattern of piiPatterns) {
          if (pattern.test(value)) {
            return {
              decision: 'require_review',
              reason: `PII detected in ${key}`,
              metadata: { piiType: pattern.source },
            };
          }
        }
      }
    }
    return { decision: 'allow', reason: 'No PII detected' };
  },
});
```

---

## Production Deployment Checklist

- [ ] Replace keyword-based goal alignment with embedding similarity
- [ ] Configure human approval UI integration
- [ ] Set up alerting for injection attempts
- [ ] Configure audit log retention policy
- [ ] Define parameter schemas for all custom tools
- [ ] Set appropriate budget limits per agent type
- [ ] Configure credential mapping for your tool set
- [ ] Test with adversarial inputs
- [ ] Enable debug logging in staging only
- [ ] Set up metrics dashboards

---

## API Reference

### SemanticFirewall Class

| Method | Description |
|--------|-------------|
| `evaluate(context)` | Evaluate a tool call |
| `getAuditLog(filter?)` | Retrieve audit entries |
| `getStats()` | Get firewall statistics |
| `addRule(rule)` | Add custom rule |
| `removeRule(ruleId)` | Remove rule by ID |
| `updateConfig(config)` | Update configuration |
| `exportConfig()` | Export current config |
| `clearAuditLog()` | Clear audit log |

### FirewallIntegration Class

| Method | Description |
|--------|-------------|
| `createSession(params)` | Create agent session |
| `getSession(sessionId)` | Get session by ID |
| `deleteSession(sessionId)` | Delete session |
| `evaluateToolCall(params)` | Evaluate tool call |
| `firewallRpc(params)` | Protected RPC call |
| `spawnSubAgent(params)` | Spawn sub-agent |
| `setGatewayManager(manager)` | Set gateway manager |
| `getStats()` | Get statistics |
| `getSessionAuditLog(sessionId)` | Get session audit log |
| `getFirewall()` | Get underlying firewall |

---

## Files

- `HermesClaw/runtime/semantic-firewall.ts` - Core firewall implementation
- `HermesClaw/runtime/firewall-integration.ts` - HermesClaw integration layer
- `HermesClaw/runtime/__tests__/semantic-firewall.test.ts` - Unit tests
- `HermesClaw/runtime/SEMANTIC_FIREWALL.md` - This documentation

---

## Related Security Components

- `app/core/guardrails.py` - Python-side URL validation & input sanitization
- `app/core/hardening.py` - Circuit breakers, rate limiting, error recovery
- `app/core/sentinel.py` - Credential failure escalation
- `electron/gateway/manager.ts` - Gateway process management
- `electron/services/secrets/secret-store.ts` - Secure credential storage

---

*Generated as part of the HermesClaw Zero Trust Architecture implementation*