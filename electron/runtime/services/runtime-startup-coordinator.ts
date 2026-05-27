import type { GatewayManager } from '../../gateway/manager';
import { logger } from '../../utils/logger';
import { getAllSettings } from '../../utils/store';
import { isHermesClawBothMode } from '../mode-registry';
import { HermesOpenClawBridge } from './hermes-openclaw-bridge-service';
import { getHermesStandaloneManager } from './hermes-standalone-manager';
import { syncHermesClawSharedConfig } from './hermesclaw-local-integration-service';

function isMissingHermesRuntimeManifestEntry(error: unknown): boolean {
  return error instanceof Error
    && error.message.includes('Hermes runtime manifest entry was not found');
}

async function startHermesIfRuntimeIsLaunchable(): Promise<boolean> {
  try {
    await getHermesStandaloneManager().start();
    return true;
  } catch (error) {
    if (!isMissingHermesRuntimeManifestEntry(error)) {
      throw error;
    }

    logger.warn(
      'Skipping Hermes runtime startup because no launchable Hermes runtime is installed yet. Install or repair HermesClaw runtime to enable Hermes startup.',
    );
    return false;
  }
}

async function syncSharedConfigOnStartup(): Promise<void> {
  try {
    await syncHermesClawSharedConfig({ dryRun: false, scope: 'startup' });
  } catch (error) {
    logger.warn('Failed to sync HermesClaw shared config during runtime startup:', error);
  }
}

export async function syncRuntimeStartup(gatewayManager: GatewayManager): Promise<void> {
  const settings = await getAllSettings();
  const runtime = settings.runtime;

  if (runtime.mode === 'hermes' && runtime.installedKinds.includes('hermes')) {
    if (!(await startHermesIfRuntimeIsLaunchable())) {
      return;
    }
    await syncSharedConfigOnStartup();
    return;
  }

  if (!isHermesClawBothMode(runtime.mode) || !runtime.installedKinds.includes('hermes')) {
    return;
  }

  if (!(await startHermesIfRuntimeIsLaunchable())) {
    return;
  }
  await syncSharedConfigOnStartup();

  const gatewayStatus = gatewayManager.getStatus();
  if (gatewayStatus.state !== 'running') {
    return;
  }

  const bridge = new HermesOpenClawBridge(gatewayManager);
  const bridgeStatus = await bridge.recheck();
  if (!bridgeStatus.hermesInstalled || bridgeStatus.attached) {
    return;
  }

  await bridge.attach();
}
