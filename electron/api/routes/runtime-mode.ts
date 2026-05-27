import type { IncomingMessage, ServerResponse } from 'http';
import { shell } from 'electron';
import type { GatewayDiagnosticsSnapshot, GatewayManager, GatewayStatus } from '../../gateway/manager';
import { InstallerOrchestrator } from '../../runtime/installer-orchestrator';
import {
  applyOpenClawRuntimeUpdate,
  applyHermesClawUpdate,
  checkOpenClawRuntimeUpdate,
  checkHermesClawUpdate,
  getHermesClawLogsLocation,
  getHermesClawLocalStatus,
  getHermesClawSharedConfig,
  repairHermesClawInstallation,
  rollbackOpenClawRuntime,
  rollbackHermesClawRuntime,
  runHermesClawDoctor,
  syncHermesClawSharedConfig,
  type HermesClawVersionChannel,
} from '../../runtime/services/hermesclaw-local-integration-service';
import { getHermesStandaloneManager } from '../../runtime/services/hermes-standalone-manager';
import { getRuntimeFoundationSnapshot } from '../../runtime/services/runtime-status-service';
import { runRuntimeHealthCheck } from '../../runtime/services/runtime-health-service';
import {
  installChoiceFromMode,
  installedKindsFromChoice,
  isHermesClawBothMode,
  normalizeInstalledKinds,
  runtimeModeFromInstallChoice,
} from '../../runtime/mode-registry';
import type { InstallChoice, RuntimeMode } from '../../runtime/types';
import { getAllSettings, setSetting } from '../../utils/store';
import { getHermesEndpoint } from '../../utils/paths';
import { proxyAwareFetch } from '../../utils/proxy-fetch';
import type { HostApiContext } from '../context';
import { parseJsonBody, sendJson } from '../route-utils';

interface RuntimeModeBody {
  mode: RuntimeMode;
}

interface InstallChoiceBody {
  installChoice: InstallChoice;
}

interface RuntimeInstallBody {
  installChoice: InstallChoice;
}

interface HermesClawUpdateBody {
  channel?: HermesClawVersionChannel;
  version?: string;
}

interface HermesClawSharedConfigSyncBody {
  dryRun?: boolean;
  scope?: 'manual' | 'startup' | 'incremental' | 'repair';
}

type HermesLifecycleAction = 'start' | 'stop' | 'restart';

type GatewayReadinessStatus = Pick<GatewayStatus, 'state' | 'gatewayReady' | 'pid' | 'version'>;

type GatewayHealthCheckResult = Awaited<ReturnType<HostApiContext['gatewayManager']['checkHealth']>>;

interface OpenClawRuntimeUpdateOutcome {
  supported?: true;
  runtime?: 'openclaw';
  action?: 'check-update' | 'apply-update' | 'rollback';
  success?: boolean;
  channel?: HermesClawVersionChannel;
  version?: string;
  backupId?: string;
  error?: string;
}

interface OpenClawRollbackOutcome extends OpenClawRuntimeUpdateOutcome {
  restoredVersion?: string;
  backupId?: string;
}

interface OpenClawGatewayReadiness {
  gatewayRefreshAction: 'restart';
  gatewayReady: boolean;
  gatewayHealth: GatewayHealthCheckResult;
  gatewayStatus: GatewayReadinessStatus;
  gatewayDiagnostics?: GatewayDiagnosticsSnapshot;
}

const _OPENCLAW_GATEWAY_READY_ATTEMPTS = 12;
const _OPENCLAW_GATEWAY_READY_INTERVAL_MS = 250;
const OPENCLAW_GATEWAY_STARTING_ATTEMPTS = 120;
const OPENCLAW_GATEWAY_STARTING_INTERVAL_MS = 500;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function runHermesLifecycleAction(action: HermesLifecycleAction, ctx: HostApiContext) {
  const manager = getHermesStandaloneManager();
  if (action === 'start') {
    await manager.start();
  } else if (action === 'stop') {
    await manager.stop();
  } else {
    await manager.restart();
  }

  return {
    success: true,
    action,
    snapshot: await getRuntimeFoundationSnapshot(ctx.gatewayManager),
  };
}

async function readOptionalRuntimeUpdateBody(req: IncomingMessage): Promise<HermesClawUpdateBody> {
  return (await parseJsonBody<HermesClawUpdateBody>(req).catch(() => undefined)) ?? {};
}

async function withRuntimeSnapshot<T extends object>(result: T, ctx: HostApiContext) {
  return {
    ...result,
    snapshot: await getRuntimeFoundationSnapshot(ctx.gatewayManager),
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function gatewayReadyFromStatus(status: GatewayReadinessStatus, health: GatewayHealthCheckResult): boolean {
  return health.ok && status.state === 'running' && status.gatewayReady !== false;
}

async function readOpenClawGatewayReadiness(ctx: HostApiContext): Promise<Pick<OpenClawGatewayReadiness, 'gatewayReady' | 'gatewayHealth' | 'gatewayStatus' | 'gatewayDiagnostics'>> {
  const gatewayHealth = await ctx.gatewayManager.checkHealth();
  const status = ctx.gatewayManager.getStatus();
  const gatewayStatus: GatewayReadinessStatus = {
    state: status.state,
    gatewayReady: status.gatewayReady,
    pid: status.pid,
    version: status.version,
  };
  const gatewayDiagnostics = typeof ctx.gatewayManager.getDiagnostics === 'function'
    ? ctx.gatewayManager.getDiagnostics()
    : undefined;

  return {
    gatewayReady: gatewayReadyFromStatus(gatewayStatus, gatewayHealth),
    gatewayHealth,
    gatewayStatus,
    gatewayDiagnostics,
  };
}

async function waitForOpenClawGatewayRunning(ctx: HostApiContext): Promise<void> {
  for (let attempt = 0; attempt < OPENCLAW_GATEWAY_STARTING_ATTEMPTS; attempt += 1) {
    const status = ctx.gatewayManager.getStatus();
    if (status.state === 'running') {
      return;
    }
    if (status.state === 'error') {
      return;
    }
    await sleep(OPENCLAW_GATEWAY_STARTING_INTERVAL_MS);
  }
}

async function waitForOpenClawGatewayReadyEvent(
  gatewayManager: GatewayManager,
  timeoutMs = 30_000
): Promise<void> {
  if (gatewayManager.getStatus().gatewayReady) return;
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, timeoutMs);
    gatewayManager.once('gateway:ready', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

async function restartOpenClawGateway(ctx: HostApiContext): Promise<OpenClawGatewayReadiness> {
  await ctx.gatewayManager.restart();
  await waitForOpenClawGatewayRunning(ctx);
  await waitForOpenClawGatewayReadyEvent(ctx.gatewayManager, 30_000);
  return { gatewayRefreshAction: 'restart', ...await readOpenClawGatewayReadiness(ctx) };
}

async function withOpenClawGatewayReadiness<T extends OpenClawRuntimeUpdateOutcome>(result: T, ctx: HostApiContext): Promise<T & Partial<OpenClawGatewayReadiness>> {
  if (result.success === false) {
    return result;
  }

  const readiness = await restartOpenClawGateway(ctx);
  if (readiness.gatewayReady) {
    return { ...result, ...readiness };
  }

  return {
    ...result,
    ...readiness,
    success: false,
    error: readiness.gatewayHealth.error
      ? `OpenClaw runtime was updated, but Gateway readiness failed: ${readiness.gatewayHealth.error}`
      : 'OpenClaw runtime was updated, but Gateway did not become ready after refresh',
  };
}

async function withOpenClawApplyReadinessAndRollback<T extends OpenClawRuntimeUpdateOutcome>(result: T, ctx: HostApiContext): Promise<T & Partial<OpenClawGatewayReadiness> & {
  rolledBack?: boolean;
  restoredVersion?: string;
  rollbackBackupId?: string;
  rollbackError?: string;
}> {
  const readyResult = await withOpenClawGatewayReadiness(result, ctx);
  if (readyResult.success !== false) {
    return readyResult;
  }

  const readinessError = readyResult.error ?? 'OpenClaw Gateway readiness failed after update apply';
  let rollback: OpenClawRollbackOutcome;
  try {
    rollback = await rollbackOpenClawRuntime();
  } catch (error) {
    return {
      ...readyResult,
      rolledBack: false,
      rollbackError: errorMessage(error),
      error: `${readinessError}; automatic rollback failed: ${errorMessage(error)}`,
    };
  }

  if (rollback.success === false) {
    return {
      ...readyResult,
      rolledBack: false,
      rollbackError: rollback.error ?? 'OpenClaw rollback failed',
      error: `${readinessError}; automatic rollback failed: ${rollback.error ?? 'OpenClaw rollback failed'}`,
    };
  }

  const rollbackReadiness = await withOpenClawGatewayReadiness(rollback, ctx);
  return {
    ...readyResult,
    ...rollbackReadiness,
    supported: readyResult.supported,
    runtime: readyResult.runtime,
    action: readyResult.action,
    channel: readyResult.channel,
    version: readyResult.version,
    backupId: readyResult.backupId,
    success: false,
    rolledBack: true,
    restoredVersion: rollback.restoredVersion,
    rollbackBackupId: rollback.backupId,
    error: `${readinessError}; automatically rolled back OpenClaw to ${rollback.restoredVersion ?? 'the previous runtime'}`,
  };
}

async function openHermesClawLogsLocation() {
  const location = getHermesClawLogsLocation();
  const error = typeof shell.openPath === 'function' ? await shell.openPath(location.dir) : '';
  return {
    success: !error,
    dir: location.dir,
    error: error || undefined,
  };
}

async function resolveHermesCompatibilityState(ctx: HostApiContext) {
  const snapshot = await getRuntimeFoundationSnapshot(ctx.gatewayManager);
  const hermesRuntime = snapshot.runtimes.find((runtime) => runtime.kind === 'hermes');

  if (snapshot.runtime.mode !== 'hermes') {
    return {
      ok: false as const,
      statusCode: 409,
      error: 'Hermes compatibility proxy is only available in Hermes runtime mode',
    };
  }

  if (!hermesRuntime?.installed) {
    return {
      ok: false as const,
      statusCode: 503,
      error: hermesRuntime?.error || 'Hermes standalone runtime is not installed',
    };
  }

  return {
    ok: true as const,
    endpoint: hermesRuntime.endpoint || getHermesEndpoint(),
  };
}

async function proxyHermesCompatibilityRequest(
  req: IncomingMessage,
  res: ServerResponse,
  ctx: HostApiContext,
  targetPath: string,
  method: 'GET' | 'POST',
): Promise<void> {
  const state = await resolveHermesCompatibilityState(ctx);
  if (!state.ok) {
    sendJson(res, state.statusCode, { success: false, error: state.error });
    return;
  }

  const headers: Record<string, string> = {};
  let body: string | undefined;

  if (method === 'POST') {
    const payload = await parseJsonBody<unknown>(req);
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(payload);
  }

  try {
    const response = await proxyAwareFetch(`${state.endpoint}${targetPath}`, {
      method,
      headers,
      body,
    });

    const rawText = await response.text();
    const text = rawText.trim();
    const payload = text ? JSON.parse(text) : {};

    if (!response.ok) {
      const error = typeof payload === 'object' && payload && 'error' in payload
        ? String((payload as { error?: unknown }).error || `Hermes compatibility request failed with status ${response.status}`)
        : `Hermes compatibility request failed with status ${response.status}`;
      sendJson(res, response.status, { success: false, error, details: payload });
      return;
    }

    sendJson(res, response.status, payload);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    sendJson(res, 502, {
      success: false,
      error: `Failed to reach Hermes endpoint ${state.endpoint}: ${errorMessage}`,
    });
  }
}

function buildResetBridgeState(
  settings: Awaited<ReturnType<typeof getAllSettings>>,
  mode: RuntimeMode,
  installedKinds: Array<'openclaw' | 'hermes'>,
) {
  return {
    ...settings.bridge,
    hermesAsOpenClawAgent: {
      ...settings.bridge.hermesAsOpenClawAgent,
      enabled: isHermesClawBothMode(mode),
      attached: false,
      hermesInstalled: installedKinds.includes('hermes'),
      hermesHealthy: false,
      openclawRecognized: false,
      reasonCode: isHermesClawBothMode(mode) ? undefined : 'bridge_disabled',
      lastSyncAt: undefined,
      lastError: undefined,
    },
  };
}

export async function handleRuntimeModeRoutes(
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
  ctx: HostApiContext,
): Promise<boolean> {
  if (url.pathname === '/api/runtime/mode' && req.method === 'GET') {
    const snapshot = await getRuntimeFoundationSnapshot(ctx.gatewayManager);
    sendJson(res, 200, {
      installChoice: snapshot.runtime.installChoice,
      mode: snapshot.runtime.mode,
    });
    return true;
  }

  if (url.pathname === '/api/runtime/mode' && req.method === 'PUT') {
    try {
      const { mode } = await parseJsonBody<RuntimeModeBody>(req);
      const settings = await getAllSettings();
      const installChoice = installChoiceFromMode(mode);
      const installedKinds = normalizeInstalledKinds(undefined, mode);
      await setSetting('runtime', {
        ...settings.runtime,
        mode,
        installChoice,
        installedKinds,
        lastStandaloneRuntime: installChoice === 'both'
          ? settings.runtime.lastStandaloneRuntime ?? 'openclaw'
          : installChoice,
      });
      await setSetting('bridge', buildResetBridgeState(settings, mode, installedKinds));
      sendJson(res, 200, { success: true, mode });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  if (url.pathname === '/api/runtime/install-choice' && req.method === 'GET') {
    const snapshot = await getRuntimeFoundationSnapshot(ctx.gatewayManager);
    sendJson(res, 200, { installChoice: snapshot.runtime.installChoice });
    return true;
  }

  if (url.pathname === '/api/runtime/install-choice' && req.method === 'PUT') {
    try {
      const { installChoice } = await parseJsonBody<InstallChoiceBody>(req);
      const settings = await getAllSettings();
      const mode = runtimeModeFromInstallChoice(installChoice);
      const installedKinds = installedKindsFromChoice(installChoice);
      await setSetting('runtime', {
        ...settings.runtime,
        installChoice,
        mode,
        installedKinds,
        lastStandaloneRuntime: installChoice === 'hermes' ? 'hermes' : 'openclaw',
      });
      await setSetting('bridge', buildResetBridgeState(settings, mode, installedKinds));
      sendJson(res, 200, { success: true, installChoice });
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  if (url.pathname === '/api/runtime/status' && req.method === 'GET') {
    sendJson(res, 200, await getRuntimeFoundationSnapshot(ctx.gatewayManager));
    return true;
  }

  if (url.pathname === '/api/runtime/install' && req.method === 'POST') {
    try {
      const { installChoice } = await parseJsonBody<RuntimeInstallBody>(req);
      const orchestrator = new InstallerOrchestrator(ctx.gatewayManager, undefined, undefined, undefined, {
        emit: (eventName, payload) => {
          ctx.eventBus.emit(eventName, payload);
          if (eventName === 'runtime:install:progress' && ctx.mainWindow && !ctx.mainWindow.isDestroyed()) {
            ctx.mainWindow.webContents.send('runtime:install-progress', payload);
          }
        },
      });
      sendJson(res, 200, await orchestrator.install(installChoice));
    } catch (error) {
      sendJson(res, 500, { success: false, error: String(error) });
    }
    return true;
  }

  if (url.pathname === '/api/runtime/health-check' && req.method === 'POST') {
    sendJson(res, 200, await runRuntimeHealthCheck(ctx.gatewayManager));
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/start' && req.method === 'POST') {
    try {
      sendJson(res, 200, await runHermesLifecycleAction('start', ctx));
    } catch (error) {
      sendJson(res, 500, { success: false, action: 'start', error: errorMessage(error) });
    }
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/stop' && req.method === 'POST') {
    try {
      sendJson(res, 200, await runHermesLifecycleAction('stop', ctx));
    } catch (error) {
      sendJson(res, 500, { success: false, action: 'stop', error: errorMessage(error) });
    }
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/restart' && req.method === 'POST') {
    try {
      sendJson(res, 200, await runHermesLifecycleAction('restart', ctx));
    } catch (error) {
      sendJson(res, 500, { success: false, action: 'restart', error: errorMessage(error) });
    }
    return true;
  }

  if (url.pathname === '/api/runtime/openclaw/update/check' && req.method === 'POST') {
    const body = await readOptionalRuntimeUpdateBody(req);
    sendJson(res, 200, await withRuntimeSnapshot(await checkOpenClawRuntimeUpdate(body.channel), ctx));
    return true;
  }

  if (url.pathname === '/api/runtime/openclaw/update/apply' && req.method === 'POST') {
    const body = await readOptionalRuntimeUpdateBody(req);
    const result = await applyOpenClawRuntimeUpdate({
      channel: body.channel,
      version: body.version,
    });
    sendJson(res, 200, await withRuntimeSnapshot(await withOpenClawApplyReadinessAndRollback(result, ctx), ctx));
    return true;
  }

  if (url.pathname === '/api/runtime/openclaw/rollback' && req.method === 'POST') {
    const result = await rollbackOpenClawRuntime();
    sendJson(res, 200, await withRuntimeSnapshot(await withOpenClawGatewayReadiness(result, ctx), ctx));
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/status' && req.method === 'GET') {
    sendJson(res, 200, await getHermesClawLocalStatus(ctx.gatewayManager));
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/doctor' && req.method === 'POST') {
    sendJson(res, 200, await runHermesClawDoctor(ctx.gatewayManager));
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/repair' && req.method === 'POST') {
    sendJson(res, 200, await repairHermesClawInstallation(ctx.gatewayManager));
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/logs' && req.method === 'GET') {
    sendJson(res, 200, getHermesClawLogsLocation());
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/logs/open' && req.method === 'POST') {
    sendJson(res, 200, await openHermesClawLogsLocation());
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/update/check' && req.method === 'POST') {
    const body = await parseJsonBody<HermesClawUpdateBody>(req);
    sendJson(res, 200, await checkHermesClawUpdate(body.channel));
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/update/apply' && req.method === 'POST') {
    const body = await parseJsonBody<HermesClawUpdateBody>(req);
    sendJson(res, 200, await applyHermesClawUpdate({
      channel: body.channel,
      version: body.version,
    }));
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/rollback' && req.method === 'POST') {
    sendJson(res, 200, await rollbackHermesClawRuntime());
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/shared-config' && req.method === 'GET') {
    sendJson(res, 200, await getHermesClawSharedConfig());
    return true;
  }

  if (url.pathname === '/api/runtime/hermesclaw/shared-config/sync' && req.method === 'POST') {
    const body = await parseJsonBody<HermesClawSharedConfigSyncBody>(req);
    sendJson(res, 200, await syncHermesClawSharedConfig({
      dryRun: body.dryRun,
      scope: body.scope,
    }));
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/status' && req.method === 'GET') {
    await proxyHermesCompatibilityRequest(req, res, ctx, '/status', 'GET');
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/health' && req.method === 'GET') {
    await proxyHermesCompatibilityRequest(req, res, ctx, '/health', 'GET');
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/models' && req.method === 'GET') {
    await proxyHermesCompatibilityRequest(req, res, ctx, '/v1/models', 'GET');
    return true;
  }

  if (url.pathname === '/api/runtime/hermes/chat/completions' && req.method === 'POST') {
    await proxyHermesCompatibilityRequest(req, res, ctx, '/v1/chat/completions', 'POST');
    return true;
  }

  return false;
}
