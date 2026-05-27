import type { GatewayManager } from '../../gateway/manager';
import { isHermesClawBothMode } from '../mode-registry';
import { getRuntimeFoundationSnapshot, type RuntimeFoundationSnapshot } from './runtime-status-service';

export interface RuntimeHealthSnapshot extends RuntimeFoundationSnapshot {
  checkedAt: number;
  summary: {
    primaryRuntimeKind: 'openclaw' | 'hermes';
    primaryRuntimeHealthy: boolean;
    bridgeRequired: boolean;
    bridgeReady: boolean;
    issues: string[];
  };
}

export async function runRuntimeHealthCheck(
  gatewayManager: GatewayManager,
): Promise<RuntimeHealthSnapshot> {
  const snapshot = await getRuntimeFoundationSnapshot(gatewayManager);
  const primaryRuntimeKind = snapshot.runtime.mode === 'hermes' ? 'hermes' : 'openclaw';
  const primaryRuntime = snapshot.runtimes.find((runtime) => runtime.kind === primaryRuntimeKind);
  const bridgeRequired = isHermesClawBothMode(snapshot.runtime.mode);
  const bridgeReady = !bridgeRequired || (
    snapshot.bridge.enabled
    && snapshot.bridge.attached
    && snapshot.bridge.openclawRecognized
    && snapshot.bridge.hermesHealthy
  );
  const issues = [
    ...snapshot.runtimes
      .filter((runtime) => runtime.error)
      .map((runtime) => `${runtime.kind}: ${runtime.error}`),
    ...(bridgeRequired && snapshot.bridge.error ? [`bridge: ${snapshot.bridge.error}`] : []),
  ];

  return {
    ...snapshot,
    checkedAt: Date.now(),
    summary: {
      primaryRuntimeKind,
      primaryRuntimeHealthy: Boolean(primaryRuntime?.healthy),
      bridgeRequired,
      bridgeReady,
      issues,
    },
  };
}
