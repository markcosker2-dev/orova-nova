import { invokeIpc } from '@/lib/api-client';
import { trackUiEvent } from './telemetry';
import { normalizeAppError } from './error-model';

const HOST_API_PORT = 13210;
const HOST_API_BASE = `http://127.0.0.1:${HOST_API_PORT}`;

/** Cached Host API auth token, fetched once from the main process via IPC. */
let cachedHostApiToken: string | null = null;

async function getHostApiToken(): Promise<string> {
  if (cachedHostApiToken) return cachedHostApiToken;
  try {
    cachedHostApiToken = await invokeIpc<string>('hostapi:token');
  } catch {
    cachedHostApiToken = '';
  }
  return cachedHostApiToken ?? '';
}

type HostApiProxyResponse = {
  ok?: boolean;
  data?: {
    status?: number;
    ok?: boolean;
    json?: unknown;
    text?: string;
  };
  error?: { message?: string } | string;
  // backward compatibility fields
  success: boolean;
  status?: number;
  json?: unknown;
  text?: string;
};

type HostApiProxyData = {
  status?: number;
  ok?: boolean;
  json?: unknown;
  text?: string;
};

function headersToRecord(headers?: HeadersInit): Record<string, string> {
  if (!headers) return {};
  if (headers instanceof Headers) return Object.fromEntries(headers.entries());
  if (Array.isArray(headers)) return Object.fromEntries(headers);
  return { ...headers };
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json() as { error?: string };
      if (payload?.error) {
        message = payload.error;
      }
    } catch {
      // ignore body parse failure
    }
    throw normalizeAppError(new Error(message), {
      source: 'browser-fallback',
      status: response.status,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return await response.json() as T;
}

function resolveProxyErrorMessage(error: HostApiProxyResponse['error']): string {
  return typeof error === 'string'
    ? error
    : (error?.message || 'Host API proxy request failed');
}

function parseUnifiedProxyResponse<T>(
  response: HostApiProxyResponse,
  path: string,
  method: string,
  startedAt: number,
): T {
  if (!response.ok) {
    throw new Error(resolveProxyErrorMessage(response.error));
  }

  const data: HostApiProxyData = response.data ?? {};
  trackUiEvent('hostapi.fetch', {
    path,
    method,
    source: 'ipc-proxy',
    durationMs: Date.now() - startedAt,
    status: data.status ?? 200,
  });

  if (data.status === 204) return undefined as T;
  if (data.json !== undefined) return data.json as T;
  return data.text as T;
}

function parseLegacyProxyResponse<T>(
  response: HostApiProxyResponse,
  path: string,
  method: string,
  startedAt: number,
): T {
  if (!response.success) {
    throw new Error(resolveProxyErrorMessage(response.error));
  }

  if (!response.ok) {
    const message = response.text
      || (typeof response.json === 'object' && response.json != null && 'error' in (response.json as Record<string, unknown>)
        ? String((response.json as Record<string, unknown>).error)
        : `HTTP ${response.status ?? 'unknown'}`);
    throw new Error(message);
  }

  trackUiEvent('hostapi.fetch', {
    path,
    method,
    source: 'ipc-proxy-legacy',
    durationMs: Date.now() - startedAt,
    status: response.status ?? 200,
  });

  if (response.status === 204) return undefined as T;
  if (response.json !== undefined) return response.json as T;
  return response.text as T;
}

function shouldFallbackToBrowser(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes('invalid ipc channel: hostapi:fetch')
    || normalized.includes("no handler registered for 'hostapi:fetch'")
    || normalized.includes('no handler registered for "hostapi:fetch"')
    || normalized.includes('no handler registered for hostapi:fetch')
    || normalized.includes('window is not defined');
}

function allowLocalhostFallback(): boolean {
  try {
    return window.localStorage.getItem('hermesclaw:allow-localhost-fallback') === '1';
  } catch {
    return false;
  }
}

export async function hostApiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const startedAt = Date.now();
  const method = init?.method || 'GET';
  // In Electron renderer, always proxy through main process to avoid CORS.
  try {
    const response = await invokeIpc<HostApiProxyResponse>('hostapi:fetch', {
      path,
      method,
      headers: headersToRecord(init?.headers),
      body: init?.body ?? null,
    });

    if (typeof response?.ok === 'boolean' && 'data' in response) {
      return parseUnifiedProxyResponse<T>(response, path, method, startedAt);
    }

    return parseLegacyProxyResponse<T>(response, path, method, startedAt);
  } catch (error) {
    const normalized = normalizeAppError(error, { source: 'ipc-proxy', path, method });
    const message = normalized.message;
    trackUiEvent('hostapi.fetch_error', {
      path,
      method,
      source: 'ipc-proxy',
      durationMs: Date.now() - startedAt,
      message,
      code: normalized.code,
    });
    if (!shouldFallbackToBrowser(message)) {
      throw normalized;
    }
    if (!allowLocalhostFallback()) {
      trackUiEvent('hostapi.fetch_error', {
        path,
        method,
        source: 'ipc-proxy',
        durationMs: Date.now() - startedAt,
        message: 'localhost fallback blocked by policy',
        code: 'CHANNEL_UNAVAILABLE',
      });
      throw normalized;
    }
  }

  // Browser-only fallback (non-Electron environments).
  const token = await getHostApiToken();
  const response = await fetch(`${HOST_API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });
  trackUiEvent('hostapi.fetch', {
    path,
    method,
    source: 'browser-fallback',
    durationMs: Date.now() - startedAt,
    status: response.status,
  });
  try {
    return await parseResponse<T>(response);
  } catch (error) {
    throw normalizeAppError(error, { source: 'browser-fallback', path, method });
  }
}

export type RuntimeStatusSnapshot = {
  runtime: {
    installChoice: 'openclaw' | 'hermes' | 'both';
    mode: 'openclaw' | 'hermes' | 'hermesclaw-both' | 'openclaw-with-hermes-agent';
    installedKinds: Array<'openclaw' | 'hermes'>;
    windowsHermesPreferredMode?: 'native' | 'wsl2';
    windowsHermesNativePath?: string;
    windowsHermesWslDistro?: string;
    lastStandaloneRuntime?: 'openclaw' | 'hermes';
  };
  bridge: {
    enabled: boolean;
    attached: boolean;
    hermesInstalled: boolean;
    hermesHealthy: boolean;
    openclawRecognized: boolean;
    reasonCode?:
      | 'bridge_disabled'
      | 'hermes_not_installed'
      | 'bridge_config_missing'
      | 'openclaw_gateway_stopped'
      | 'openclaw_recognition_pending'
      | 'openclaw_health_failed'
      | 'hermes_home_unreachable';
    lastSyncAt?: number;
    error?: string;
  };
  runtimes: Array<{
    kind: 'openclaw' | 'hermes';
    installed: boolean;
    running: boolean;
    healthy: boolean;
    version?: string;
    endpoint?: string;
    error?: string;
  }>;
};

export type RuntimeModeSelection = Pick<RuntimeStatusSnapshot['runtime'], 'installChoice' | 'mode'>;

export type RuntimeInstallChoiceSelection = Pick<RuntimeStatusSnapshot['runtime'], 'installChoice'>;

export type RuntimeHealthSnapshot = RuntimeStatusSnapshot & {
  checkedAt: number;
  summary: {
    primaryRuntimeKind: 'openclaw' | 'hermes';
    primaryRuntimeHealthy: boolean;
    bridgeRequired: boolean;
    bridgeReady: boolean;
    issues: string[];
  };
};

export type RuntimeInstallResult = {
  success: boolean;
  installChoice: 'openclaw' | 'hermes' | 'both';
  steps: Array<{
    id: 'openclaw' | 'hermes' | 'bridge';
    kind: 'runtime' | 'bridge';
    status: 'pending' | 'installing' | 'completed' | 'failed' | 'skipped';
    label: string;
    error?: string;
  }>;
  snapshot: RuntimeStatusSnapshot;
  error?: string;
};

export type HermesRuntimeLifecycleResult = {
  success: boolean;
  action: 'start' | 'stop' | 'restart';
  snapshot: RuntimeStatusSnapshot;
  error?: string;
};

export type OpenClawRuntimeLifecycleResult = {
  success: boolean;
  action: 'start' | 'stop' | 'restart';
  snapshot: RuntimeStatusSnapshot;
  error?: string;
};

export type OpenClawRuntimeUpdateResult = {
  supported: true;
  runtime: 'openclaw';
  action: 'check-update' | 'apply-update' | 'rollback';
  success?: boolean;
  channel?: HermesClawVersionChannel;
  currentVersion?: string;
  latestVersion?: string;
  updateAvailable?: boolean;
  version?: string;
  backupId?: string;
  restoredVersion?: string;
  rolledBack?: boolean;
  rollbackBackupId?: string;
  rollbackError?: string;
  releaseNotes?: string;
  risk?: 'low' | 'medium' | 'high';
  gatewayRefreshAction?: 'reload' | 'restart';
  gatewayReady?: boolean;
  gatewayHealth?: {
    ok: boolean;
    error?: string;
    uptime?: number;
  };
  gatewayStatus?: {
    state: string;
    gatewayReady?: boolean;
    pid?: number;
    version?: string;
  };
  gatewayDiagnostics?: {
    lastAliveAt?: number;
    lastRpcSuccessAt?: number;
    lastRpcFailureAt?: number;
    lastRpcFailureMethod?: string;
    lastHeartbeatTimeoutAt?: number;
    consecutiveHeartbeatMisses: number;
    lastSocketCloseAt?: number;
    lastSocketCloseCode?: number;
    consecutiveRpcFailures: number;
  };
  error?: string;
  snapshot: RuntimeStatusSnapshot;
};

export type HermesClawVersionChannel = 'stable' | 'beta' | 'nightly';

export type HermesClawRuntimeManifest = {
  schemaVersion: 1;
  activeChannel: HermesClawVersionChannel;
  channels: Partial<Record<HermesClawVersionChannel, {
    version?: string;
    runtimeDir?: string;
    updatedAt?: number;
    backupId?: string;
  }>>;
  rollbackStack: Array<{
    id: string;
    runtime?: 'openclaw' | 'hermes';
    channel: HermesClawVersionChannel;
    version?: string;
    runtimeDir?: string;
    createdAt: number;
  }>;
};

export type HermesClawRuntimeLayout = {
  rootDir: string;
  packagedBaselineDir: string;
  baselineRuntimesDir: string;
  userRuntimesDir: string;
  runtimeStateDir: string;
  activeRuntimesPath: string;
  compatibilityMatrixPath: string;
  installHistoryPath: string;
  sharedConfigDir: string;
  manifestPath: string;
  backupsDir: string;
  logsDir: string;
  cacheDir: string;
};

export type HermesClawRuntimeStateStatus =
  | 'not-installed'
  | 'installed'
  | 'starting'
  | 'ready'
  | 'degraded'
  | 'stopping'
  | 'stopped'
  | 'updating'
  | 'rollback-required'
  | 'error';

export type HermesClawActiveRuntimeRecord = {
  runtime: 'openclaw' | 'hermes';
  channel: HermesClawVersionChannel;
  version: string;
  runtimeDir: string;
  status: HermesClawRuntimeStateStatus;
  lastKnownGoodVersion?: string;
  lastKnownGoodRuntimeDir?: string;
  updatedAt: number;
  lastError?: string;
};

export type HermesClawActiveRuntimesState = {
  schemaVersion: 1;
  runtimes: Partial<Record<'openclaw' | 'hermes', HermesClawActiveRuntimeRecord>>;
};

export type HermesClawCompatibilityMatrix = {
  schemaVersion: 1;
  bridgeProtocol?: string;
  hermes: {
    latestVersion?: string;
    versions: Array<{
      version: string;
      channel?: HermesClawVersionChannel;
      runtimeDir?: string;
      downloadUrl?: string;
      checksum?: string;
      signature?: string;
      releaseNotes?: string;
      risk?: 'low' | 'medium' | 'high';
      bridgeProtocol?: string;
      compatibleOpenClaw?: string;
    }>;
    manifestUrl?: string;
    trustedSignatures?: string[];
  };
  openclaw?: {
    latestVersion?: string;
    versions: Array<{
      version: string;
      channel?: HermesClawVersionChannel;
      runtimeDir?: string;
      downloadUrl?: string;
      checksum?: string;
      signature?: string;
      releaseNotes?: string;
      risk?: 'low' | 'medium' | 'high';
      bridgeProtocol?: string;
      compatibleOpenClaw?: string;
    }>;
    manifestUrl?: string;
    trustedSignatures?: string[];
  };
  updatedAt?: number;
};

export type HermesClawInstallHistory = {
  schemaVersion: 1;
  entries: Array<{
    id: string;
    runtime: 'openclaw' | 'hermes';
    channel: HermesClawVersionChannel;
    version?: string;
    action: 'check' | 'apply' | 'rollback' | 'auto-rollback' | 'failed-update';
    status: 'success' | 'failure';
    runtimeDir?: string;
    backupId?: string;
    error?: string;
    createdAt: number;
  }>;
};

export type HermesClawLocalStatus = {
  layout: HermesClawRuntimeLayout;
  manifest: HermesClawRuntimeManifest;
  runtimeState: HermesClawActiveRuntimesState;
  compatibilityMatrix: HermesClawCompatibilityMatrix;
  installHistory: HermesClawInstallHistory;
  installStatus: {
    installed: boolean;
    installPath?: string;
    version?: string;
    error?: string;
  };
  bridge: RuntimeStatusSnapshot['bridge'];
};

export type HermesClawDoctorResult = {
  ok: boolean;
  checkedAt: number;
  checks: Array<{
    id: 'runtime-directories'
      | 'manifest'
      | 'install-status'
      | 'port'
      | 'config'
      | 'python'
      | 'bridge'
      | 'executable'
      | 'runtime-state'
      | 'compatibility'
      | 'sync-status'
      | 'repair';
    status: 'pass' | 'warn' | 'fail';
    label: string;
    detail?: string;
    repairAction?: string;
  }>;
  reportPath: string;
  repairPlan: string[];
};

export type HermesClawRepairResult = {
  success: boolean;
  repaired: string[];
  doctor: HermesClawDoctorResult;
};

export type HermesClawLogsLocation = {
  dir: string;
};

export type HermesClawOpenLogsResult = {
  success: boolean;
  dir: string;
  error?: string;
};

export type HermesClawUpdateCheckResult = {
  channel: HermesClawVersionChannel;
  currentVersion?: string;
  latestVersion?: string;
  updateAvailable: boolean;
  releaseNotes?: string;
  risk?: 'low' | 'medium' | 'high';
};

export type HermesClawUpdateApplyResult = {
  success: boolean;
  channel: HermesClawVersionChannel;
  version: string;
  backupId: string;
  rolledBack?: boolean;
  restoredVersion?: string;
  rollbackRequired?: boolean;
  error?: string;
};

export type HermesClawRollbackResult = {
  success: boolean;
  restoredVersion?: string;
  backupId?: string;
  error?: string;
};

export type HermesClawSharedConfigRegistry = {
  schemaVersion: 1;
  skills: Array<{
    id: string;
    name?: string;
    description?: string;
    runtimeSupport: Array<'openclaw' | 'hermes' | 'both'>;
    entry?: string | {
      type?: string;
      path?: string;
      command?: string;
      args?: string[];
    };
    permissions?: string[];
    schemaVersion?: number;
    source?: string;
  }>;
  agents: Array<{
    id: string;
    name?: string;
    provider?: string;
    providerRef?: string;
    model?: string;
    systemPrompt?: string;
    tools?: string[];
    skills?: string[];
    rules?: string[];
    runtimePreference?: 'openclaw' | 'hermes' | 'auto';
  }>;
  rules: Array<{
    id: string;
    scope: 'global' | 'workspace' | 'project' | 'agent' | 'skill';
    priority: number;
    enabled: boolean;
    content?: string;
  }>;
  providers: Array<{
    id: string;
    provider: string;
    configRef: string;
    baseUrlRef?: string;
  }>;
  tools: Array<{
    id: string;
    command: string;
    runtimeSupport: Array<'openclaw' | 'hermes' | 'both'>;
    permissions?: string[];
  }>;
  hooks: Array<{
    id: string;
    event: string;
    command: string;
    runtimeSupport: Array<'openclaw' | 'hermes' | 'both'>;
  }>;
  updatedAt?: number;
};

export type HermesClawSharedConfigIssue = {
  severity: 'error' | 'warning';
  code: string;
  path: string;
  message: string;
};

export type HermesClawSharedConfigConflict = {
  code: string;
  ids: string[];
  message: string;
};

export type HermesClawRuntimeAdapterOutput = {
  skills: Array<Record<string, unknown>>;
  agents: Array<Record<string, unknown>>;
  rules: Array<Record<string, unknown>>;
  providers: Array<Record<string, unknown>>;
  tools: Array<Record<string, unknown>>;
  hooks: Array<Record<string, unknown>>;
};

export type HermesClawSharedConfigSyncResult = {
  dryRun: boolean;
  scope: 'manual' | 'startup' | 'incremental' | 'repair';
  changes: Array<{ type: string; path: string }>;
  log: string[];
  validation: {
    ok: boolean;
    issues: HermesClawSharedConfigIssue[];
  };
  conflicts: HermesClawSharedConfigConflict[];
  adapters: {
    openclaw: HermesClawRuntimeAdapterOutput;
    hermes: HermesClawRuntimeAdapterOutput;
  };
};

export async function getRuntimeMode(): Promise<RuntimeModeSelection> {
  return hostApiFetch<RuntimeModeSelection>('/api/runtime/mode');
}

export async function setRuntimeMode(
  mode: RuntimeStatusSnapshot['runtime']['mode'],
): Promise<{ success: boolean; mode: RuntimeStatusSnapshot['runtime']['mode'] }> {
  return hostApiFetch('/api/runtime/mode', {
    method: 'PUT',
    body: JSON.stringify({ mode }),
  });
}

export async function getRuntimeInstallChoice(): Promise<RuntimeInstallChoiceSelection> {
  return hostApiFetch<RuntimeInstallChoiceSelection>('/api/runtime/install-choice');
}

export async function setRuntimeInstallChoice(
  installChoice: RuntimeStatusSnapshot['runtime']['installChoice'],
): Promise<{ success: boolean; installChoice: RuntimeStatusSnapshot['runtime']['installChoice'] }> {
  return hostApiFetch('/api/runtime/install-choice', {
    method: 'PUT',
    body: JSON.stringify({ installChoice }),
  });
}

export async function getRuntimeStatus(): Promise<RuntimeStatusSnapshot> {
  return hostApiFetch<RuntimeStatusSnapshot>('/api/runtime/status');
}

export async function installRuntime(
  installChoice: RuntimeStatusSnapshot['runtime']['installChoice'],
): Promise<RuntimeInstallResult> {
  return hostApiFetch<RuntimeInstallResult>('/api/runtime/install', {
    method: 'POST',
    body: JSON.stringify({ installChoice }),
  });
}

export async function runRuntimeHealthCheck(): Promise<RuntimeHealthSnapshot> {
  return hostApiFetch<RuntimeHealthSnapshot>('/api/runtime/health-check', {
    method: 'POST',
  });
}

export async function startHermesRuntime(): Promise<HermesRuntimeLifecycleResult> {
  return hostApiFetch<HermesRuntimeLifecycleResult>('/api/runtime/hermes/start', {
    method: 'POST',
  });
}

export async function stopHermesRuntime(): Promise<HermesRuntimeLifecycleResult> {
  return hostApiFetch<HermesRuntimeLifecycleResult>('/api/runtime/hermes/stop', {
    method: 'POST',
  });
}

export async function restartHermesRuntime(): Promise<HermesRuntimeLifecycleResult> {
  return hostApiFetch<HermesRuntimeLifecycleResult>('/api/runtime/hermes/restart', {
    method: 'POST',
  });
}

async function runOpenClawLifecycleAction(action: 'start' | 'stop' | 'restart'): Promise<OpenClawRuntimeLifecycleResult> {
  const endpoint = action === 'start'
    ? '/api/gateway/start'
    : action === 'stop'
      ? '/api/gateway/stop'
      : '/api/gateway/restart';
  const result = await hostApiFetch<{ success: boolean; error?: string }>(endpoint, { method: 'POST' });
  return {
    success: result.success,
    action,
    snapshot: await getRuntimeStatus(),
    error: result.error,
  };
}

export async function startOpenClawRuntime(): Promise<OpenClawRuntimeLifecycleResult> {
  return runOpenClawLifecycleAction('start');
}

export async function stopOpenClawRuntime(): Promise<OpenClawRuntimeLifecycleResult> {
  return runOpenClawLifecycleAction('stop');
}

export async function restartOpenClawRuntime(): Promise<OpenClawRuntimeLifecycleResult> {
  return runOpenClawLifecycleAction('restart');
}

export async function checkOpenClawUpdate(): Promise<OpenClawRuntimeUpdateResult> {
  return hostApiFetch<OpenClawRuntimeUpdateResult>('/api/runtime/openclaw/update/check', {
    method: 'POST',
  });
}

export async function applyOpenClawUpdate(): Promise<OpenClawRuntimeUpdateResult> {
  return hostApiFetch<OpenClawRuntimeUpdateResult>('/api/runtime/openclaw/update/apply', {
    method: 'POST',
  });
}

export async function rollbackOpenClawRuntime(): Promise<OpenClawRuntimeUpdateResult> {
  return hostApiFetch<OpenClawRuntimeUpdateResult>('/api/runtime/openclaw/rollback', {
    method: 'POST',
  });
}

export async function getHermesClawLocalStatus(): Promise<HermesClawLocalStatus> {
  return hostApiFetch<HermesClawLocalStatus>('/api/runtime/hermesclaw/status');
}

export async function runHermesClawDoctor(): Promise<HermesClawDoctorResult> {
  return hostApiFetch<HermesClawDoctorResult>('/api/runtime/hermesclaw/doctor', {
    method: 'POST',
  });
}

export async function repairHermesClawInstallation(): Promise<HermesClawRepairResult> {
  return hostApiFetch<HermesClawRepairResult>('/api/runtime/hermesclaw/repair', {
    method: 'POST',
  });
}

export async function getHermesClawLogsLocation(): Promise<HermesClawLogsLocation> {
  return hostApiFetch<HermesClawLogsLocation>('/api/runtime/hermesclaw/logs');
}

export async function openHermesClawLogsLocation(): Promise<HermesClawOpenLogsResult> {
  return hostApiFetch<HermesClawOpenLogsResult>('/api/runtime/hermesclaw/logs/open', {
    method: 'POST',
  });
}

export async function checkHermesClawUpdate(
  channel?: HermesClawVersionChannel,
): Promise<HermesClawUpdateCheckResult> {
  return hostApiFetch<HermesClawUpdateCheckResult>('/api/runtime/hermesclaw/update/check', {
    method: 'POST',
    body: JSON.stringify({ channel }),
  });
}

export async function applyHermesClawUpdate(input: {
  channel?: HermesClawVersionChannel;
  version?: string;
}): Promise<HermesClawUpdateApplyResult> {
  return hostApiFetch<HermesClawUpdateApplyResult>('/api/runtime/hermesclaw/update/apply', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function rollbackHermesClawRuntime(): Promise<HermesClawRollbackResult> {
  return hostApiFetch<HermesClawRollbackResult>('/api/runtime/hermesclaw/rollback', {
    method: 'POST',
  });
}

export async function getHermesClawSharedConfig(): Promise<HermesClawSharedConfigRegistry> {
  return hostApiFetch<HermesClawSharedConfigRegistry>('/api/runtime/hermesclaw/shared-config');
}

export async function syncHermesClawSharedConfig(input: {
  dryRun?: boolean;
  scope?: HermesClawSharedConfigSyncResult['scope'];
} = {}): Promise<HermesClawSharedConfigSyncResult> {
  return hostApiFetch<HermesClawSharedConfigSyncResult>('/api/runtime/hermesclaw/shared-config/sync', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function getHermesRuntimeStatus<T = unknown>(): Promise<T> {
  return hostApiFetch<T>('/api/runtime/hermes/status');
}

export async function getHermesRuntimeHealth<T = unknown>(): Promise<T> {
  return hostApiFetch<T>('/api/runtime/hermes/health');
}

export async function getHermesRuntimeModels<T = unknown>(): Promise<T> {
  return hostApiFetch<T>('/api/runtime/hermes/models');
}

export async function sendHermesRuntimeChatCompletion<T = unknown>(body: unknown): Promise<T> {
  return hostApiFetch<T>('/api/runtime/hermes/chat/completions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function attachHermesOpenClawBridge(): Promise<void> {
  await hostApiFetch('/api/bridges/hermes-openclaw/attach', {
    method: 'POST',
  });
}

export async function detachHermesOpenClawBridge(): Promise<void> {
  await hostApiFetch('/api/bridges/hermes-openclaw/detach', {
    method: 'POST',
  });
}

export async function recheckHermesOpenClawBridge(): Promise<void> {
  await hostApiFetch('/api/bridges/hermes-openclaw/recheck', {
    method: 'POST',
  });
}

export function createHostEventSource(path = '/api/events'): EventSource {
  // EventSource does not support custom headers, so pass the auth token
  // as a query parameter. The server accepts both mechanisms.
  const separator = path.includes('?') ? '&' : '?';
  const tokenParam = `token=${encodeURIComponent(cachedHostApiToken ?? '')}`;
  return new EventSource(`${HOST_API_BASE}${path}${separator}${tokenParam}`);
}

export function getHostApiBase(): string {
  return HOST_API_BASE;
}
