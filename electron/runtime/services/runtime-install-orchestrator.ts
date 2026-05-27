import { installedKindsFromChoice, isHermesClawBothMode, runtimeModeFromInstallChoice } from '../mode-registry';
import type { BridgeSettings, InstallChoice, RuntimeSettings } from '../types';

interface RuntimeInstallStateInput {
  runtime: RuntimeSettings;
  bridge: BridgeSettings;
}

interface RuntimeInstallStateOutput {
  runtime: RuntimeSettings;
  bridge: BridgeSettings;
}

export function buildRuntimeInstallState(
  input: RuntimeInstallStateInput,
  installChoice: InstallChoice,
): RuntimeInstallStateOutput {
  const mode = runtimeModeFromInstallChoice(installChoice);
  const installedKinds = installedKindsFromChoice(installChoice);
  const bridgeEnabled = isHermesClawBothMode(mode);

  return {
    runtime: {
      ...input.runtime,
      installChoice,
      mode,
      installedKinds,
      lastStandaloneRuntime: installChoice === 'both'
        ? input.runtime.lastStandaloneRuntime ?? 'openclaw'
        : installChoice,
    },
    bridge: {
      ...input.bridge,
      hermesAsOpenClawAgent: {
        ...input.bridge.hermesAsOpenClawAgent,
        enabled: bridgeEnabled,
        attached: bridgeEnabled ? Boolean(input.bridge.hermesAsOpenClawAgent.attached) : false,
        hermesInstalled: installedKinds.includes('hermes'),
        hermesHealthy: bridgeEnabled ? Boolean(input.bridge.hermesAsOpenClawAgent.hermesHealthy) : false,
        openclawRecognized: bridgeEnabled ? Boolean(input.bridge.hermesAsOpenClawAgent.openclawRecognized) : false,
        reasonCode: bridgeEnabled ? input.bridge.hermesAsOpenClawAgent.reasonCode : 'bridge_disabled',
        lastSyncAt: bridgeEnabled ? input.bridge.hermesAsOpenClawAgent.lastSyncAt : undefined,
        lastError: bridgeEnabled ? input.bridge.hermesAsOpenClawAgent.lastError : undefined,
      },
    },
  };
}
