import type { AcpActivity } from '../../src/types/team';
import * as teamManager from './team-manager';

/**
 * ACP Event Bridge
 *
 * Parses gateway 'agent' notifications into typed AcpActivity objects
 * and associates them with teams via session key pattern matching.
 *
 * Session key format: agent:${targetAgentId}:acp:${uuid}
 */

/** Shape of agent notification payload from gateway protocol */
interface AgentNotificationPayload {
  event?: string;
  type?: string;
  parentAgentId?: string;
  childAgentId?: string;
  sourceAgentId?: string;
  targetAgentId?: string;
  sessionKey?: string;
  content?: string;
  message?: string;
  error?: string;
}

const ACP_SESSION_KEY_REGEX = /^agent:([^:]+):acp:([0-9a-f-]+)$/;

/**
 * Parse an agent notification payload into an AcpActivity.
 * Returns null if the notification is not a recognized ACP event.
 */
export function parseAgentNotification(
  payload: AgentNotificationPayload,
): AcpActivity | null {
  const eventType = payload.event ?? payload.type;
  if (!eventType) return null;

  // Map raw event types to AcpActivity types
  let activityType: AcpActivity['type'];
  switch (eventType) {
    case 'spawn':
    case 'acp:spawn':
    case 'agent:spawn':
      activityType = 'spawn';
      break;
    case 'message':
    case 'acp:message':
    case 'agent:message':
      activityType = 'message';
      break;
    case 'complete':
    case 'acp:complete':
    case 'agent:complete':
      activityType = 'complete';
      break;
    case 'error':
    case 'acp:error':
    case 'agent:error':
      activityType = 'error';
      break;
    default:
      return null;
  }

  const parentAgentId = payload.parentAgentId ?? payload.sourceAgentId ?? '';
  const childAgentId = payload.childAgentId ?? payload.targetAgentId ?? '';
  const sessionKey = payload.sessionKey ?? '';
  const content = payload.content ?? payload.message ?? payload.error ?? '';

  if (!parentAgentId && !childAgentId && !sessionKey) {
    return null;
  }

  const activity: AcpActivity = {
    type: activityType,
    parentAgentId,
    childAgentId,
    sessionKey,
    content: content || undefined,
    timestamp: new Date().toISOString(),
  };

  // Try to associate with a team
  activity.teamId = resolveTeamId(parentAgentId, childAgentId, sessionKey);

  return activity;
}

/**
 * Resolve a team ID from ACP activity participants.
 * Checks if either agent is an orchestrator or member of any team.
 */
function resolveTeamId(
  parentAgentId: string,
  childAgentId: string,
  sessionKey: string,
): string | undefined {
  // Extract agent ID from session key if available
  let sessionAgentId: string | undefined;
  const match = ACP_SESSION_KEY_REGEX.exec(sessionKey);
  if (match) {
    sessionAgentId = match[1];
  }

  try {
    const teams = teamManager.listTeams();
    for (const team of teams) {
      const isParentInTeam =
        team.orchestratorId === parentAgentId || team.memberIds.includes(parentAgentId);
      const isChildInTeam =
        team.orchestratorId === childAgentId || team.memberIds.includes(childAgentId);
      const isSessionAgentInTeam =
        sessionAgentId !== undefined &&
        (team.orchestratorId === sessionAgentId || team.memberIds.includes(sessionAgentId));

      if (isParentInTeam || isChildInTeam || isSessionAgentInTeam) {
        return team.id;
      }
    }
  } catch {
    // Teams directory may not exist yet — that's fine
  }

  return undefined;
}
