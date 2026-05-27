/**
 * Gateway Lifecycle IPC Routes
 * 
 * Exposes gateway lifecycle operations (start, restart, reload, stop) to the renderer process.
 * Uses the GatewayLifecycleQueue for sequential execution and deduplication.
 */

import type { IncomingMessage, ServerResponse } from 'http';
import type { HostApiContext } from '../context';
import { parseJsonBody, sendJson } from '../route-utils';
import type { GatewayApplyChangeSet } from '../../gateway/apply-policy';
import { resolveGatewayApplyAction } from '../../gateway/apply-policy';

export async function handleGatewayLifecycleRoutes(
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
  ctx: HostApiContext
): Promise<boolean> {
  // Validate that gatewayManager exists
  if (!ctx.gatewayManager) {
    throw new Error('gatewayManager is not available in context');
  }

  // GET /api/gateway/lifecycle-state - Query the current state of the lifecycle queue
  if (url.pathname === '/api/gateway/lifecycle-state' && req.method === 'GET') {
    try {
      const state = ctx.gatewayManager.getLifecycleQueueState();
      sendJson(res, 200, { success: true, state });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // POST /api/gateway/apply-config - Apply a configuration change with smart restart/hot-reload decision
  if (url.pathname === '/api/gateway/apply-config' && req.method === 'POST') {
    try {
      const body = await parseJsonBody<GatewayApplyChangeSet>(req);
      const decision = resolveGatewayApplyAction(body);
      
      interface ApplyConfigResult {
        success: true;
        decision: GatewayApplyChangeSet;
        action?: string;
        message?: string;
      }
      let result: ApplyConfigResult = { success: true, decision };
      
      if (decision.action === 'restart') {
        await ctx.gatewayManager.restart();
        result.action = 'restart';
        result.message = 'Gateway restarted due to configuration change';
      } else if (decision.action === 'hot-reload') {
        // TODO: Implement hot-reload logic when available
        result.action = 'hot-reload';
        result.message = 'Hot-reload not yet implemented, falling back to restart';
        await ctx.gatewayManager.restart();
      } else {
        result.action = 'none';
        result.message = 'No gateway action needed for this configuration change';
      }
      
      sendJson(res, 200, result);
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // POST /api/gateway/restart-with-reason - Restart with a custom reason
  if (url.pathname === '/api/gateway/restart-with-reason' && req.method === 'POST') {
    try {
      const body = await parseJsonBody<{ reason?: string }>(req);
      const reason = body.reason || 'manual-restart';
      await ctx.gatewayManager.restart();
      sendJson(res, 200, { success: true, reason });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  // POST /api/gateway/ensure-ready - Ensure gateway is running
  if (url.pathname === '/api/gateway/ensure-ready' && req.method === 'POST') {
    try {
      await ctx.gatewayManager.start();
      sendJson(res, 200, { success: true, message: 'Gateway is ready' });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  return false;
}
