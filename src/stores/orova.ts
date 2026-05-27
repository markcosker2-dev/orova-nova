import { create } from 'zustand';
import { hostApiFetch } from '@/lib/host-api';

export interface OrovaAgent {
  id: string;
  name: string;
  role: string;
  status: string;
  model: string;
  skills: string[];
  dept: string;
  task: string;
  initial: string;
  color: string;
}

export interface OrovaLead {
  id: number;
  business: string;
  owner: string;
  url: string;
  website: string;
  email: string;
  phone: string;
  vertical: string;
  status: string;
  notes: string;
  icebreaker: string;
  score: number;
  client_id: number;
  created_at: string;
}

export interface OrovaMetrics {
  leads_found: number;
  emails_sent: number;
  replies_received: number;
  meetings_booked: number;
  calls_made: number;
  proposals_sent: number;
}

export interface OrovaLane {
  name: string;
  status: string;
  interval: string;
  last_run: string;
}

export interface OrovaSkill {
  id: string;
  name: string;
  description: string;
}

export interface OrovaTask {
  id: string;
  title: string;
  description: string;
  assignee: string;
  status: string;
  result?: string;
}

export interface OrovaHealth {
  status: string;
  timestamp: string;
  queue_depth: number;
  memory?: Record<string, unknown>;
  hardening_health?: Record<string, unknown>;
}

export interface OrovaActionResponse {
  message?: string;
}

export const useOrovaStore = create<{
  agents: OrovaAgent[];
  leads: OrovaLead[];
  metrics: OrovaMetrics | null;
  lanes: Record<string, OrovaLane>;
  tasks: OrovaTask[];
  skills: OrovaSkill[];
  health: OrovaHealth | null;
  loading: boolean;
  error: string | null;

  fetchAgents: () => Promise<void>;
  fetchLeads: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
  fetchTasksAndLanes: () => Promise<void>;
  fetchSkills: () => Promise<void>;
  fetchHealth: () => Promise<void>;

  approveLead: (leadId: number) => Promise<void>;
  clearLeads: () => Promise<void>;

  triggerAction: (action: 'hunt-leads' | 'send-emails' | 'generate-report') => Promise<OrovaActionResponse>;
}>((set, get) => ({
  agents: [],
  leads: [],
  metrics: null,
  lanes: {},
  tasks: [],
  skills: [],
  health: null,
  loading: false,
  error: null,

  fetchAgents: async () => {
    try {
      const res = await hostApiFetch<{ status: string; agents: OrovaAgent[] }>('/api/hermesclaw/agents');
      if (res.status === 'ok') {
        set({ agents: res.agents });
      }
    } catch (_e) {
      console.error('Failed to fetch OROVA agents:', _e);
    }
  },

  fetchLeads: async () => {
    try {
      const res = await hostApiFetch<{ status: string; leads: OrovaLead[] }>('/api/hermesclaw/leads');
      if (res.status === 'ok') {
        set({ leads: res.leads });
      }
    } catch (_e) {
      console.error('Failed to fetch OROVA leads:', _e);
    }
  },

  fetchMetrics: async () => {
    try {
      const res = await hostApiFetch<{ status: string; metrics: OrovaMetrics }>('/api/hermesclaw/metrics');
      if (res.status === 'ok') {
        set({
          metrics: {
            leads_found: res.metrics.leads_found,
            emails_sent: res.metrics.emails_sent,
            replies_received: res.metrics.replies_received,
            meetings_booked: res.metrics.meetings_booked,
            calls_made: res.metrics.calls_made,
            proposals_sent: res.metrics.proposals_sent
          }
        });
      }
    } catch (_e) {
      console.error('Failed to fetch OROVA metrics:', _e);
    }
  },

  fetchTasksAndLanes: async () => {
    try {
      const res = await hostApiFetch<{ status: string; tasks: OrovaTask[]; lanes: Record<string, OrovaLane> }>('/api/hermesclaw/tasks');
      if (res.status === 'ok') {
        set({ tasks: res.tasks, lanes: res.lanes });
      }
    } catch (_e) {
      console.error('Failed to fetch OROVA tasks:', _e);
    }
  },

  fetchSkills: async () => {
    try {
      const res = await hostApiFetch<{ status: string; skills: OrovaSkill[] }>('/api/hermesclaw/skills');
      if (res.status === 'ok') {
        set({ skills: res.skills });
      }
    } catch (_e) {
      console.error('Failed to fetch OROVA skills:', _e);
    }
  },

  fetchHealth: async () => {
    try {
      const res = await hostApiFetch<{ status: string; health: OrovaHealth }>('/api/hermesclaw/health');
      if (res.status === 'ok') {
        set({ health: res.health });
      }
    } catch (_e) {
      console.error('Failed to fetch OROVA health:', _e);
    }
  },

  approveLead: async (leadId: number) => {
    try {
      set({ loading: true, error: null });
      await hostApiFetch(`/api/leads/${leadId}/approve`, {
        method: 'POST'
      });
      await get().fetchLeads();
      set({ loading: false });
    } catch (_e) {
      set({ loading: false, error: String(_e) });
      throw _e;
    }
  },

  clearLeads: async () => {
    try {
      set({ loading: true, error: null });
      await hostApiFetch('/api/leads/clear', {
        method: 'POST'
      });
      set({ leads: [], loading: false });
    } catch (_e) {
      set({ loading: false, error: String(_e) });
      throw _e;
    }
  },

  triggerAction: async (action: 'hunt-leads' | 'send-emails' | 'generate-report') => {
    try {
      set({ loading: true, error: null });
      const res = await hostApiFetch<OrovaActionResponse>(`/api/hermesclaw/actions/${action}`, {
        method: 'POST'
      });
      set({ loading: false });
      return res;
    } catch (_e) {
      set({ loading: false, error: String(_e) });
      throw _e;
    }
  }
}));