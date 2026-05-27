/**
 * Config Reload Without Restart Module
 * 
 * Implements a 3-tier config reload strategy:
 * 1. Tier 1: config.patch (partial config update via RPC)
 * 2. Tier 2: Deferred restart (if gateway is stable)
 * 3. Tier 3: Immediate restart (if deferred restart not possible)
 * 
 * Note: config.reload RPC method does not exist in OpenClaw protocol.
 * See: https://github.com/openclaw/openclaw/blob/main/docs/gateway/protocol.md (lines 398-403)
 * Available config methods: config.get, config.set, config.patch, config.apply, config.schema, config.schema.lookup
 */

import { logger } from '../utils/logger';
import type { GatewayManager } from './manager';
import type { GatewayRestartController } from './restart-controller';
import type { GatewayReloadPolicy } from './reload-policy';

export interface ConfigReloadOptions {
  reason: string;
  allowRestart?: boolean;
  rpcTimeoutMs?: number;
  debounceMs?: number;
}

export interface ConfigReloadResult {
  success: boolean;
  method: 'config.patch' | 'deferred-restart' | 'immediate-restart' | 'failed';
  error?: string;
  durationMs: number;
}

export class ConfigReloadHandler {
  private lastReloadAttemptAt = 0;
  private lastSuccessfulReloadAt = 0;
  private consecutiveReloadFailures = 0;

  constructor(
    private gatewayManager: GatewayManager,
    private restartController: GatewayRestartController,
    private reloadPolicy: GatewayReloadPolicy,
  ) {}

  async reload(options: ConfigReloadOptions): Promise<ConfigReloadResult> {
    const startTime = Date.now();
    const { reason, allowRestart = true, rpcTimeoutMs = 10000, debounceMs } = options;

    logger.info(`[ConfigReload] Starting reload (reason=${reason}, policy=${this.reloadPolicy.mode})`);

    try {
      // Tier 1: Attempt config.patch (partial config update)
      if (this.reloadPolicy.mode === 'reload' || this.reloadPolicy.mode === 'hybrid') {
        const patchResult = await this.attemptConfigPatch(rpcTimeoutMs);
        if (patchResult.success) {
          this.recordReloadSuccess();
          return {
            success: true,
            method: 'config.patch',
            durationMs: Date.now() - startTime,
          };
        }
      }

      // Tier 2: Deferred restart (if gateway is stable)
      if (allowRestart && (this.reloadPolicy.mode === 'restart' || this.reloadPolicy.mode === 'hybrid')) {
        const deferralContext = {
          state: this.gatewayManager.getStatus().state,
          startLock: this.gatewayManager.isStartLocked(),
          shouldReconnect: true,
        };

        if (this.restartController.isRestartDeferred(deferralContext)) {
          logger.info(`[ConfigReload] Deferring restart (reason=${reason})`);
          this.restartController.markDeferredRestart(reason, deferralContext);
          return {
            success: true,
            method: 'deferred-restart',
            durationMs: Date.now() - startTime,
          };
        }

        // Tier 3: Immediate restart (with debounce)
        const delay = debounceMs ?? this.reloadPolicy.debounceMs;
        logger.info(`[ConfigReload] Scheduling restart with ${delay}ms debounce`);
        this.restartController.debouncedRestart(delay, () => {
          this.gatewayManager.restart().catch((err) => {
            logger.error(`[ConfigReload] Restart failed: ${err}`);
          });
        });

        return {
          success: true,
          method: 'immediate-restart',
          durationMs: Date.now() - startTime,
        };
      }

      this.consecutiveReloadFailures += 1;
      return {
        success: false,
        method: 'failed',
        error: `Config reload failed (policy=${this.reloadPolicy.mode})`,
        durationMs: Date.now() - startTime,
      };
    } catch (error) {
      this.consecutiveReloadFailures += 1;
      const errorMsg = error instanceof Error ? error.message : String(error);
      logger.error(`[ConfigReload] Unexpected error: ${errorMsg}`);
      return {
        success: false,
        method: 'failed',
        error: errorMsg,
        durationMs: Date.now() - startTime,
      };
    }
  }

  private async attemptConfigPatch(timeoutMs: number): Promise<{ success: boolean; error?: string }> {
    try {
      logger.debug('[ConfigReload] Attempting RPC config.patch');
      await this.gatewayManager.rpc('config.patch', {}, timeoutMs);
      logger.info('[ConfigReload] RPC config.patch succeeded');
      return { success: true };
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      return { success: false, error: errorMsg };
    }
  }

  private recordReloadSuccess(): void {
    this.lastSuccessfulReloadAt = Date.now();
    this.lastReloadAttemptAt = Date.now();
    this.consecutiveReloadFailures = 0;
  }

  getStats() {
    return {
      lastReloadAttemptAt: this.lastReloadAttemptAt,
      lastSuccessfulReloadAt: this.lastSuccessfulReloadAt,
      consecutiveReloadFailures: this.consecutiveReloadFailures,
    };
  }

  reset(): void {
    this.lastReloadAttemptAt = 0;
    this.lastSuccessfulReloadAt = 0;
    this.consecutiveReloadFailures = 0;
  }
}
