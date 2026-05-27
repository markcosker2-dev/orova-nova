import type { GatewayManager } from '../gateway/manager';
import { syncRuntimeStartup } from '../runtime/services/runtime-startup-coordinator';
import { logger } from '../utils/logger';

export function scheduleRuntimeStartupSync(
  gatewayManager: GatewayManager,
  failureMessage: string,
): void {
  void syncRuntimeStartup(gatewayManager).catch((error) => {
    logger.warn(failureMessage, error);
  });
}
