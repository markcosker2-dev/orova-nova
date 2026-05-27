import type {
  GatewayDiagnosticsSnapshot,
  GatewayManager,
  GatewayStatus,
} from '../../gateway/manager';
import { getOpenClawRuntimeStatus } from '../../utils/paths';
import type { InstallStatus, RuntimeStatus } from '../types';

type GatewayManagerLike = Pick<GatewayManager,
  | 'checkHealth'
  | 'debouncedReload'
  | 'debouncedRestart'
  | 'forceTerminateOwnedProcessForQuit'
  | 'getDiagnostics'
  | 'getStatus'
  | 'isConnected'
  | 'reload'
  | 'restart'
  | 'rpc'
  | 'start'
  | 'stop'
>;

interface BuildRuntimeStatusOptions {
  installed?: boolean;
  checkedAt?: number;
}

export class OpenClawHostAdapter {
  readonly kind = 'openclaw';

  constructor(
    private readonly gatewayManager: GatewayManagerLike,
    private readonly readInstallStatus: typeof getOpenClawRuntimeStatus = getOpenClawRuntimeStatus,
  ) {}

  getGatewayStatus(): GatewayStatus {
    return this.gatewayManager.getStatus();
  }

  getDiagnostics(): GatewayDiagnosticsSnapshot {
    return this.gatewayManager.getDiagnostics();
  }

  isConnected(): boolean {
    return this.gatewayManager.isConnected();
  }

  getInstallStatus(): InstallStatus {
    const status = this.readInstallStatus();
    return {
      installed: status.packageExists,
      version: status.version,
      installPath: status.dir,
      installMode: 'native',
    };
  }

  buildRuntimeStatus(options: BuildRuntimeStatusOptions = {}): RuntimeStatus {
    const gatewayStatus = this.getGatewayStatus();
    const installed = options.installed ?? this.getInstallStatus().installed;
    const running = gatewayStatus.state === 'running';
    const version = gatewayStatus.version
      ?? (installed ? this.getInstallStatus().version : undefined);

    return {
      kind: this.kind,
      installed,
      running,
      healthy: running && gatewayStatus.gatewayReady !== false,
      version,
      endpoint: installed ? `http://127.0.0.1:${gatewayStatus.port}` : undefined,
      lastCheckedAt: options.checkedAt,
      error: gatewayStatus.error,
    };
  }

  start(): Promise<void> {
    return this.gatewayManager.start();
  }

  stop(): Promise<void> {
    return this.gatewayManager.stop();
  }

  restart(): Promise<void> {
    return this.gatewayManager.restart();
  }

  reload(): Promise<void> {
    return this.gatewayManager.reload();
  }

  debouncedRestart(delayMs?: number): void {
    this.gatewayManager.debouncedRestart(delayMs);
  }

  debouncedReload(delayMs?: number): void {
    this.gatewayManager.debouncedReload(delayMs);
  }

  checkHealth(): Promise<{ ok: boolean; error?: string; uptime?: number }> {
    return this.gatewayManager.checkHealth();
  }

  rpc<T>(method: string, params?: unknown, timeoutMs?: number): Promise<T> {
    return this.gatewayManager.rpc<T>(method, params, timeoutMs);
  }

  forceTerminateOwnedProcessForQuit(): Promise<boolean> {
    return this.gatewayManager.forceTerminateOwnedProcessForQuit();
  }
}
