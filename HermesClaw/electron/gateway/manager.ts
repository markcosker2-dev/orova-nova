export interface GatewayStatus {
  state: string;
  pid?: number;
}

export interface GatewayManager {
  getStatus(): GatewayStatus;
  checkHealth(): Promise<{ ok: boolean; error?: string; uptime?: number }>;
  reload(): Promise<void>;
}