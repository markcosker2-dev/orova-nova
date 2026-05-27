/**
 * Multi-agent team collaboration types.
 * Teams group agents under an orchestrator that coordinates delegation.
 */

export interface TeamConfig {
  /** How the orchestrator delegates tasks to members */
  delegationMode: 'auto' | 'manual';
  /** Custom SOUL template override for the orchestrator */
  soulTemplate?: string;
  /** Whether team members share conversation context */
  sharedContext?: boolean;
}

export interface AgentTeam {
  id: string;
  name: string;
  description: string;
  avatar?: string;
  /** The lead agent that receives user messages and delegates */
  orchestratorId: string;
  /** Member agent IDs (excludes orchestrator) */
  memberIds: string[];
  config: TeamConfig;
  createdAt: string;
  updatedAt: string;
}

export interface TeamWithAgents extends AgentTeam {
  orchestrator: import('./agent').AgentSummary;
  members: import('./agent').AgentSummary[];
}

export interface CreateTeamParams {
  name: string;
  description?: string;
  avatar?: string;
  orchestratorId: string;
  memberIds?: string[];
  config?: Partial<TeamConfig>;
}

export interface UpdateTeamParams {
  name?: string;
  description?: string;
  avatar?: string;
  orchestratorId?: string;
  config?: Partial<TeamConfig>;
}

export interface AcpActivity {
  type: 'spawn' | 'message' | 'complete' | 'error';
  parentAgentId: string;
  childAgentId: string;
  sessionKey: string;
  teamId?: string;
  content?: string;
  timestamp: string;
}
