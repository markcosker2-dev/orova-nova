export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  color?: string;
  emoji?: string;
  vibe?: string;
  category: string;
  soulContent: string;
}

export interface AgentTemplateCategory {
  id: string;
  label: string;
  count: number;
}
