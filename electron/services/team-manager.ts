import { existsSync, readFileSync, writeFileSync, readdirSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { homedir } from 'node:os';
import { getDataDir, ensureDir } from '../utils/paths';
import type { AgentTeam, TeamConfig, CreateTeamParams, UpdateTeamParams } from '../../src/types/team';

const DEFAULT_TEAM_CONFIG: TeamConfig = {
  delegationMode: 'auto',
  sharedContext: true,
};

function getTeamsDir(): string {
  const dir = join(getDataDir(), 'teams');
  ensureDir(dir);
  return dir;
}

function teamFilePath(teamId: string): string {
  return join(getTeamsDir(), `${teamId}.json`);
}

function readTeamFile(teamId: string): AgentTeam | null {
  const filePath = teamFilePath(teamId);
  if (!existsSync(filePath)) return null;
  const raw = readFileSync(filePath, 'utf-8');
  return JSON.parse(raw) as AgentTeam;
}

function writeTeamFile(team: AgentTeam): void {
  const filePath = teamFilePath(team.id);
  writeFileSync(filePath, JSON.stringify(team, null, 2), 'utf-8');
}

export function createTeam(params: CreateTeamParams): AgentTeam {
  const now = new Date().toISOString();
  const team: AgentTeam = {
    id: randomUUID(),
    name: params.name,
    description: params.description ?? '',
    avatar: params.avatar,
    orchestratorId: params.orchestratorId,
    memberIds: params.memberIds ?? [],
    config: { ...DEFAULT_TEAM_CONFIG, ...params.config },
    createdAt: now,
    updatedAt: now,
  };
  writeTeamFile(team);
  return team;
}

export function updateTeam(teamId: string, params: UpdateTeamParams): AgentTeam {
  const team = readTeamFile(teamId);
  if (!team) throw new Error(`Team not found: ${teamId}`);

  if (params.name !== undefined) team.name = params.name;
  if (params.description !== undefined) team.description = params.description;
  if (params.avatar !== undefined) team.avatar = params.avatar;
  if (params.orchestratorId !== undefined) team.orchestratorId = params.orchestratorId;
  if (params.config !== undefined) {
    team.config = { ...team.config, ...params.config };
  }
  team.updatedAt = new Date().toISOString();

  writeTeamFile(team);
  return team;
}

export function deleteTeam(teamId: string): void {
  const filePath = teamFilePath(teamId);
  if (!existsSync(filePath)) throw new Error(`Team not found: ${teamId}`);
  unlinkSync(filePath);
}

export function listTeams(): AgentTeam[] {
  const dir = getTeamsDir();
  const files = readdirSync(dir).filter((f) => f.endsWith('.json'));
  const teams: AgentTeam[] = [];
  for (const file of files) {
    const raw = readFileSync(join(dir, file), 'utf-8');
    teams.push(JSON.parse(raw) as AgentTeam);
  }
  teams.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  return teams;
}

export function getTeam(teamId: string): AgentTeam {
  const team = readTeamFile(teamId);
  if (!team) throw new Error(`Team not found: ${teamId}`);
  return team;
}

export function addMember(teamId: string, agentId: string): AgentTeam {
  const team = readTeamFile(teamId);
  if (!team) throw new Error(`Team not found: ${teamId}`);
  if (team.memberIds.includes(agentId)) return team;
  team.memberIds.push(agentId);
  team.updatedAt = new Date().toISOString();
  writeTeamFile(team);
  return team;
}

export function removeMember(teamId: string, agentId: string): AgentTeam {
  const team = readTeamFile(teamId);
  if (!team) throw new Error(`Team not found: ${teamId}`);
  team.memberIds = team.memberIds.filter((id) => id !== agentId);
  team.updatedAt = new Date().toISOString();
  writeTeamFile(team);
  return team;
}

/**
 * Generate orchestrator SOUL.md content for a team.
 * This SOUL instructs the orchestrator agent on how to delegate to team members.
 */
export function generateOrchestratorSoul(team: AgentTeam, memberNames: string[]): string {
  const membersBlock = memberNames.length > 0
    ? memberNames.map((name, i) => `- ${name} (ID: ${team.memberIds[i]})`).join('\n')
    : '- (no members yet)';

  const delegationRule = team.config.delegationMode === 'auto'
    ? 'Automatically delegate subtasks to the most appropriate team member based on their specialization.'
    : 'Ask the user which team member should handle each subtask before delegating.';

  return `# Team Orchestrator: ${team.name}

## Role
You are the lead agent (orchestrator) of the team "${team.name}".
${team.description ? `\nTeam purpose: ${team.description}\n` : ''}
## Team Members
${membersBlock}

## Delegation Rules
${delegationRule}

## Collaboration Protocol
1. Analyze incoming requests and break them into subtasks
2. Delegate subtasks to appropriate team members using ACP spawn
3. Integrate results from team members into a coherent response
4. Reply to the user with the final consolidated answer

## Important
- Always acknowledge which team member is handling which subtask
- If a member reports an error, try an alternative approach or escalate to the user
- Maintain shared context across delegations when possible
`;
}

/**
 * Write the orchestrator SOUL.md to the agent's directory.
 * Orchestrator agent dir: ~/.openclaw/agents/${orchestratorId}/agent/SOUL.md
 */
export function writeOrchestratorSoul(team: AgentTeam, memberNames: string[]): void {
  const soulContent = generateOrchestratorSoul(team, memberNames);
  const agentDir = join(homedir(), '.openclaw', 'agents', team.orchestratorId, 'agent');
  const soulPath = join(agentDir, 'SOUL.md');
  if (existsSync(agentDir)) {
    writeFileSync(soulPath, soulContent, 'utf-8');
  }
}
