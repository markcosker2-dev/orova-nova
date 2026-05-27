import type { GatewayManager } from '../../gateway/manager';
import { readOpenClawConfig, removePluginRegistration, writeOpenClawConfig } from '../../utils/channel-config';
import { withConfigLock } from '../../utils/config-mutex';
import { getHermesInstallStatus } from '../../utils/paths';
import { getAllSettings, setSetting } from '../../utils/store';
import { isHermesClawBothMode } from '../mode-registry';
import type { BridgeReasonCode, BridgeStatus, RuntimeSettings } from '../types';
import { getRuntimeFoundationSnapshot } from './runtime-status-service';

export const HERMES_OPENCLAW_BRIDGE_PLUGIN_ID = 'hermesclaw-bridge';
export const LEGACY_HERMES_OPENCLAW_BRIDGE_PLUGIN_ID = 'hermesclaw-hermes-bridge';
const MANAGED_HERMES_OPENCLAW_BRIDGE_PLUGIN_IDS = [
  HERMES_OPENCLAW_BRIDGE_PLUGIN_ID,
  LEGACY_HERMES_OPENCLAW_BRIDGE_PLUGIN_ID,
];

type GatewayManagerLike = Pick<GatewayManager, 'getStatus' | 'checkHealth' | 'reload'>;
type HermesProbeResult = { ok: boolean; error?: string };

function getBridgeReasonCode(params: {
  enabled: boolean;
  hermesInstalled: boolean;
  attached: boolean;
  gatewayRunning: boolean;
  gatewayReady: boolean;
  openclawHealthy: { ok: boolean; error?: string };
  hermesProbe: HermesProbeResult;
}): BridgeReasonCode | undefined {
  if (!params.enabled) {
    return 'bridge_disabled';
  }

  if (!params.hermesInstalled) {
    return 'hermes_not_installed';
  }

  if (!params.attached) {
    return 'bridge_config_missing';
  }

  if (!params.gatewayRunning) {
    return 'openclaw_gateway_stopped';
  }

  if (!params.gatewayReady) {
    return 'openclaw_recognition_pending';
  }

  if (!params.openclawHealthy.ok) {
    return 'openclaw_health_failed';
  }

  if (!params.hermesProbe.ok) {
    return 'hermes_home_unreachable';
  }

  return undefined;
}

async function defaultProbeHermesHome(runtime: RuntimeSettings): Promise<HermesProbeResult> {
  try {
    const installStatus = await getHermesInstallStatus({
      windowsHermesPreferredMode: runtime.windowsHermesPreferredMode,
      windowsHermesNativePath: runtime.windowsHermesNativePath,
      windowsHermesWslDistro: runtime.windowsHermesWslDistro,
      installedKinds: [],
    });

    if (installStatus.installed) {
      return { ok: true };
    }

    return {
      ok: false,
      error: installStatus.error ?? 'Hermes home directory is not reachable',
    };
  } catch {
    return { ok: false, error: 'Hermes home directory is not reachable' };
  }
}

export class HermesOpenClawBridge {
  constructor(
    private readonly gatewayManager: GatewayManagerLike,
    private readonly readSettings: typeof getAllSettings = getAllSettings,
    private readonly writeSetting: typeof setSetting = setSetting,
    private readonly readSnapshot: typeof getRuntimeFoundationSnapshot = getRuntimeFoundationSnapshot,
    private readonly lockConfig: typeof withConfigLock = withConfigLock,
    private readonly readConfig: typeof readOpenClawConfig = readOpenClawConfig,
    private readonly writeConfig: typeof writeOpenClawConfig = writeOpenClawConfig,
    private readonly probeHermesHome: (runtime: RuntimeSettings) => Promise<HermesProbeResult> = defaultProbeHermesHome,
  ) {}

  async getStatus(): Promise<BridgeStatus> {
    const snapshot = await this.readSnapshot(this.gatewayManager as GatewayManager);
    return snapshot.bridge;
  }

  async attach(): Promise<BridgeStatus> {
    await this.lockConfig(async () => {
      const config = await this.readConfig();
      const plugins = config.plugins && typeof config.plugins === 'object' ? config.plugins : {};
      const allow = Array.isArray(plugins.allow) ? [...plugins.allow] : [];
      const entries = plugins.entries && typeof plugins.entries === 'object' ? { ...plugins.entries } : {};

      if (!allow.includes(HERMES_OPENCLAW_BRIDGE_PLUGIN_ID)) {
        allow.push(HERMES_OPENCLAW_BRIDGE_PLUGIN_ID);
      }

      entries[HERMES_OPENCLAW_BRIDGE_PLUGIN_ID] = {
        ...(entries[HERMES_OPENCLAW_BRIDGE_PLUGIN_ID] as Record<string, unknown> | undefined),
        enabled: true,
      };

      config.plugins = {
        ...plugins,
        enabled: true,
        allow,
        entries,
      };

      await this.writeConfig(config);
    });

    await this.reloadOpenClawIfNeeded();

    return this.recheck();
  }

  async detach(): Promise<BridgeStatus> {
    await this.lockConfig(async () => {
      const config = await this.readConfig();
      for (const pluginId of MANAGED_HERMES_OPENCLAW_BRIDGE_PLUGIN_IDS) {
        removePluginRegistration(config, pluginId);
      }
      await this.writeConfig(config);
    });

    await this.reloadOpenClawIfNeeded();

    return this.recheck();
  }

  async recheck(): Promise<BridgeStatus> {
    const settings = await this.readSettings();
    const enabled = isHermesClawBothMode(settings.runtime.mode);
    const config = await this.readConfig();
    const pluginRegistered = MANAGED_HERMES_OPENCLAW_BRIDGE_PLUGIN_IDS.some((pluginId) => {
      const pluginAllowed = Array.isArray(config.plugins?.allow) && config.plugins.allow.includes(pluginId);
      const pluginEntry = config.plugins?.entries?.[pluginId];
      const pluginEnabled = Boolean(
        pluginEntry
        && typeof pluginEntry === 'object'
        && (pluginEntry as { enabled?: unknown }).enabled !== false,
      );
      return pluginAllowed && pluginEnabled;
    });
    const gatewayStatus = this.gatewayManager.getStatus();
    const openclawHealthy = enabled ? await this.gatewayManager.checkHealth().catch(() => ({ ok: false })) : { ok: false };
    const hermesInstalled = settings.runtime.installedKinds.includes('hermes');
    const attached = enabled && hermesInstalled && pluginRegistered;
    const gatewayRunning = gatewayStatus.state === 'running';
    const gatewayReadyForRecognition = gatewayRunning && gatewayStatus.gatewayReady !== false;
    const openclawRecognized = attached && openclawHealthy.ok && gatewayReadyForRecognition;
    const hermesProbe = openclawRecognized
      ? await this.probeHermesHome(settings.runtime).catch(() => ({ ok: false, error: 'Hermes home directory is not reachable' }))
      : { ok: false as const };
    const hermesHealthy = openclawRecognized && hermesProbe.ok;
    const reasonCode = getBridgeReasonCode({
      enabled,
      hermesInstalled,
      attached,
      gatewayRunning,
      gatewayReady: gatewayReadyForRecognition,
      openclawHealthy,
      hermesProbe,
    });
    const lastError = !enabled
      ? undefined
      : !hermesInstalled
        ? 'Hermes runtime is not installed'
        : !pluginRegistered
          ? 'Hermes bridge config is not registered in OpenClaw'
          : attached && !gatewayRunning
            ? 'OpenClaw gateway is not running'
            : attached && gatewayStatus.gatewayReady === false
              ? 'OpenClaw bridge reload/recognition is still pending'
              : !openclawHealthy.ok
                ? openclawHealthy.error ?? 'OpenClaw health check failed'
            : !hermesProbe.ok
              ? hermesProbe.error ?? 'Hermes home directory is not reachable'
              : undefined;
    const lastSyncAt = Date.now();

    const bridgeStatus: BridgeStatus = {
      enabled,
      attached,
      hermesInstalled,
      hermesHealthy,
      openclawRecognized,
      reasonCode,
      lastSyncAt,
      error: lastError,
    };

    await this.persistBridgeState({
      enabled,
      attached,
      hermesInstalled,
      hermesHealthy,
      openclawRecognized,
      reasonCode,
      lastError,
      lastSyncAt,
    });

    return bridgeStatus;
  }

  private async reloadOpenClawIfNeeded(): Promise<void> {
    const settings = await this.readSettings();
    if (!isHermesClawBothMode(settings.runtime.mode)) {
      return;
    }

    const gatewayStatus = this.gatewayManager.getStatus();
    if (gatewayStatus.state === 'stopped') {
      return;
    }

    await this.gatewayManager.reload();
  }

  private async persistBridgeState(status: {
    enabled: boolean;
    attached: boolean;
    hermesInstalled: boolean;
    hermesHealthy: boolean;
    openclawRecognized: boolean;
    reasonCode?: BridgeReasonCode;
    lastError?: string;
    lastSyncAt: number;
  }): Promise<void> {
    const settings = await this.readSettings();

    await this.writeSetting('bridge', {
      ...settings.bridge,
      hermesAsOpenClawAgent: {
        ...settings.bridge.hermesAsOpenClawAgent,
        enabled: status.enabled,
        attached: status.attached,
        hermesInstalled: status.hermesInstalled,
        hermesHealthy: status.hermesHealthy,
        openclawRecognized: status.openclawRecognized,
        reasonCode: status.reasonCode,
        lastSyncAt: status.lastSyncAt,
        lastError: status.lastError,
      },
    });
  }
}
