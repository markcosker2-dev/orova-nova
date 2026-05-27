import type { GatewayManager } from '../../gateway/manager';
import { getAllSettings } from '../../utils/store';
import { HermesStandaloneAdapter } from '../adapters/hermes-standalone-adapter';
import { OpenClawHostAdapter } from '../adapters/openclaw-host-adapter';
import { getHermesStandaloneManager } from './hermes-standalone-manager';
import { HermesOpenClawBridge } from './hermes-openclaw-bridge-service';
import {
  installChoiceFromMode,
  isHermesClawBothMode,
  normalizeInstalledKinds,
  runtimeModeFromInstallChoice,
} from '../mode-registry';
import type { BridgeStatus, RuntimeSettings, RuntimeStatus } from '../types';

export interface RuntimeFoundationSnapshot {
  runtime: RuntimeSettings;
  bridge: BridgeStatus;
  runtimes: RuntimeStatus[];
}

function buildPersistedBridgeStatus(runtime: RuntimeSettings, persistedBridge: Awaited<ReturnType<typeof getAllSettings>>['bridge'] extends infer T
  ? T extends { hermesAsOpenClawAgent?: infer B }
    ? B
    : never
  : never): BridgeStatus {
  const bridgeEnabled = isHermesClawBothMode(runtime.mode);
  const bridgeAttached = bridgeEnabled ? (persistedBridge?.attached ?? false) : false;

  return {
    enabled: bridgeEnabled,
    attached: bridgeAttached,
    hermesInstalled: persistedBridge?.hermesInstalled ?? runtime.installedKinds.includes('hermes'),
    hermesHealthy: bridgeEnabled ? (persistedBridge?.hermesHealthy ?? false) : false,
    openclawRecognized: bridgeEnabled ? (persistedBridge?.openclawRecognized ?? false) : false,
    reasonCode: bridgeEnabled ? persistedBridge?.reasonCode : 'bridge_disabled',
    lastSyncAt: persistedBridge?.lastSyncAt,
    error: bridgeEnabled ? persistedBridge?.lastError : undefined,
  };
}

export async function getRuntimeFoundationSnapshot(
  gatewayManager: GatewayManager,
): Promise<RuntimeFoundationSnapshot> {
  const settings = await getAllSettings();
  const now = Date.now();
  const persistedRuntime = settings.runtime;
  const mode = persistedRuntime?.mode ?? runtimeModeFromInstallChoice(persistedRuntime?.installChoice ?? 'both');
  const installChoice = persistedRuntime?.installChoice ?? installChoiceFromMode(mode);

  const runtime: RuntimeSettings = {
    installChoice,
    mode,
    installedKinds: normalizeInstalledKinds(persistedRuntime?.installedKinds, mode),
    windowsHermesPreferredMode: persistedRuntime?.windowsHermesPreferredMode,
    windowsHermesNativePath: persistedRuntime?.windowsHermesNativePath,
    windowsHermesWslDistro: persistedRuntime?.windowsHermesWslDistro,
    lastStandaloneRuntime: persistedRuntime?.lastStandaloneRuntime,
  };

  const persistedBridge = settings.bridge?.hermesAsOpenClawAgent;
  const persistedBridgeStatus = buildPersistedBridgeStatus(runtime, persistedBridge);
  const bridge = isHermesClawBothMode(mode)
    ? await new HermesOpenClawBridge(gatewayManager).recheck().catch(() => persistedBridgeStatus)
    : persistedBridgeStatus;

  const openclawInstalled = runtime.installedKinds.includes('openclaw');
  const openclawAdapter = new OpenClawHostAdapter(gatewayManager);
  const hermesAdapter = new HermesStandaloneAdapter(undefined, getHermesStandaloneManager());
  const hermesStandaloneHealth = runtime.mode === 'hermes'
    ? await hermesAdapter.checkHealth().catch((error) => ({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }))
    : undefined;

  const runtimes: RuntimeStatus[] = [
    openclawAdapter.buildRuntimeStatus({ installed: openclawInstalled, checkedAt: now }),
    hermesAdapter.buildRuntimeStatus(runtime, bridge, {
      checkedAt: now,
      standaloneHealth: hermesStandaloneHealth,
    }),
  ];

  return { runtime, bridge, runtimes };
}
