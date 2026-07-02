/**
 * Semantic Firewall Integration — HermesClaw
 * 
 * Provides integration points between the Semantic Firewall and the
 * HermesClaw agent runtime (Gateway Manager, OpenClaw Bridge, etc.)
 */

import { SemanticFirewall, getSemanticFirewall, setFirewallLogger, ToolCallContext, FirewallDecision, FirewallConfig } from './semantic-firewall';
import { GatewayManager } from '../../gateway/manager';
import { logger } from '../../utils/logger';

// Route firewall diagnostics through the main-process file logger.
setFirewallLogger(logger);

// ──────────────────────────────────────────────────────────────────────────────
// TYPES
// ──────────────────────────────────────────────────────────────────────────────

export interface FirewallIntegrationConfig {
  /** Firewall configuration */
  firewallConfig?: Partial<FirewallConfig>;
  /** Enable firewall for all RPC calls */
  enableForRpc: boolean;
  /** Enable firewall for tool calls from agents */
  enableForAgentTools: boolean;
  /** Custom tool name mapping (agent tool name -> firewall tool name) */
  toolNameMapping?: Record<string, string>;
  /** Callback when human approval is required */
  onHumanApprovalRequired?: (context: ToolCallContext, reason: string) => Promise<boolean>;
  /** Callback when review is required */
  onReviewRequired?: (context: ToolCallContext, reason: string) => Promise<FirewallDecision>;
}

export interface AgentSession {
  id: string;
  goal: string;
  parentTaskId?: string;
  agentDepth: number;
  isSubAgent: boolean;
  grantedCredentials?: string[];
  maxToolCalls: number;
  maxCost?: number;
  taskTimeoutMs?: number;
  startTime: number;
  toolCallHistory: Array<{
    toolName: string;
    parameters: Record<string, unknown>;
    timestamp: number;
    decision: FirewallDecision;
    reason?: string;
  }>;
}

// ──────────────────────────────────────────────────────────────────────────────
// FIREWALL INTEGRATION CLASS
// ──────────────────────────────────────────────────────────────────────────────

export class FirewallIntegration {
  private firewall: SemanticFirewall;
  private config: FirewallIntegrationConfig;
  private sessions: Map<string, AgentSession> = new Map();
  private gatewayManager: GatewayManager | null = null;
  
  constructor(config: FirewallIntegrationConfig = { enableForRpc: true, enableForAgentTools: true }) {
    this.config = config;
    this.firewall = getSemanticFirewall(config.firewallConfig);
    
    // Set up event listeners
    this.setupEventListeners();
  }
  
  private setupEventListeners(): void {
    this.firewall.on('tool-call-evaluated', (entry) => {
      logger.debug(`[FirewallIntegration] Tool evaluated: ${entry.toolName} -> ${entry.decision}`);
    });
    
    this.firewall.on('high-impact-tool-blocked', (entry) => {
      logger.warn(`[FirewallIntegration] High-impact tool blocked: ${entry.toolName} (session: ${entry.sessionId})`);
    });
    
    this.firewall.on('sub-agent-spawned', (entry) => {
      logger.info(`[FirewallIntegration] Sub-agent spawned: ${entry.toolName} (session: ${entry.sessionId})`);
    });
    
    this.firewall.on('budget-exceeded', (entry) => {
      logger.warn(`[FirewallIntegration] Budget exceeded for session: ${entry.sessionId}`);
    });
    
    this.firewall.on('injection-attempt', (entry) => {
      logger.error(`[FirewallIntegration] INJECTION ATTEMPT DETECTED: ${entry.toolName} (session: ${entry.sessionId})`);
    });
  }
  
  /**
   * Set the gateway manager for RPC interception
   */
  setGatewayManager(gatewayManager: GatewayManager): void {
    this.gatewayManager = gatewayManager;
    if (this.config.enableForRpc) {
      this.installRpcInterceptor();
    }
  }
  
  /**
   * Install RPC interceptor on the gateway manager
   */
  private installRpcInterceptor(): void {
    if (!this.gatewayManager) return;

    // The gateway's rpc method is not monkey-patched; agent-originated calls
    // must go through firewallRpc() so evaluation happens per-session.
    logger.info('[FirewallIntegration] RPC interceptor installed - use firewallRpc() for protected calls');
  }
  
  /**
   * Create a new agent session
   */
  createSession(params: {
    sessionId: string;
    goal: string;
    parentTaskId?: string;
    agentDepth?: number;
    isSubAgent?: boolean;
    grantedCredentials?: string[];
    maxToolCalls?: number;
    maxCost?: number;
    taskTimeoutMs?: number;
  }): AgentSession {
    const session: AgentSession = {
      id: params.sessionId,
      goal: params.goal,
      parentTaskId: params.parentTaskId,
      agentDepth: params.agentDepth ?? 0,
      isSubAgent: params.isSubAgent ?? false,
      grantedCredentials: params.grantedCredentials,
      maxToolCalls: params.maxToolCalls ?? this.firewall.exportConfig().maxToolCallsPerTask,
      maxCost: params.maxCost,
      taskTimeoutMs: params.taskTimeoutMs ?? this.firewall.exportConfig().defaultTaskTimeoutMs,
      startTime: Date.now(),
      toolCallHistory: [],
    };
    
    this.sessions.set(params.sessionId, session);
    logger.info(`[FirewallIntegration] Created session: ${params.sessionId} (depth: ${session.agentDepth})`);
    return session;
  }
  
  /**
   * Get an existing session
   */
  getSession(sessionId: string): AgentSession | undefined {
    return this.sessions.get(sessionId);
  }
  
  /**
   * Delete a session
   */
  deleteSession(sessionId: string): boolean {
    return this.sessions.delete(sessionId);
  }
  
  /**
   * Evaluate a tool call through the firewall
   */
  async evaluateToolCall(params: {
    sessionId: string;
    toolName: string;
    parameters: Record<string, unknown>;
  }): Promise<{
    decision: FirewallDecision;
    reason: string;
    sanitizedParameters?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    shouldExecute: boolean;
  }> {
    const session = this.sessions.get(params.sessionId);
    if (!session) {
      logger.warn(`[FirewallIntegration] Session not found: ${params.sessionId}`);
      return {
        decision: 'deny',
        reason: 'Session not found',
        shouldExecute: false,
      };
    }
    
    // Map tool name if mapping exists
    const firewallToolName = this.config.toolNameMapping?.[params.toolName] ?? params.toolName;
    
    // Build context
    const context: ToolCallContext = {
      currentGoal: session.goal,
      toolName: firewallToolName,
      parameters: params.parameters,
      sessionId: session.id,
      parentTaskId: session.parentTaskId,
      agentDepth: session.agentDepth,
      toolCallHistory: session.toolCallHistory,
      isSubAgent: session.isSubAgent,
      grantedCredentials: session.grantedCredentials,
      maxToolCalls: session.maxToolCalls,
      maxCost: session.maxCost,
      currentCost: 0, // Would be tracked by the application
      taskTimeoutMs: session.taskTimeoutMs,
      taskStartTime: session.startTime,
    };
    
    // Evaluate through firewall
    const result = await this.firewall.evaluate(context);
    
    // Record in session history
    session.toolCallHistory.push({
      toolName: firewallToolName,
      parameters: params.parameters,
      timestamp: Date.now(),
      decision: result.decision,
      reason: result.reason,
    });
    
    // Handle decisions requiring human interaction
    let shouldExecute = false;
    let finalDecision = result.decision;
    
    switch (result.decision) {
      case 'allow':
        shouldExecute = true;
        break;
        
      case 'require_review':
        if (this.config.onReviewRequired) {
          finalDecision = await this.config.onReviewRequired(context, result.reason);
          shouldExecute = finalDecision === 'allow';
        } else {
          // Default: deny if no review handler
          finalDecision = 'deny';
          shouldExecute = false;
        }
        break;
        
      case 'require_human_approval':
        if (this.config.onHumanApprovalRequired) {
          const approved = await this.config.onHumanApprovalRequired(context, result.reason);
          shouldExecute = approved;
          finalDecision = approved ? 'allow' : 'deny';
        } else {
          // Default: deny if no approval handler
          finalDecision = 'deny';
          shouldExecute = false;
        }
        break;
        
      case 'deny':
      default:
        shouldExecute = false;
        break;
    }
    
    // Update the last history entry with final decision
    const lastEntry = session.toolCallHistory[session.toolCallHistory.length - 1];
    if (lastEntry) {
      lastEntry.decision = finalDecision;
      lastEntry.reason = result.reason + (finalDecision !== result.decision ? ` (overridden to ${finalDecision})` : '');
    }
    
    return {
      decision: finalDecision,
      reason: result.reason,
      sanitizedParameters: result.sanitizedParameters,
      metadata: result.metadata,
      shouldExecute,
    };
  }
  
  /**
   * Protected RPC call that goes through the firewall
   */
  async firewallRpc<T>(params: {
    sessionId: string;
    method: string;
    rpcParams?: unknown;
    timeoutMs?: number;
  }): Promise<T> {
    const session = this.sessions.get(params.sessionId);
    if (!session) {
      throw new Error(`Session not found: ${params.sessionId}`);
    }
    
    if (!this.gatewayManager) {
      throw new Error('Gateway manager not set');
    }
    
    // Evaluate through firewall
    const evalResult = await this.evaluateToolCall({
      sessionId: params.sessionId,
      toolName: `rpc:${params.method}`,
      parameters: params.rpcParams as Record<string, unknown> || {},
    });
    
    if (!evalResult.shouldExecute) {
      throw new Error(`Firewall blocked RPC call: ${evalResult.reason}`);
    }
    
    // Use sanitized parameters if available
    const rpcParams = evalResult.sanitizedParameters ?? params.rpcParams;
    
    // Execute the actual RPC call
    return this.gatewayManager.rpc<T>(params.method, rpcParams, params.timeoutMs);
  }
  
  /**
   * Spawn a sub-agent with limited permissions
   */
  async spawnSubAgent(params: {
    parentSessionId: string;
    subSessionId: string;
    goal: string;
    allowedTools: string[];
    grantedCredentials: string[];
    maxToolCalls: number;
    maxCost?: number;
    taskTimeoutMs?: number;
  }): Promise<AgentSession> {
    const parentSession = this.sessions.get(params.parentSessionId);
    if (!parentSession) {
      throw new Error(`Parent session not found: ${params.parentSessionId}`);
    }
    
    // Check depth limit
    const newDepth = parentSession.agentDepth + 1;
    const maxDepth = this.firewall.exportConfig().maxAgentDepth;
    if (newDepth > maxDepth) {
      throw new Error(`Sub-agent depth limit exceeded: ${newDepth} > ${maxDepth}`);
    }
    
    // Evaluate the delegation through the firewall BEFORE creating the
    // sub-session, so a denied delegation never leaves an orphaned session.
    const delegation = await this.evaluateToolCall({
      sessionId: params.parentSessionId,
      toolName: 'delegate_task',
      parameters: {
        task: params.goal,
        requiredSkills: [], // Would be populated by the application
        allowedTools: params.allowedTools,
        maxToolCalls: params.maxToolCalls,
        credentials: params.grantedCredentials,
      },
    });

    if (!delegation.shouldExecute) {
      throw new Error(`Firewall blocked sub-agent delegation: ${delegation.reason}`);
    }

    // Create sub-agent session
    return this.createSession({
      sessionId: params.subSessionId,
      goal: params.goal,
      parentTaskId: params.parentSessionId,
      agentDepth: newDepth,
      isSubAgent: true,
      grantedCredentials: params.grantedCredentials,
      maxToolCalls: Math.min(params.maxToolCalls, parentSession.maxToolCalls),
      maxCost: params.maxCost,
      taskTimeoutMs: params.taskTimeoutMs,
    });
  }
  
  /**
   * Get firewall statistics
   */
  getStats() {
    return this.firewall.getStats();
  }
  
  /**
   * Get audit log for a session
   */
  getSessionAuditLog(sessionId: string) {
    return this.firewall.getAuditLog({ sessionId });
  }
  
  /**
   * Update firewall configuration
   */
  updateConfig(config: Partial<FirewallConfig>): void {
    this.firewall.updateConfig(config);
  }
  
  /**
   * Get the underlying firewall instance
   */
  getFirewall(): SemanticFirewall {
    return this.firewall;
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// FACTORY & SINGLETON
// ──────────────────────────────────────────────────────────────────────────────

let _defaultIntegration: FirewallIntegration | null = null;

export function getFirewallIntegration(config?: FirewallIntegrationConfig): FirewallIntegration {
  if (!_defaultIntegration) {
    _defaultIntegration = new FirewallIntegration(config);
  }
  return _defaultIntegration;
}

export function resetFirewallIntegration(): void {
  _defaultIntegration = null;
}

export default FirewallIntegration;