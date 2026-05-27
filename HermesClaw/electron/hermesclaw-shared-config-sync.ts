import { syncHermesClawSharedConfig, type HermesClawSharedConfigSyncScope } from '../runtime/services/hermesclaw-local-integration-service';
import { logger } from '../utils/logger';

let pendingSharedConfigSync: ReturnType<typeof setTimeout> | undefined;

export function scheduleHermesClawSharedConfigSync(
  scope: HermesClawSharedConfigSyncScope = 'incremental',
  delayMs = 250,
): void {
  if (pendingSharedConfigSync) {
    clearTimeout(pendingSharedConfigSync);
  }

  pendingSharedConfigSync = setTimeout(() => {
    pendingSharedConfigSync = undefined;
    void syncHermesClawSharedConfig({ dryRun: false, scope }).catch((error) => {
      logger.warn('Failed to sync HermesClaw shared config after configuration change:', error);
    });
  }, delayMs);
}

export function cancelScheduledHermesClawSharedConfigSync(): void {
  if (!pendingSharedConfigSync) {
    return;
  }
  clearTimeout(pendingSharedConfigSync);
  pendingSharedConfigSync = undefined;
}
