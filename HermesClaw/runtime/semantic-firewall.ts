/**
 * Semantic Firewall — HermesClaw Security Layer
 * 
 * Implements a dedicated validation layer between the agent's "Thought" 
 * and its "Tool Execution" as recommended in the vulnerability assessment.
 * 
 * Based on Zero Trust model for AI agents:
 * - Instruction Hierarchy Enforcement (System vs Data separation)
 * - Deterministic Parameter Validation (Allowlist-based)
 * - Principle of Least Privilege (JIT credentials)
 * - Human-in-the-Loop for High-Impact Tools
 * - Hard Action Budgets & Termination Conditions
 */

import { EventEmitter } from 'events';
import { logger } from '../../electron/utils/logger';

// ──────────────────────────────────────────────────────────────────────────────
// TYPES & INTERFACES
// ──────────────────────────────────────────────────────────────────────────────

export type FirewallDecision = 'allow' | 'deny' | 'require_human_approval' | 'require_review';

export interface ToolCallContext {
  /** The agent's current goal/task description */
  currentGoal: string;
  /** Tool being invoked */
  toolName: string;
  /** Tool parameters */
  parameters: Record<string, unknown>;
  /** Agent session ID */
  sessionId: string;
  /** Parent task ID (for sub-agent tracking) */
  parentTaskId?: string;
  /** Sub-agent depth (0 = root agent) */
  agentDepth: number;
  /** Tools already called in this task */
  toolCallHistory: ToolCallRecord[];
  /** Whether this is a sub-agent spawned via delegate_task */
  isSubAgent: boolean;
  /** JIT credentials granted to this agent */
  grantedCredentials?: string[];
  /** Maximum tool calls allowed for this task */
  maxToolCalls: number;
  /** Maximum cost (tokens/credits) for this task */
  maxCost?: number;
  /** Current cost accumulated */
  currentCost?: number;
  /** Task timeout (ms) */
  taskTimeoutMs?: number;
  /** Task start time */
  taskStartTime?: number;
}

export interface ToolCallRecord {
  toolName: string;
  parameters: Record<string, unknown>;
  timestamp: number;
  decision: FirewallDecision;
  reason?: string;
}

export interface FirewallRule {
  id: string;
  name: string;
  description: string;
  /** Priority: higher runs first */
  priority: number;
  /** Tool names this rule applies to ('*' for all) */
  toolNames: string[];
  /** Condition function */
  evaluate: (context: ToolCallContext) => Promise<FirewallRuleResult>;
}

export interface FirewallRuleResult {
  decision: FirewallDecision;
  reason: string;
  /** Modified parameters (for sanitization) */
  sanitizedParameters?: Record<string, unknown>;
  /** Metadata for audit logging */
  metadata?: Record<string, unknown>;
}

export interface FirewallConfig {
  /** Maximum tool calls per task (default: 20) */
  maxToolCallsPerTask: number;
  /** Maximum sub-agent depth (default: 3) */
  maxAgentDepth: number;
  /** Default task timeout (default: 5 minutes) */
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

export interface ParameterSchema {
  type: 'object';
  properties: Record<string, ParameterProperty>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface ParameterProperty {
  type: string | string[];
  description?: string;
  enum?: unknown[];
  pattern?: string;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  format?: 'ip' | 'filepath' | 'url' | 'email' | 'uuid';
  items?: ParameterProperty;
  additionalProperties?: boolean | ParameterProperty;
  maxItems?: number;
}

export interface FirewallAuditEntry {
  timestamp: number;
  sessionId: string;
  toolName: string;
  parameters: Record<string, unknown>;
  decision: FirewallDecision;
  reasons: string[];
  agentDepth: number;
  goalMatchScore?: number;
  matchedRules: string[];
}

export interface SemanticFirewallEvents {
  'tool-call-evaluated': (entry: FirewallAuditEntry) => void;
  'high-impact-tool-blocked': (entry: FirewallAuditEntry) => void;
  'sub-agent-spawned': (entry: FirewallAuditEntry) => void;
  'budget-exceeded': (entry: FirewallAuditEntry) => void;
  'injection-attempt': (entry: FirewallAuditEntry) => void;
}

// ──────────────────────────────────────────────────────────────────────────────
// DEFAULT CONFIGURATION
// ──────────────────────────────────────────────────────────────────────────────

export const DEFAULT_FIREWALL_CONFIG: FirewallConfig = {
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
  parameterSchemas: {
    shell: {
      type: 'object',
      properties: {
        command: { type: 'string', maxLength: 500 },
        args: { type: 'array', items: { type: 'string', maxLength: 200 } },
        cwd: { type: 'string', format: 'filepath', maxLength: 500 },
      },
      required: ['command'],
      additionalProperties: false,
    },
    write: {
      type: 'object',
      properties: {
        path: { type: 'string', format: 'filepath', maxLength: 500 },
        content: { type: 'string', maxLength: 100000 },
      },
      required: ['path', 'content'],
      additionalProperties: false,
    },
    read: {
      type: 'object',
      properties: {
        path: { type: 'string', format: 'filepath', maxLength: 500 },
      },
      required: ['path'],
      additionalProperties: false,
    },
    delete: {
      type: 'object',
      properties: {
        path: { type: 'string', format: 'filepath', maxLength: 500 },
        recursive: { type: 'boolean' },
      },
      required: ['path'],
      additionalProperties: false,
    },
    execute_code: {
      type: 'object',
      properties: {
        code: { type: 'string', maxLength: 50000 },
        language: { type: 'string', enum: ['python', 'javascript', 'typescript', 'bash'] },
        timeoutMs: { type: 'number', minimum: 1000, maximum: 300000 },
      },
      required: ['code', 'language'],
      additionalProperties: false,
    },
    api_request: {
      type: 'object',
      properties: {
        url: { type: 'string', format: 'url', maxLength: 2048 },
        method: { type: 'string', enum: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] },
        headers: { type: 'object', additionalProperties: { type: 'string' } },
        body: { type: 'string', maxLength: 100000 },
      },
      required: ['url', 'method'],
      additionalProperties: false,
    },
    delegate_task: {
      type: 'object',
      properties: {
        task: { type: 'string', minLength: 10, maxLength: 5000 },
        requiredSkills: { type: 'array', items: { type: 'string' }, maxItems: 10 },
        allowedTools: { type: 'array', items: { type: 'string' }, maxItems: 20 },
        maxToolCalls: { type: 'number', minimum: 1, maximum: 20 },
        credentials: { type: 'array', items: { type: 'string' }, maxItems: 5 },
      },
      required: ['task'],
      additionalProperties: false,
    },
  },
  debug: false,
};

// ──────────────────────────────────────────────────────────────────────────────
// UTILITY FUNCTIONS
// ──────────────────────────────────────────────────────────────────────────────

function validateParameter(value: unknown, property: ParameterProperty, path: string): string | null {
  // Type check
  const expectedTypes = Array.isArray(property.type) ? property.type : [property.type];
  const actualType = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
  
  if (!expectedTypes.includes(actualType)) {
    return `Parameter '${path}': expected type ${expectedTypes.join('|')}, got ${actualType}`;
  }

  // String validations
  if (actualType === 'string') {
    const str = value as string;
    if (property.minLength !== undefined && str.length < property.minLength) {
      return `Parameter '${path}': length ${str.length} < minimum ${property.minLength}`;
    }
    if (property.maxLength !== undefined && str.length > property.maxLength) {
      return `Parameter '${path}': length ${str.length} > maximum ${property.maxLength}`;
    }
    if (property.pattern !== undefined) {
      const regex = new RegExp(property.pattern);
      if (!regex.test(str)) {
        return `Parameter '${path}': does not match pattern ${property.pattern}`;
      }
    }
    if (property.enum !== undefined && !property.enum.includes(value)) {
      return `Parameter '${path}': value not in allowed enum`;
    }
    // Format validations
    if (property.format === 'url') {
      try {
        new URL(str);
      } catch {
        return `Parameter '${path}': invalid URL format`;
      }
    }
    if (property.format === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(str)) {
      return `Parameter '${path}': invalid email format`;
    }
    if (property.format === 'ip' && !/^(\d{1,3}\.){3}\d{1,3}$/.test(str)) {
      return `Parameter '${path}': invalid IP format`;
    }
    if (property.format === 'uuid' && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(str)) {
      return `Parameter '${path}': invalid UUID format`;
    }
    // File path validation - block path traversal
    if (property.format === 'filepath' && /\.\./.test(str)) {
      return `Parameter '${path}': path traversal attempt detected`;
    }
  }

  // Number validations
  if (actualType === 'number') {
    const num = value as number;
    if (property.minimum !== undefined && num < property.minimum) {
      return `Parameter '${path}': value ${num} < minimum ${property.minimum}`;
    }
    if (property.maximum !== undefined && num > property.maximum) {
      return `Parameter '${path}': value ${num} > maximum ${property.maximum}`;
    }
  }

  // Array validations
  if (actualType === 'array') {
    const arr = value as unknown[];
    if (property.maxLength !== undefined && arr.length > property.maxLength) {
      return `Parameter '${path}': array length ${arr.length} > maximum ${property.maxLength}`;
    }
  }

  return null;
}

function validateAgainstSchema(parameters: Record<string, unknown>, schema: ParameterSchema): string[] {
  const errors: string[] = [];
  const props = schema.properties;
  
  // Check required fields
  if (schema.required) {
    for (const req of schema.required) {
      if (!(req in parameters)) {
        errors.push(`Missing required parameter: ${req}`);
      }
    }
  }

  // Check each provided parameter
  for (const [key, value] of Object.entries(parameters)) {
    const prop = props[key];
    if (!prop) {
      if (schema.additionalProperties === false) {
        errors.push(`Unexpected parameter: ${key}`);
      }
      continue;
    }
    const error = validateParameter(value, prop, key);
    if (error) errors.push(error);
  }

  return errors;
}

function sanitizeString(str: string): string {
  // Remove control characters except newlines/tabs
  return str.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
}

function computeGoalMatchScore(goal: string, toolName: string, parameters: Record<string, unknown>): number {
  /**
   * Semantic similarity check between the stated goal and the tool call.
   * Returns a score 0-1 indicating alignment.
   * In production, this would use an embedding model or smaller LLM.
   */
  const goalLower = goal.toLowerCase();
  const toolLower = toolName.toLowerCase();
  
  // Keyword-based heuristic (replace with embedding similarity in production)
  const goalKeywords = goalLower.match(/\b\w+\b/g) || [];
  const toolKeywords = toolLower.match(/\b\w+\b/g) || [];
  
  let matches = 0;
  for (const gk of goalKeywords) {
    for (const tk of toolKeywords) {
      if (gk === tk || gk.includes(tk) || tk.includes(gk)) {
        matches++;
        break;
      }
    }
  }
  
  // Check parameter values against goal
  const paramStr = JSON.stringify(parameters).toLowerCase();
  for (const gk of goalKeywords) {
    if (paramStr.includes(gk)) matches++;
  }
  
  const totalKeywords = goalKeywords.length + toolKeywords.length;
  return totalKeywords > 0 ? Math.min(1, matches / totalKeywords) : 0.5;
}

// ──────────────────────────────────────────────────────────────────────────────
// BUILT-IN FIREWALL RULES
// ──────────────────────────────────────────────────────────────────────────────

function createInjectionDetectionRule(): FirewallRule {
  return {
    id: 'injection-detection',
    name: 'Prompt Injection Detection',
    description: 'Detects potential indirect prompt injection in tool parameters',
    priority: 100,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      const injectionPatterns = [
        /ignore\s+(previous|all)\s+instructions?/i,
        /system\s+prompt/i,
        /you\s+are\s+now/i,
        /your\s+new\s+role/i,
        /disregard\s+(previous|all)/i,
        /new\s+persona/i,
        /act\s+as/i,
        /pretend\s+you\s+are/i,
        /forget\s+your/i,
        /override/i,
        /<script/i,
        /javascript:/i,
        /data:/i,
        /eval\s*\(/i,
        /exec\s*\(/i,
      ];
      
      const checkValue = (val: unknown, path: string): string | null => {
        if (typeof val === 'string') {
          for (const pattern of injectionPatterns) {
            if (pattern.test(val)) {
              return `Potential injection detected in ${path}: matched pattern ${pattern.source}`;
            }
          }
        } else if (typeof val === 'object' && val !== null) {
          for (const [k, v] of Object.entries(val)) {
            const result = checkValue(v, `${path}.${k}`);
            if (result) return result;
          }
        }
        return null;
      };
      
      for (const [key, value] of Object.entries(context.parameters)) {
        const detection = checkValue(value, key);
        if (detection) {
          return {
            decision: 'deny',
            reason: detection,
            metadata: { detectionType: 'prompt_injection', parameter: key },
          };
        }
      }
      
      return { decision: 'allow', reason: 'No injection patterns detected' };
    },
  };
}

function createParameterValidationRule(config: FirewallConfig): FirewallRule {
  return {
    id: 'parameter-validation',
    name: 'Parameter Schema Validation',
    description: 'Validates tool parameters against allowlist schemas',
    priority: 90,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      const schema = config.parameterSchemas[context.toolName];
      if (!schema) {
        // No schema defined - allow but log warning
        return { decision: 'allow', reason: 'No parameter schema defined for tool' };
      }
      
      const errors = validateAgainstSchema(context.parameters, schema);
      if (errors.length > 0) {
        return {
          decision: 'deny',
          reason: `Parameter validation failed: ${errors.join('; ')}`,
          metadata: { validationErrors: errors },
        };
      }
      
      // Sanitize string parameters
      const sanitized: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(context.parameters)) {
        if (typeof value === 'string') {
          sanitized[key] = sanitizeString(value);
        } else {
          sanitized[key] = value;
        }
      }
      
      return { 
        decision: 'allow', 
        reason: 'Parameters valid',
        sanitizedParameters: sanitized,
      };
    },
  };
}

function createGoalAlignmentRule(): FirewallRule {
  return {
    id: 'goal-alignment',
    name: 'Goal-Tool Alignment Check',
    description: 'Ensures tool calls align with the agent\'s stated goal',
    priority: 80,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      if (!context.currentGoal || context.currentGoal.trim().length === 0) {
        return { decision: 'allow', reason: 'No goal specified, skipping alignment check' };
      }
      
      const score = computeGoalMatchScore(context.currentGoal, context.toolName, context.parameters);
      
      // Threshold: below 0.15 suggests potential misalignment
      if (score < 0.15) {
        return {
          decision: 'require_review',
          reason: `Low goal alignment score (${score.toFixed(2)}). Tool '${context.toolName}' may not serve goal: "${context.currentGoal}"`,
          metadata: { goalMatchScore: score },
        };
      }
      
      return { 
        decision: 'allow', 
        reason: `Goal alignment score: ${score.toFixed(2)}`,
        metadata: { goalMatchScore: score },
      };
    },
  };
}

function createActionBudgetRule(config: FirewallConfig): FirewallRule {
  return {
    id: 'action-budget',
    name: 'Action Budget Enforcement',
    description: 'Enforces maximum tool calls and cost per task',
    priority: 70,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      // Check tool call count
      const toolCallsSoFar = context.toolCallHistory.length;
      if (toolCallsSoFar >= config.maxToolCallsPerTask) {
        return {
          decision: 'deny',
          reason: `Action budget exceeded: ${toolCallsSoFar}/${config.maxToolCallsPerTask} tool calls used`,
          metadata: { toolCallsUsed: toolCallsSoFar, limit: config.maxToolCallsPerTask },
        };
      }
      
      // Check cost budget
      if (context.maxCost !== undefined && context.currentCost !== undefined) {
        if (context.currentCost >= context.maxCost) {
          return {
            decision: 'deny',
            reason: `Cost budget exceeded: ${context.currentCost}/${context.maxCost}`,
            metadata: { costUsed: context.currentCost, limit: context.maxCost },
          };
        }
      }
      
      // Check timeout
      if (context.taskTimeoutMs && context.taskStartTime) {
        const elapsed = Date.now() - context.taskStartTime;
        if (elapsed >= context.taskTimeoutMs) {
          return {
            decision: 'deny',
            reason: `Task timeout exceeded: ${elapsed}ms > ${context.taskTimeoutMs}ms`,
            metadata: { elapsedMs: elapsed, limit: context.taskTimeoutMs },
          };
        }
      }
      
      // Warning at 80% budget
      const atWarningThreshold = toolCallsSoFar >= config.maxToolCallsPerTask * 0.8;
      
      return { 
        decision: 'allow', 
        reason: `Budget OK: ${toolCallsSoFar}/${config.maxToolCallsPerTask} calls`,
        metadata: { 
          toolCallsUsed: toolCallsSoFar, 
          limit: config.maxToolCallsPerTask,
          warning: atWarningThreshold,
        },
      };
    },
  };
}

function createSubAgentDepthRule(config: FirewallConfig): FirewallRule {
  return {
    id: 'sub-agent-depth',
    name: 'Sub-Agent Depth Limit',
    description: 'Prevents excessive sub-agent nesting',
    priority: 60,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      if (context.agentDepth > config.maxAgentDepth) {
        return {
          decision: 'deny',
          reason: `Sub-agent depth limit exceeded: ${context.agentDepth} > ${config.maxAgentDepth}`,
          metadata: { currentDepth: context.agentDepth, maxDepth: config.maxAgentDepth },
        };
      }
      
      if (context.agentDepth === config.maxAgentDepth && 
          config.delegationTools.includes(context.toolName)) {
        return {
          decision: 'deny',
          reason: `Cannot spawn sub-agent at maximum depth (${config.maxAgentDepth})`,
          metadata: { currentDepth: context.agentDepth, maxDepth: config.maxAgentDepth },
        };
      }
      
      return { decision: 'allow', reason: `Sub-agent depth OK: ${context.agentDepth}/${config.maxAgentDepth}` };
    },
  };
}

function createHighImpactToolRule(config: FirewallConfig): FirewallRule {
  return {
    id: 'high-impact-tools',
    name: 'High-Impact Tool Human-in-the-Loop',
    description: 'Requires human approval for destructive/high-impact operations',
    priority: 50,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      if (!config.highImpactTools.includes(context.toolName)) {
        return { decision: 'allow', reason: 'Not a high-impact tool' };
      }
      
      // Check if this specific call is especially dangerous
      const isDestructive = 
        context.toolName === 'delete' ||
        context.toolName === 'shell' ||
        (context.toolName === 'execute_code' && 
         typeof context.parameters.code === 'string' && 
         /rm\s+-rf|DELETE|DROP|TRUNCATE|format/i.test(context.parameters.code)) ||
        (context.toolName === 'database_write' &&
         /DELETE|DROP|TRUNCATE/i.test(JSON.stringify(context.parameters)));
      
      if (isDestructive) {
        return {
          decision: 'require_human_approval',
          reason: `Destructive operation requires human approval: ${context.toolName}`,
          metadata: { 
            toolName: context.toolName, 
            isDestructive: true,
            parameters: context.parameters,
          },
        };
      }
      
      // Non-destructive high-impact tools still need review
      return {
        decision: 'require_review',
        reason: `High-impact tool requires review: ${context.toolName}`,
        metadata: { toolName: context.toolName, isDestructive: false },
      };
    },
  };
}

function createCredentialScopeRule(): FirewallRule {
  return {
    id: 'credential-scope',
    name: 'Credential Scope Enforcement (JIT)',
    description: 'Ensures sub-agents only use granted credentials',
    priority: 40,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      if (!context.isSubAgent) {
        return { decision: 'allow', reason: 'Root agent has full credential access' };
      }
      
      // Check if tool requires credentials not granted to sub-agent
      const requiredCredentials = inferRequiredCredentials(context.toolName, context.parameters);
      const grantedCredentials = context.grantedCredentials || [];
      
      for (const required of requiredCredentials) {
        if (!grantedCredentials.includes(required) && !grantedCredentials.includes('*')) {
          return {
            decision: 'deny',
            reason: `Sub-agent lacks required credential: ${required}. Granted: [${grantedCredentials.join(', ')}]`,
            metadata: { requiredCredential: required, grantedCredentials },
          };
        }
      }
      
      return { decision: 'allow', reason: 'Credential scope satisfied' };
    },
  };
}

function inferRequiredCredentials(toolName: string, parameters: Record<string, unknown>): string[] {
  const credMap: Record<string, string[]> = {
    api_request: ['api_access'],
    send_email: ['email_send'],
    send_message: ['messaging'],
    database_write: ['database_write'],
    shell: ['shell_access'],
    execute_code: ['code_execution'],
  };
  return credMap[toolName] || [];
}

function createDataLeakagePreventionRule(): FirewallRule {
  return {
    id: 'data-leakage-prevention',
    name: 'Data Leakage Prevention',
    description: 'Prevents sensitive data from being exposed via tool outputs',
    priority: 30,
    toolNames: ['shell', 'execute_code', 'api_request', 'send_email', 'send_message', 'write'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      const sensitivePatterns = [
        /api[_-]?key/i,
        /secret/i,
        /password/i,
        /token/i,
        /credential/i,
        /private[_-]?key/i,
        /access[_-]?token/i,
        /bearer\s+[a-zA-Z0-9\-._~+/]+=*/i,
        /sk-[a-zA-Z0-9]{32,}/i, // OpenAI-style keys
        /gh[pousr]_[a-zA-Z0-9]{36,}/i, // GitHub tokens
      ];
      
      const checkForSecrets = (val: unknown, path: string): string[] => {
        const found: string[] = [];
        if (typeof val === 'string') {
          for (const pattern of sensitivePatterns) {
            if (pattern.test(val)) {
              found.push(`Potential secret in ${path}`);
              break;
            }
          }
        } else if (typeof val === 'object' && val !== null) {
          for (const [k, v] of Object.entries(val)) {
            found.push(...checkForSecrets(v, `${path}.${k}`));
          }
        }
        return found;
      };
      
      const leaks: string[] = [];
      for (const [key, value] of Object.entries(context.parameters)) {
        leaks.push(...checkForSecrets(value, key));
      }
      
      if (leaks.length > 0) {
        return {
          decision: 'require_review',
          reason: `Potential sensitive data in parameters: ${leaks.join('; ')}`,
          metadata: { leaks },
        };
      }
      
      return { decision: 'allow', reason: 'No sensitive data patterns detected' };
    },
  };
}

function createToolChainAnalysisRule(): FirewallRule {
  return {
    id: 'tool-chain-analysis',
    name: 'Tool Chain Anomaly Detection',
    description: 'Detects suspicious sequences of tool calls',
    priority: 20,
    toolNames: ['*'],
    async evaluate(context: ToolCallContext): Promise<FirewallRuleResult> {
      if (context.toolCallHistory.length < 2) {
        return { decision: 'allow', reason: 'Insufficient history for chain analysis' };
      }
      
      // Check for repeated failed attempts
      const recentCalls = context.toolCallHistory.slice(-5);
      const failures = recentCalls.filter(c => c.decision === 'deny').length;
      if (failures >= 3) {
        return {
          decision: 'require_review',
          reason: `${failures}/5 recent tool calls denied - possible attack loop`,
          metadata: { recentDenials: failures },
        };
      }
      
      // Check for rapid tool cycling (potential infinite loop)
      const uniqueTools = new Set(recentCalls.map(c => c.toolName));
      if (recentCalls.length >= 5 && uniqueTools.size <= 2) {
        return {
          decision: 'require_review',
          reason: 'Repetitive tool cycle detected - possible infinite loop',
          metadata: { uniqueTools: uniqueTools.size, callCount: recentCalls.length },
        };
      }
      
      // Check for escalation pattern (read -> write -> delete)
      const toolSequence = recentCalls.map(c => c.toolName).join(' -> ');
      const escalationPattern = /read.*write.*delete|write.*delete.*shell|shell.*execute_code/.test(toolSequence);
      if (escalationPattern) {
        return {
          decision: 'require_review',
          reason: 'Potential privilege escalation chain detected',
          metadata: { sequence: toolSequence },
        };
      }
      
      return { decision: 'allow', reason: 'Tool chain analysis passed' };
    },
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// SEMANTIC FIREWALL CLASS
// ──────────────────────────────────────────────────────────────────────────────

export class SemanticFirewall extends EventEmitter {
  private config: FirewallConfig;
  private rules: FirewallRule[];
  private auditLog: FirewallAuditEntry[] = [];
  private maxAuditLogSize = 10000;
  
  constructor(config: Partial<FirewallConfig> = {}) {
    super();
    this.config = { ...DEFAULT_FIREWALL_CONFIG, ...config };
    this.rules = this.buildDefaultRules();
  }
  
  private buildDefaultRules(): FirewallRule[] {
    return [
      createInjectionDetectionRule(),
      createParameterValidationRule(this.config),
      createGoalAlignmentRule(),
      createActionBudgetRule(this.config),
      createSubAgentDepthRule(this.config),
      createHighImpactToolRule(this.config),
      createCredentialScopeRule(),
      createDataLeakagePreventionRule(),
      createToolChainAnalysisRule(),
    ].sort((a, b) => b.priority - a.priority); // Higher priority first
  }
  
  /**
   * Evaluate a tool call against all firewall rules
   */
  async evaluate(context: ToolCallContext): Promise<{
    decision: FirewallDecision;
    reason: string;
    sanitizedParameters?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    matchedRules: string[];
  }> {
    const startTime = Date.now();
    let finalDecision: FirewallDecision = 'allow';
    const reasons: string[] = [];
    let sanitizedParameters: Record<string, unknown> | undefined;
    const matchedRules: string[] = [];
    let goalMatchScore: number | undefined;
    const combinedMetadata: Record<string, unknown> = {};
    
    // Run all rules
    for (const rule of this.rules) {
      if (rule.toolNames.includes('*') || rule.toolNames.includes(context.toolName)) {
        const result = await rule.evaluate(context);
        matchedRules.push(rule.id);
        
        if (result.metadata) {
          Object.assign(combinedMetadata, result.metadata);
        }
        
        // Extract goal match score
        if (result.metadata?.goalMatchScore !== undefined) {
          goalMatchScore = result.metadata.goalMatchScore as number;
        }
        
        // Sanitized parameters from validation rule
        if (result.sanitizedParameters) {
          sanitizedParameters = result.sanitizedParameters;
        }
        
        // Track reasons
        reasons.push(`[${rule.name}] ${result.reason}`);
        
        // Decision precedence: deny > require_human_approval > require_review > allow
        if (result.decision === 'deny') {
          finalDecision = 'deny';
          break;
        }
        if (result.decision === 'require_human_approval') {
          finalDecision = 'require_human_approval';
        } else if (result.decision === 'require_review' && finalDecision === 'allow') {
          finalDecision = 'require_review';
        }
      }
    }
    
    // Create audit entry
    const auditEntry: FirewallAuditEntry = {
      timestamp: startTime,
      sessionId: context.sessionId,
      toolName: context.toolName,
      parameters: context.parameters,
      decision: finalDecision,
      reasons,
      agentDepth: context.agentDepth,
      goalMatchScore,
      matchedRules,
    };
    
    this.addAuditEntry(auditEntry);
    
    // Emit events
    this.emit('tool-call-evaluated', auditEntry);
    
    if (finalDecision === 'require_human_approval' && this.config.highImpactTools.includes(context.toolName)) {
      this.emit('high-impact-tool-blocked', auditEntry);
    }
    
    if (this.config.delegationTools.includes(context.toolName) && finalDecision === 'allow') {
      this.emit('sub-agent-spawned', auditEntry);
    }
    
    if (reasons.some(r => r.includes('budget exceeded'))) {
      this.emit('budget-exceeded', auditEntry);
    }
    
    if (reasons.some(r => r.includes('injection'))) {
      this.emit('injection-attempt', auditEntry);
    }
    
    if (this.config.debug) {
      logger.debug(`[SemanticFirewall] ${context.toolName}: ${finalDecision} (${reasons.join('; ')})`);
    }
    
    return {
      decision: finalDecision,
      reason: reasons.join('; '),
      sanitizedParameters,
      metadata: combinedMetadata,
      matchedRules,
    };
  }
  
  private addAuditEntry(entry: FirewallAuditEntry): void {
    this.auditLog.push(entry);
    if (this.auditLog.length > this.maxAuditLogSize) {
      this.auditLog = this.auditLog.slice(-this.maxAuditLogSize);
    }
  }
  
  /**
   * Get audit log entries
   */
  getAuditLog(filter?: {
    sessionId?: string;
    toolName?: string;
    decision?: FirewallDecision;
    since?: number;
    limit?: number;
  }): FirewallAuditEntry[] {
    let filtered = [...this.auditLog];
    
    if (filter?.sessionId) {
      filtered = filtered.filter(e => e.sessionId === filter.sessionId);
    }
    if (filter?.toolName) {
      filtered = filtered.filter(e => e.toolName === filter.toolName);
    }
    if (filter?.decision) {
      filtered = filtered.filter(e => e.decision === filter.decision);
    }
    if (filter?.since) {
      filtered = filtered.filter(e => e.timestamp >= filter.since!);
    }
    
    filtered.sort((a, b) => b.timestamp - a.timestamp);
    
    if (filter?.limit) {
      filtered = filtered.slice(0, filter.limit);
    }
    
    return filtered;
  }
  
  /**
   * Get statistics
   */
  getStats(): {
    totalCalls: number;
    byDecision: Record<FirewallDecision, number>;
    byTool: Record<string, number>;
    injectionAttempts: number;
    highImpactBlocked: number;
  } {
    const byDecision: Record<FirewallDecision, number> = {
      allow: 0,
      deny: 0,
      require_human_approval: 0,
      require_review: 0,
    };
    const byTool: Record<string, number> = {};
    let injectionAttempts = 0;
    let highImpactBlocked = 0;
    
    for (const entry of this.auditLog) {
      byDecision[entry.decision]++;
      byTool[entry.toolName] = (byTool[entry.toolName] || 0) + 1;
      if (entry.reasons.some(r => r.includes('injection'))) injectionAttempts++;
      if (entry.decision === 'require_human_approval') highImpactBlocked++;
    }
    
    return {
      totalCalls: this.auditLog.length,
      byDecision,
      byTool,
      injectionAttempts,
      highImpactBlocked,
    };
  }
  
  /**
   * Add a custom rule
   */
  addRule(rule: FirewallRule): void {
    this.rules.push(rule);
    this.rules.sort((a, b) => b.priority - a.priority);
  }
  
  /**
   * Remove a rule by ID
   */
  removeRule(ruleId: string): boolean {
    const index = this.rules.findIndex(r => r.id === ruleId);
    if (index !== -1) {
      this.rules.splice(index, 1);
      return true;
    }
    return false;
  }
  
  /**
   * Update configuration
   */
  updateConfig(config: Partial<FirewallConfig>): void {
    this.config = { ...this.config, ...config };
    // Rebuild rules that depend on config
    this.rules = this.buildDefaultRules();
  }
  
  /**
   * Clear audit log
   */
  clearAuditLog(): void {
    this.auditLog = [];
  }
  
  /**
   * Export configuration
   */
  exportConfig(): FirewallConfig {
    return { ...this.config };
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// FACTORY & SINGLETON
// ──────────────────────────────────────────────────────────────────────────────

let _defaultFirewall: SemanticFirewall | null = null;

export function getSemanticFirewall(config?: Partial<FirewallConfig>): SemanticFirewall {
  if (!_defaultFirewall) {
    _defaultFirewall = new SemanticFirewall(config);
  } else if (config) {
    _defaultFirewall.updateConfig(config);
  }
  return _defaultFirewall;
}

export function resetSemanticFirewall(): void {
  _defaultFirewall = null;
}

export default SemanticFirewall;