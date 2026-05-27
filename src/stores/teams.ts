import { create } from 'zustand';
import { hostApiFetch } from '@/lib/host-api';
import type { AgentTeam, AcpActivity, CreateTeamParams, UpdateTeamParams } from '@/types/team';

interface TeamsState {
  teams: AgentTeam[];
  loading: boolean;
  error: string | null;
  acpActivities: AcpActivity[];

  fetchTeams: () => Promise<void>;
  createTeam: (params: CreateTeamParams) => Promise<AgentTeam>;
  updateTeam: (id: string, params: UpdateTeamParams) => Promise<void>;
  deleteTeam: (id: string) => Promise<void>;
  addMember: (teamId: string, agentId: string) => Promise<void>;
  removeMember: (teamId: string, agentId: string) => Promise<void>;
  pushAcpActivity: (activity: AcpActivity) => void;
}

export const useTeamsStore = create<TeamsState>((set) => ({
  teams: [],
  loading: false,
  error: null,
  acpActivities: [],

  fetchTeams: async () => {
    set({ loading: true, error: null });
    try {
      const result = await hostApiFetch<{ success: boolean; teams: AgentTeam[] }>('/api/teams');
      set({ teams: result.teams, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  createTeam: async (params) => {
    try {
      const result = await hostApiFetch<{ success: boolean; team: AgentTeam }>('/api/teams', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      set((state) => ({ teams: [result.team, ...state.teams] }));
      return result.team;
    } catch (error) {
      set({ error: String(error) });
      throw error;
    }
  },

  updateTeam: async (id, params) => {
    try {
      const result = await hostApiFetch<{ success: boolean; team: AgentTeam }>(
        `/api/teams/${encodeURIComponent(id)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        }
      );
      set((state) => ({
        teams: state.teams.map((t) => (t.id === id ? result.team : t)),
      }));
    } catch (error) {
      set({ error: String(error) });
      throw error;
    }
  },

  deleteTeam: async (id) => {
    try {
      await hostApiFetch<{ success: boolean }>(`/api/teams/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
      set((state) => ({
        teams: state.teams.filter((t) => t.id !== id),
      }));
    } catch (error) {
      set({ error: String(error) });
      throw error;
    }
  },

  addMember: async (teamId, agentId) => {
    try {
      const result = await hostApiFetch<{ success: boolean; team: AgentTeam }>(
        `/api/teams/${encodeURIComponent(teamId)}/members`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agentId }),
        }
      );
      set((state) => ({
        teams: state.teams.map((t) => (t.id === teamId ? result.team : t)),
      }));
    } catch (error) {
      set({ error: String(error) });
      throw error;
    }
  },

  removeMember: async (teamId, agentId) => {
    try {
      const result = await hostApiFetch<{ success: boolean; team: AgentTeam }>(
        `/api/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(agentId)}`,
        {
          method: 'DELETE',
        }
      );
      set((state) => ({
        teams: state.teams.map((t) => (t.id === teamId ? result.team : t)),
      }));
    } catch (error) {
      set({ error: String(error) });
      throw error;
    }
  },

  pushAcpActivity: (activity) => {
    set((state) => ({
      acpActivities: [...state.acpActivities, activity],
    }));
  },
}));
