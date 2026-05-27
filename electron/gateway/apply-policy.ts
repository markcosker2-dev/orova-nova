/**
 * Gateway Apply Policy
 * 
 * Determines whether a configuration change requires a full restart, hot-reload, or no action.
 * 
 * Based on QClaw pattern:
 * https://github.com/qiuzhi2046/Qclaw/blob/c494768977f4e48b8eacbfae7ae390af11fc015f/electron/main/gateway-apply-policy.ts
 */

export type GatewayApplyAction = 'none' | 'hot-reload' | 'restart';

export interface GatewayApplyChangeSet {
  changedJsonPaths: string[];
  changedEnvKeys?: string[];
}

export interface GatewayApplyDecision {
  action: GatewayApplyAction;
  reason: string;
  matched: string[];
}

// Configuration paths that require a full restart
const RESTART_PATH_PREFIXES = [
  '$.gateway.mode',
  '$.gateway.port',
  '$.gateway.bind',
  '$.gateway.auth.mode',
  '$.channels',
  '$.plugins.allow',
  '$.plugins.entries',
  '$.plugins.installs',
];

// Configuration paths that support hot-reload
const HOT_RELOAD_PATH_PREFIXES = [
  '$.gateway.auth.token',
];

// Environment variable pattern for hot-reload (secrets)
const HOT_RELOAD_ENV_KEY_PATTERN = /(TOKEN|API_KEY|AUTH|SECRET)/i;

function normalizePathList(paths: string[]): string[] {
  return [...new Set((paths || []).map((path) => String(path || '').trim()).filter(Boolean))];
}

function normalizeEnvKeyList(keys: string[] | undefined): string[] {
  return [...new Set((keys || []).map((key) => String(key || '').trim()).filter(Boolean))];
}

function isPathMatched(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}.`) || path.startsWith(`${prefix}[`);
}

export function resolveGatewayApplyAction(changeSet: GatewayApplyChangeSet): GatewayApplyDecision {
  const changedJsonPaths = normalizePathList(changeSet.changedJsonPaths);
  const changedEnvKeys = normalizeEnvKeyList(changeSet.changedEnvKeys);

  // Check for restart-required paths
  const restartMatched = changedJsonPaths.filter((path) =>
    RESTART_PATH_PREFIXES.some((prefix) => isPathMatched(path, prefix))
  );
  if (restartMatched.length > 0) {
    return {
      action: 'restart',
      reason: 'matched-runtime-topology-paths',
      matched: restartMatched,
    };
  }

  // Check for hot-reload paths and environment variables
  const hotReloadPathMatched = changedJsonPaths.filter((path) =>
    HOT_RELOAD_PATH_PREFIXES.some((prefix) => isPathMatched(path, prefix))
  );
  const hotReloadEnvMatched = changedEnvKeys.filter((key) => HOT_RELOAD_ENV_KEY_PATTERN.test(key));
  const hotReloadMatched = [...hotReloadPathMatched, ...hotReloadEnvMatched.map((key) => `env:${key}`)];
  if (hotReloadMatched.length > 0) {
    return {
      action: 'hot-reload',
      reason: 'matched-secrets-paths',
      matched: hotReloadMatched,
    };
  }

  // No matching paths - no action needed
  return {
    action: 'none',
    reason: 'non-runtime-config-change',
    matched: [],
  };
}
