import type { IncomingMessage, ServerResponse } from 'node:http';
import type { HostApiContext } from '../context';
import { parseJsonBody, sendJson } from '../route-utils';
import * as teamManager from '../../services/team-manager';
import type { CreateTeamParams, UpdateTeamParams } from '../../../src/types/team';

const TEAMS_PREFIX = '/api/teams';

export async function handleTeamRoutes(
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
  ctx: HostApiContext
): Promise<boolean> {
  // POST /api/teams — create team
  if (url.pathname === TEAMS_PREFIX && req.method === 'POST') {
    try {
      const body = await parseJsonBody<CreateTeamParams>(req);
      if (!body.name || !body.orchestratorId) {
        sendJson(res, 400, { success: false, error: 'name and orchestratorId are required' });
        return true;
      }
      const team = teamManager.createTeam(body);
      sendJson(res, 201, { success: true, team });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // GET /api/teams — list all teams
  if (url.pathname === TEAMS_PREFIX && req.method === 'GET') {
    try {
      const teams = teamManager.listTeams();
      sendJson(res, 200, { success: true, teams });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // Routes with teamId
  if (!url.pathname.startsWith(TEAMS_PREFIX + '/')) return false;
  const pathAfterTeams = url.pathname.slice(TEAMS_PREFIX.length + 1);
  const parts = pathAfterTeams.split('/').map(decodeURIComponent);
  const teamId = parts[0];

  if (!teamId) return false;

  // GET /api/teams/:teamId
  if (parts.length === 1 && req.method === 'GET') {
    try {
      const team = teamManager.getTeam(teamId);
      sendJson(res, 200, { success: true, team });
    } catch (error) {
      sendJson(res, 404, { success: false, error: String(error) });
    }
    return true;
  }

  // PUT /api/teams/:teamId
  if (parts.length === 1 && req.method === 'PUT') {
    try {
      const body = await parseJsonBody<UpdateTeamParams>(req);
      const team = teamManager.updateTeam(teamId, body);
      sendJson(res, 200, { success: true, team });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // DELETE /api/teams/:teamId
  if (parts.length === 1 && req.method === 'DELETE') {
    try {
      teamManager.deleteTeam(teamId);
      sendJson(res, 200, { success: true });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // POST /api/teams/:teamId/members — add member
  if (parts.length === 2 && parts[1] === 'members' && req.method === 'POST') {
    try {
      const body = await parseJsonBody<{ agentId: string }>(req);
      if (!body.agentId) {
        sendJson(res, 400, { success: false, error: 'agentId is required' });
        return true;
      }
      const team = teamManager.addMember(teamId, body.agentId);
      sendJson(res, 200, { success: true, team });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // DELETE /api/teams/:teamId/members/:agentId — remove member
  if (parts.length === 3 && parts[1] === 'members' && req.method === 'DELETE') {
    const agentId = parts[2];
    try {
      const team = teamManager.removeMember(teamId, agentId);
      sendJson(res, 200, { success: true, team });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // POST /api/teams/:teamId/chat — send message to team (routed to orchestrator)
  if (parts.length === 2 && parts[1] === 'chat' && req.method === 'POST') {
    try {
      const body = await parseJsonBody<{ message: string }>(req);
      if (!body.message) {
        sendJson(res, 400, { success: false, error: 'message is required' });
        return true;
      }
      const team = teamManager.getTeam(teamId);
      const sessionKey = `agent:${team.orchestratorId}:main`;
      const result = await ctx.gatewayManager.rpc(
        'chat.send',
        { sessionKey, message: body.message, deliver: false },
        30_000,
      );
      sendJson(res, 200, { success: true, result });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  return false;
}
