import { getHermesInstallStatus, getHermesEndpoint } from '../../utils/paths';
import type { HermesInstallStatus } from '../../utils/paths';
import type { BridgeStatus, InstallStatus, RuntimeSettings, RuntimeStatus } from '../types';

interface BuildRuntimeStatusOptions {
  checkedAt?: number;
  standaloneHealth?: { ok: boolean; error?: string; uptime?: number };
}

type HermesInstallStatusResolver = (runtime: RuntimeSettings) => HermesInstallStatus;

type HermesManagerLike = {
  checkHealth: () => Promise<{ ok: boolean; error?: string; uptime?: number }>;
  debouncedReload: (delayMs?: number) => void;
  debouncedRestart: (delayMs?: number) => void;
  forceTerminateOwnedProcessForQuit: () => Promise<boolean>;
  reload: () => Promise<void>;
  restart: () => Promise<void>;
  rpc: <T>(method: string, params?: unknown, timeoutMs?: number) => Promise<T>;
  start: () => Promise<void>;
  stop: () => Promise<void>;
};

const defaultHermesManager: HermesManagerLike = {
  checkHealth: async () => ({ ok: false, error: 'Hermes standalone lifecycle is not configured' }),
  debouncedReload: () => {},
  debouncedRestart: () => {},
  forceTerminateOwnedProcessForQuit: async () => false,
  reload: async () => {},
  restart: async () => {},
  rpc: async () => {
    throw new Error('Hermes standalone RPC is not configured');
  },
  start: async () => {},
  stop: async () => {},
};

function defaultResolveHermesInstallStatus(runtime: RuntimeSettings): HermesInstallStatus {
  return getHermesInstallStatus({
    windowsHermesPreferredMode: runtime.windowsHermesPreferredMode,
    windowsHermesNativePath: runtime.windowsHermesNativePath,
    windowsHermesWslDistro: runtime.windowsHermesWslDistro,
    installedKinds: runtime.installedKinds,
  });
}

export class HermesStandaloneAdapter {
  readonly kind = 'hermes';

  constructor(
    private readonly resolveInstallStatus: HermesInstallStatusResolver = defaultResolveHermesInstallStatus,
    private readonly hermesManager: HermesManagerLike = defaultHermesManager,
  ) {}

  getInstallStatus(runtime: RuntimeSettings): InstallStatus {
    return this.resolveInstallStatus(runtime);
  }

  start(): Promise<void> {
    return this.hermesManager.start();
  }

  stop(): Promise<void> {
    return this.hermesManager.stop();
  }

  restart(): Promise<void> {
    return this.hermesManager.restart();
  }

  reload(): Promise<void> {
    return this.hermesManager.reload();
  }

  debouncedRestart(delayMs?: number): void {
    this.hermesManager.debouncedRestart(delayMs);
  }

  debouncedReload(delayMs?: number): void {
    this.hermesManager.debouncedReload(delayMs);
  }

  checkHealth(): Promise<{ ok: boolean; error?: string; uptime?: number }> {
    return this.hermesManager.checkHealth();
  }

  rpc<T>(method: string, params?: unknown, timeoutMs?: number): Promise<T> {
    return this.hermesManager.rpc<T>(method, params, timeoutMs);
  }

  forceTerminateOwnedProcessForQuit(): Promise<boolean> {
    return this.hermesManager.forceTerminateOwnedProcessForQuit();
  }

  buildRuntimeStatus(
    runtime: RuntimeSettings,
    bridge: BridgeStatus,
    options: BuildRuntimeStatusOptions = {},
  ): RuntimeStatus {
    const installStatus = this.getInstallStatus(runtime);
    const installed = installStatus.installed;
    const standaloneMode = runtime.mode === 'hermes';

    if (standaloneMode) {
      const standaloneHealth = options.standaloneHealth;
      const standaloneError = !installed
        ? installStatus.error ?? 'Hermes standalone runtime is not installed'
        : standaloneHealth && !standaloneHealth.ok
          ? standaloneHealth.error ?? installStatus.error ?? 'Hermes standalone runtime is unhealthy'
          : installStatus.error;
      const standaloneRunning = installed && (standaloneHealth ? standaloneHealth.ok : true);
      const standaloneHealthy = installed && (standaloneHealth ? standaloneHealth.ok : !standaloneError);

      return {
        kind: this.kind,
        installed,
        running: standaloneRunning,
        healthy: standaloneHealthy,
        version: installStatus.version,
        endpoint: installStatus.endpoint ?? installStatus.installPath ?? getHermesEndpoint(),
        lastCheckedAt: options.checkedAt,
        error: standaloneError,
      };
    }

    return {
      kind: this.kind,
      installed,
      running: bridge.attached,
      healthy: bridge.enabled && bridge.hermesInstalled && bridge.hermesHealthy,
      version: installStatus.version,
      endpoint: installStatus.installPath,
      lastCheckedAt: options.checkedAt,
      error: bridge.error,
    };
  }
}
