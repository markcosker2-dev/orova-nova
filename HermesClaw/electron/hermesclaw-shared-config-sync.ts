/**
 * HermesClaw Shared Config Sync
 * Stub for HermesClaw standalone runtime integration
 */

export type HermesClawSharedConfigSyncScope = 'manual' | 'startup' | 'incremental' | 'repair';

let pendingSharedConfigSync: ReturnType<typeof setTimeout> | undefined;

export function scheduleHermesClawSharedConfigSync(
  _scope: HermesClawSharedConfigSyncScope = 'incremental',
  delayMs = 250,
): void {
  if (pendingSharedConfigSync) {
    clearTimeout(pendingSharedConfigSync);
  }
  pendingSharedConfigSync = setTimeout(() => {
    pendingSharedConfigSync = undefined;
  }, delayMs);
}

export function cancelScheduledHermesClawSharedConfigSync(): void {
  if (!pendingSharedConfigSync) {
    return;
  }
  clearTimeout(pendingSharedConfigSync);
  pendingSharedConfigSync = undefined;
}