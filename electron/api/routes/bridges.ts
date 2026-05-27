import type { IncomingMessage, ServerResponse } from 'http';
import { HermesOpenClawBridge } from '../../runtime/services/hermes-openclaw-bridge-service';
import type { HostApiContext } from '../context';
import { sendJson } from '../route-utils';

export async function handleBridgeRoutes(
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
  ctx: HostApiContext,
): Promise<boolean> {
  const bridgeService = new HermesOpenClawBridge(ctx.gatewayManager);

  if (url.pathname === '/api/bridges/hermes-openclaw/status' && req.method === 'GET') {
    sendJson(res, 200, await bridgeService.getStatus());
    return true;
  }

  if (url.pathname === '/api/bridges/hermes-openclaw/attach' && req.method === 'POST') {
    try {
      sendJson(res, 200, { success: true, bridge: await bridgeService.attach() });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  if (url.pathname === '/api/bridges/hermes-openclaw/detach' && req.method === 'POST') {
    try {
      sendJson(res, 200, { success: true, bridge: await bridgeService.detach() });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  if (url.pathname === '/api/bridges/hermes-openclaw/recheck' && req.method === 'POST') {
    sendJson(res, 200, { success: true, bridge: await bridgeService.recheck() });
    return true;
  }

  return false;
}
