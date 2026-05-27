import type { IncomingMessage, ServerResponse } from 'http';
import { getPort } from '../../utils/config';
import { getSetting } from '../../utils/store';
import { proxyAwareFetch } from '../../utils/proxy-fetch';
import type { HostApiContext } from '../context';
import { parseJsonBody, sendJson } from '../route-utils';

const DEFAULT_OROVA_API_KEY = 'nova_admin_2026';

const AGENT_DEPT_MAP: Record<string, string> = {
  "CEO": "Executive",
  "Lead Hunter": "Research",
  "Sales Director": "Sales",
  "Content Strategist": "Content",
  "Operations": "Operations",
  "Data Intel": "Analytics"
};

const AGENT_TASKS: Record<string, string> = {
  "Nova": "Orchestrating 5 autonomous lane executors",
  "Hawk": "Scouting high-ticket businesses",
  "Closer": "Escalating cold leads to call lane",
  "Quill": "Drafting outreach sequences",
  "Sentinel": "Monitoring swarm health",
  "Oracle": "Analyzing pipeline performance"
};

const AGENT_COLORS: Record<string, string> = {
  "Nova": "#4f46e5",
  "Hawk": "#059669",
  "Closer": "#dc2626",
  "Quill": "#0ea5e9",
  "Sentinel": "#7c3aed",
  "Oracle": "#f59e0b"
};

interface Agent {
  name: string;
  role: string;
  status: string;
}

interface AugmentedAgent extends Agent {
  id: string;
  model: string;
  dept: string;
  task: string;
  color: string;
  initial: string;
  skills: string[];
}

export async function handleOrovaRoutes(
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
  _ctx: HostApiContext,
): Promise<boolean> {
  const isHermesClawRoute = url.pathname.startsWith('/api/hermesclaw/');
  const isLeadsRoute = url.pathname.startsWith('/api/leads/');

  if (!isHermesClawRoute && !isLeadsRoute) {
    return false;
  }

  try {
    const backendUrl = await getSetting('orovaBackendUrl') || `http://127.0.0.1:${getPort('OROVA_BACKEND')}`;
    const apiKey = await getSetting('orovaApiKey') || DEFAULT_OROVA_API_KEY;

    const targetPathname = isLeadsRoute ? url.pathname : translatePath(url.pathname);
    const targetUrl = `${backendUrl}${targetPathname}${url.search}`;

    const headers: Record<string, string> = {
      'X-API-Key': apiKey,
    };

    const init: RequestInit = {
      method: req.method,
      headers,
    };

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      const body = await parseJsonBody<Record<string, unknown>>(req);
      if (Object.keys(body).length > 0) {
        init.body = JSON.stringify(body);
        init.headers = {
          ...headers,
          'Content-Type': 'application/json',
        };
      }
    }

    const response = await proxyAwareFetch(targetUrl, init);
    const data = await response.json();

    const transformedData = transformResponse(url.pathname, data);
    sendJson(res, response.status, transformedData);
    return true;
  } catch (error) {
    sendJson(res, 500, { success: false, error: String(error) });
    return true;
  }
}

function getAgentSkills(role: string): string[] {
  const skillsMap: Record<string, string[]> = {
    "CEO": ["Strategy", "Leadership", "Decision Making"],
    "Lead Hunter": ["Lead Generation", "Qualification", "Research"],
    "Sales Director": ["Closing", "Negotiation", "Pipeline Management"],
    "Content Strategist": ["Copywriting", "Sequence Design", "A/B Testing"],
    "Operations": ["Process Optimization", "Resource Allocation", "Quality Control"],
    "Data Intel": ["Analytics", "Reporting", "Insights"]
  };
  return skillsMap[role] || ["General"];
}

function translatePath(pathname: string): string {
  if (pathname.startsWith('/api/hermesclaw/agents')) {
    return '/api/agents';
  }
  if (pathname.startsWith('/api/hermesclaw/health')) {
    return '/api/health';
  }
  if (pathname.startsWith('/api/hermesclaw/metrics')) {
    return '/api/metrics';
  }
  if (pathname.startsWith('/api/hermesclaw/tasks')) {
    return '/api/tasks';
  }
  if (pathname.startsWith('/api/hermesclaw/actions/')) {
    const action = pathname.replace('/api/hermesclaw/actions/', '');
    return `/api/actions/${action}`;
  }
  if (pathname.startsWith('/api/hermesclaw/skills')) {
    return '/api/skills';
  }
  if (pathname.startsWith('/api/hermesclaw/content')) {
    return '/api/content';
  }
  if (pathname.startsWith('/api/hermesclaw/notifications')) {
    return '/api/notifications';
  }
  if (pathname.startsWith('/api/hermesclaw/performance')) {
    return '/api/performance';
  }
  if (pathname.startsWith('/api/hermesclaw/leads')) {
    return pathname.replace('/api/hermesclaw', '/api');
  }
  return pathname;
}

function transformResponse(pathname: string, data: unknown): unknown {
  if (pathname.startsWith('/api/hermesclaw/health')) {
    const response = data as Record<string, unknown>;
    const status = response.status;
    const normalizedStatus = status === 'Operational' ? 'ok' :
      status === 'Degraded' ? 'warn' :
      status === 'Critical' ? 'error' : 'ok';
    const { status: _status, ...healthRest } = response;
    return {
      status: normalizedStatus,
      health: healthRest,
    };
  }

  if (pathname.startsWith('/api/hermesclaw/metrics')) {
    const response = data as Record<string, unknown>;
    return {
      status: response.status,
      metrics: response.metrics ?? {
        leads_found: response.leads_found,
        emails_sent: response.emails_sent,
        replies_received: response.replies_received,
        meetings_booked: response.meetings_booked,
        calls_made: response.calls_made,
        proposals_sent: response.proposals_sent
      },
    };
  }

  if (pathname.startsWith('/api/hermesclaw/tasks')) {
    const response = data as Record<string, unknown>;
    return {
      ...response,
      lanes: {},
    };
  }

  if (pathname.startsWith('/api/hermesclaw/agents')) {
    const response = data as Record<string, unknown> & { agents?: Record<string, Agent> };
    const agentsData = (response.agents ?? response) as Record<string, Agent>;
    const agents: AugmentedAgent[] = Object.entries(agentsData).map(([key, agent]) => {
      return {
        ...agent,
        name: agent.name ?? key,
        role: agent.role ?? key,
        status: agent.status ?? 'unknown',
        id: key.toLowerCase(),
        model: 'gpt-4',
        dept: AGENT_DEPT_MAP[agent.role] ?? agent.role ?? key,
        task: AGENT_TASKS[agent.name] ?? "Available for assignment",
        color: AGENT_COLORS[agent.name] ?? "#6b7280",
        initial: agent.name.charAt(0).toUpperCase(),
        skills: typeof agent.role === 'string' ? getAgentSkills(agent.role) : [],
      };
    });
    return {
      status: 'ok',
      agents,
    };
  }

  if (pathname.startsWith('/api/hermesclaw/skills')) {
    const response = data as Record<string, unknown>;
    return {
      status: response.status,
      skills: response.skills,
    };
  }

  if (pathname.startsWith('/api/hermesclaw/content')) {
    const response = data as Record<string, unknown>;
    return {
      status: response.status,
      content: response.content,
    };
  }

  if (pathname.startsWith('/api/hermesclaw/notifications')) {
    const response = data as Record<string, unknown>;
    return {
      status: response.status,
      notifications: response.notifications,
    };
  }

  if (pathname.startsWith('/api/hermesclaw/performance')) {
    const response = data as Record<string, unknown>;
    return {
      status: response.status,
      performance: response.performance,
    };
  }

  return data;
}