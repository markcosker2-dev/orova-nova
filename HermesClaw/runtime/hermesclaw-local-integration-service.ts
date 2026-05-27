import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import type { GatewayManager } from '../../gateway/manager';
import { proxyAwareFetch } from '../../utils/proxy-fetch';
import {
  ensureDir,
  ensureHermesClawRuntimeLayout,
  getHermesClawRuntimeLayout,
  getHermesEndpoint,
  getHermesInstallStatus,
  type HermesClawRuntimeLayout,
} from '../../utils/paths';
import { getAllSettings } from '../../utils/store';
import { HermesOpenClawBridge } from './hermes-openclaw-bridge-service';
import { getHermesStandaloneManager } from './hermes-standalone-manager';

export type HermesClawVersionChannel = 'stable' | 'beta' | 'nightly';
export type HermesClawRuntimeKind = 'openclaw' | 'hermes';
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

export interface HermesClawRuntimeChannelState {
  version?: string;
  runtimeDir?: string;
  updatedAt?: number;
  backupId?: string;
}

export interface HermesClawRuntimeManifest {
  schemaVersion: 1;
  activeChannel: HermesClawVersionChannel;
  channels: Partial<Record<HermesClawVersionChannel, HermesClawRuntimeChannelState>>;
  rollbackStack: Array<{
    id: string;
    runtime?: HermesClawRuntimeKind;
    channel: HermesClawVersionChannel;
    version?: string;
    runtimeDir?: string;
    createdAt: number;
  }>;
}

export interface HermesClawActiveRuntimeRecord {
  runtime: HermesClawRuntimeKind;
  channel: HermesClawVersionChannel;
  version: string;
  runtimeDir: string;
  status: HermesClawRuntimeStateStatus;
  lastKnownGoodVersion?: string;
  lastKnownGoodRuntimeDir?: string;
  updatedAt: number;
  lastError?: string;
}

export interface HermesClawActiveRuntimesState {
  schemaVersion: 1;
  runtimes: Partial<Record<HermesClawRuntimeKind, HermesClawActiveRuntimeRecord>>;
}

export interface HermesClawCompatibleVersion {
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
}

export interface HermesClawCompatibilityMatrix {
  schemaVersion: 1;
  bridgeProtocol?: string;
  hermes: {
    manifestUrl?: string;
    latestVersion?: string;
    trustedSignatures?: string[];
    versions: HermesClawCompatibleVersion[];
  };
  openclaw?: {
    manifestUrl?: string;
    latestVersion?: string;
    trustedSignatures?: string[];
    versions: HermesClawCompatibleVersion[];
  };
  updatedAt?: number;
}

export interface HermesClawInstallHistoryEntry {
  id: string;
  runtime: HermesClawRuntimeKind;
  channel: HermesClawVersionChannel;
  version?: string;
  action: 'check' | 'apply' | 'rollback' | 'auto-rollback' | 'failed-update';
  status: 'success' | 'failure';
  runtimeDir?: string;
  backupId?: string;
  error?: string;
  createdAt: number;
}

export interface HermesClawInstallHistory {
  schemaVersion: 1;
  entries: HermesClawInstallHistoryEntry[];
}

export interface HermesClawSharedSkill {
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
}

export interface HermesClawSharedAgent {
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
}

export interface HermesClawSharedRule {
  id: string;
  scope: 'global' | 'workspace' | 'project' | 'agent' | 'skill';
  priority: number;
  enabled: boolean;
  content?: string;
}

export interface HermesClawSharedProviderReference {
  id: string;
  provider: string;
  configRef: string;
  baseUrlRef?: string;
}

export interface HermesClawSharedToolMapping {
  id: string;
  command: string;
  runtimeSupport: Array<'openclaw' | 'hermes' | 'both'>;
  permissions?: string[];
}

export interface HermesClawSharedHook {
  id: string;
  event: string;
  command: string;
  runtimeSupport: Array<'openclaw' | 'hermes' | 'both'>;
}

export interface HermesClawSharedConfigRegistry {
  schemaVersion: 1;
  skills: HermesClawSharedSkill[];
  agents: HermesClawSharedAgent[];
  rules: HermesClawSharedRule[];
  providers: HermesClawSharedProviderReference[];
  tools: HermesClawSharedToolMapping[];
  hooks: HermesClawSharedHook[];
  updatedAt?: number;
}

export interface HermesClawDoctorCheck {
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
}

export interface HermesClawDoctorResult {
  ok: boolean;
  checkedAt: number;
  checks: HermesClawDoctorCheck[];
  reportPath: string;
  repairPlan: string[];
}

export interface HermesClawRepairResult {
  success: boolean;
  repaired: string[];
  doctor: HermesClawDoctorResult;
}

export interface HermesClawLogsLocation {
  dir: string;
}

export type HermesClawSharedConfigSyncScope = 'manual' | 'startup' | 'incremental' | 'repair';

export type HermesClawSharedConfigIssueSeverity = 'error' | 'warning';

export interface HermesClawSharedConfigIssue {
  severity: HermesClawSharedConfigIssueSeverity;
  code: string;
  path: string;
  message: string;
}

export interface HermesClawSharedConfigConflict {
  code: string;
  ids: string[];
  message: string;
}

export interface HermesClawRuntimeAdapterOutput {
  skills: Array<Record<string, unknown>>;
  agents: Array<Record<string, unknown>>;
  rules: Array<Record<string, unknown>>;
  providers: Array<Record<string, unknown>>;
  tools: Array<Record<string, unknown>>;
  hooks: Array<Record<string, unknown>>;
}

export interface HermesClawSharedConfigAdapterBundle {
  openclaw: HermesClawRuntimeAdapterOutput;
  hermes: HermesClawRuntimeAdapterOutput;
}

export interface HermesClawSharedConfigSyncResult {
  dryRun: boolean;
  scope: HermesClawSharedConfigSyncScope;
  changes: Array<{ type: 'create' | 'update'; path: string }>;
  log: string[];
  validation: {
    ok: boolean;
    issues: HermesClawSharedConfigIssue[];
  };
  conflicts: HermesClawSharedConfigConflict[];
  adapters: HermesClawSharedConfigAdapterBundle;
}

export interface HermesClawLocalStatus {
  layout: HermesClawRuntimeLayout;
  manifest: HermesClawRuntimeManifest;
  runtimeState: HermesClawActiveRuntimesState;
  compatibilityMatrix: HermesClawCompatibilityMatrix;
  installHistory: HermesClawInstallHistory;
  installStatus: ReturnType<typeof getHermesInstallStatus>;
  bridge: Awaited<ReturnType<HermesOpenClawBridge['getStatus']>>;
}

const MANIFEST_SCHEMA_VERSION = 1 as const;
const DEFAULT_CHANNEL: HermesClawVersionChannel = 'stable';
const SHARED_CONFIG_REGISTRY_FILE = 'registry.json';

function now(): number {
  return Date.now();
}

function defaultManifest(): HermesClawRuntimeManifest {
  return {
    schemaVersion: MANIFEST_SCHEMA_VERSION,
    activeChannel: DEFAULT_CHANNEL,
    channels: {},
    rollbackStack: [],
  };
}

function defaultSharedConfigRegistry(): HermesClawSharedConfigRegistry {
  return {
    schemaVersion: 1,
    skills: [],
    agents: [],
    rules: [],
    providers: [],
    tools: [],
    hooks: [],
  };
}

function defaultActiveRuntimesState(): HermesClawActiveRuntimesState {
  return {
    schemaVersion: 1,
    runtimes: {},
  };
}

function defaultCompatibilityMatrix(): HermesClawCompatibilityMatrix {
  return {
    schemaVersion: 1,
    hermes: {
      versions: [],
    },
    openclaw: {
      versions: [],
    },
  };
}

function defaultInstallHistory(): HermesClawInstallHistory {
  return {
    schemaVersion: 1,
    entries: [],
  };
}

function readJsonFile<T>(path: string, fallback: T): T {
  if (!existsSync(path)) {
    return fallback;
  }

  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T;
  } catch {
    return fallback;
  }
}

function writeJsonFile(path: string, value: unknown): void {
  ensureDir(dirname(path));
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function getSharedConfigRegistryPath(layout = getHermesClawRuntimeLayout()): string {
  return join(layout.sharedConfigDir, SHARED_CONFIG_REGISTRY_FILE);
}

function normalizeChannel(channel?: unknown): HermesClawVersionChannel {
  return channel === 'beta' || channel === 'nightly' || channel === 'stable'
    ? channel
    : DEFAULT_CHANNEL;
}

function normalizeSharedConfigSyncScope(scope?: unknown): HermesClawSharedConfigSyncScope {
  return scope === 'startup' || scope === 'incremental' || scope === 'repair' || scope === 'manual'
    ? scope
    : 'manual';
}

function supportsRuntime(skill: HermesClawSharedSkill, runtime: 'openclaw' | 'hermes'): boolean {
  const runtimeSupport = Array.isArray(skill.runtimeSupport) ? skill.runtimeSupport : [];
  return runtimeSupport.includes(runtime) || runtimeSupport.includes('both');
}

function runtimeSupportIncludes(runtimeSupport: unknown, runtime: 'openclaw' | 'hermes'): boolean {
  const values = Array.isArray(runtimeSupport) ? runtimeSupport : [];
  return values.includes(runtime) || values.includes('both');
}

function duplicateIds(values: Array<{ id?: string }>): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (!value.id) {
      continue;
    }
    if (seen.has(value.id)) {
      duplicates.add(value.id);
    }
    seen.add(value.id);
  }
  return [...duplicates];
}

function validateSharedConfigRegistry(registry: HermesClawSharedConfigRegistry): HermesClawSharedConfigIssue[] {
  const issues: HermesClawSharedConfigIssue[] = [];
  const skillIds = new Set(registry.skills.map((skill) => skill.id).filter(Boolean));
  const ruleIds = new Set(registry.rules.map((rule) => rule.id).filter(Boolean));
  const providerIds = new Set((registry.providers ?? []).map((provider) => provider.id).filter(Boolean));
  const toolIds = new Set((registry.tools ?? []).map((tool) => tool.id).filter(Boolean));

  registry.skills.forEach((skill, index) => {
    const runtimeSupport = Array.isArray(skill.runtimeSupport) ? skill.runtimeSupport : [];
    if (!skill.id) {
      issues.push({ severity: 'error', code: 'skill_missing_id', path: `skills[${index}]`, message: 'Skill id is required' });
    }
    if (runtimeSupport.length === 0) {
      issues.push({ severity: 'error', code: 'skill_runtime_support_missing', path: `skills[${index}].runtimeSupport`, message: `Skill ${skill.id || index} must declare runtimeSupport` });
    }
    const invalidSupport = runtimeSupport.filter((runtime) => runtime !== 'openclaw' && runtime !== 'hermes' && runtime !== 'both');
    if (invalidSupport.length > 0) {
      issues.push({ severity: 'error', code: 'skill_runtime_support_invalid', path: `skills[${index}].runtimeSupport`, message: `Skill ${skill.id || index} has unsupported runtimes: ${invalidSupport.join(', ')}` });
    }
  });

  registry.agents.forEach((agent, index) => {
    if (!agent.id) {
      issues.push({ severity: 'error', code: 'agent_missing_id', path: `agents[${index}]`, message: 'Agent id is required' });
    }
    for (const skillId of agent.skills ?? []) {
      if (!skillIds.has(skillId)) {
        issues.push({ severity: 'error', code: 'agent_unknown_skill', path: `agents[${index}].skills`, message: `Agent ${agent.id || index} references unknown skill ${skillId}` });
      }
    }
    for (const ruleId of agent.rules ?? []) {
      if (!ruleIds.has(ruleId)) {
        issues.push({ severity: 'error', code: 'agent_unknown_rule', path: `agents[${index}].rules`, message: `Agent ${agent.id || index} references unknown rule ${ruleId}` });
      }
    }
    if (agent.providerRef && !providerIds.has(agent.providerRef)) {
      issues.push({ severity: 'error', code: 'agent_unknown_provider', path: `agents[${index}].providerRef`, message: `Agent ${agent.id || index} references unknown provider ${agent.providerRef}` });
    }
    for (const toolId of agent.tools ?? []) {
      if (!toolIds.has(toolId)) {
        issues.push({ severity: 'error', code: 'agent_unknown_tool', path: `agents[${index}].tools`, message: `Agent ${agent.id || index} references unknown tool ${toolId}` });
      }
    }
  });

  registry.rules.forEach((rule, index) => {
    if (!rule.id) {
      issues.push({ severity: 'error', code: 'rule_missing_id', path: `rules[${index}]`, message: 'Rule id is required' });
    }
    if (!Number.isFinite(rule.priority)) {
      issues.push({ severity: 'error', code: 'rule_priority_invalid', path: `rules[${index}].priority`, message: `Rule ${rule.id || index} must declare a finite priority` });
    }
    if (rule.enabled && (!rule.content || rule.content.trim().length === 0)) {
      issues.push({ severity: 'warning', code: 'rule_content_empty', path: `rules[${index}].content`, message: `Enabled rule ${rule.id || index} has no content` });
    }
  });

  (registry.providers ?? []).forEach((provider, index) => {
    if (!provider.id) {
      issues.push({ severity: 'error', code: 'provider_missing_id', path: `providers[${index}]`, message: 'Provider id is required' });
    }
    if (!provider.provider) {
      issues.push({ severity: 'error', code: 'provider_kind_missing', path: `providers[${index}].provider`, message: `Provider ${provider.id || index} must declare provider` });
    }
    if (!provider.configRef) {
      issues.push({ severity: 'error', code: 'provider_config_ref_missing', path: `providers[${index}].configRef`, message: `Provider ${provider.id || index} must declare configRef` });
    }
  });

  for (const [kind, values] of [
    ['tool', registry.tools ?? []],
    ['hook', registry.hooks ?? []],
  ] as const) {
    values.forEach((value, index) => {
      const runtimeSupport = Array.isArray(value.runtimeSupport) ? value.runtimeSupport : [];
      if (!value.id) {
        issues.push({ severity: 'error', code: `${kind}_missing_id`, path: `${kind}s[${index}]`, message: `${kind} id is required` });
      }
      if (!value.command) {
        issues.push({ severity: 'error', code: `${kind}_command_missing`, path: `${kind}s[${index}].command`, message: `${kind} ${value.id || index} must declare command` });
      }
      if (runtimeSupport.length === 0) {
        issues.push({ severity: 'error', code: `${kind}_runtime_support_missing`, path: `${kind}s[${index}].runtimeSupport`, message: `${kind} ${value.id || index} must declare runtimeSupport` });
      }
      const invalidSupport = runtimeSupport.filter((runtime) => runtime !== 'openclaw' && runtime !== 'hermes' && runtime !== 'both');
      if (invalidSupport.length > 0) {
        issues.push({ severity: 'error', code: `${kind}_runtime_support_invalid`, path: `${kind}s[${index}].runtimeSupport`, message: `${kind} ${value.id || index} has unsupported runtimes: ${invalidSupport.join(', ')}` });
      }
    });
  }

  return issues;
}

function detectSharedConfigConflicts(registry: HermesClawSharedConfigRegistry): HermesClawSharedConfigConflict[] {
  const conflicts: HermesClawSharedConfigConflict[] = [];
  for (const [kind, values] of [
    ['skill', registry.skills],
    ['agent', registry.agents],
    ['rule', registry.rules],
    ['provider', registry.providers ?? []],
    ['tool', registry.tools ?? []],
    ['hook', registry.hooks ?? []],
  ] as const) {
    const duplicates = duplicateIds(values);
    if (duplicates.length > 0) {
      conflicts.push({ code: `${kind}_duplicate_id`, ids: duplicates, message: `Duplicate ${kind} ids: ${duplicates.join(', ')}` });
    }
  }

  const ruleSlots = new Map<string, string[]>();
  for (const rule of registry.rules) {
    const slot = `${rule.scope}:${rule.priority}`;
    ruleSlots.set(slot, [...(ruleSlots.get(slot) ?? []), rule.id]);
  }
  for (const [slot, ids] of ruleSlots) {
    const uniqueIds = ids.filter(Boolean);
    if (uniqueIds.length > 1) {
      conflicts.push({ code: 'rule_priority_conflict', ids: uniqueIds, message: `Rules share scope/priority ${slot}: ${uniqueIds.join(', ')}` });
    }
  }

  return conflicts;
}

function adaptEntry(entry: HermesClawSharedSkill['entry']): unknown {
  return typeof entry === 'string' ? { path: entry } : entry;
}

function adaptSharedConfigForRuntime(
  registry: HermesClawSharedConfigRegistry,
  runtime: 'openclaw' | 'hermes',
): HermesClawRuntimeAdapterOutput {
  const supportedSkillIds = new Set(
    registry.skills
      .filter((skill) => supportsRuntime(skill, runtime))
      .map((skill) => skill.id),
  );
  const enabledRules = registry.rules
    .filter((rule) => rule.enabled)
    .sort((left, right) => right.priority - left.priority);

  return {
    skills: registry.skills
      .filter((skill) => supportedSkillIds.has(skill.id))
      .map((skill) => runtime === 'openclaw'
        ? {
            id: skill.id,
            name: skill.name ?? skill.id,
            description: skill.description,
            plugin: adaptEntry(skill.entry),
            permissions: skill.permissions ?? [],
            source: skill.source ?? 'hermesclaw-shared-config',
            schemaVersion: skill.schemaVersion ?? 1,
          }
        : {
            id: skill.id,
            displayName: skill.name ?? skill.id,
            description: skill.description,
            entry: adaptEntry(skill.entry),
            permissions: skill.permissions ?? [],
            source: skill.source ?? 'hermesclaw-shared-config',
            schemaVersion: skill.schemaVersion ?? 1,
          }),
    agents: registry.agents
      .filter((agent) => agent.runtimePreference === runtime || agent.runtimePreference === 'auto' || !agent.runtimePreference)
      .map((agent) => ({
        id: agent.id,
        name: agent.name ?? agent.id,
        providerRef: agent.providerRef ?? agent.provider,
        model: agent.model,
        systemPrompt: agent.systemPrompt,
        skills: (agent.skills ?? []).filter((skillId) => supportedSkillIds.has(skillId)),
        rules: (agent.rules ?? []).filter((ruleId) => enabledRules.some((rule) => rule.id === ruleId)),
        tools: agent.tools ?? [],
        runtime,
      })),
    rules: enabledRules.map((rule) => runtime === 'openclaw'
      ? {
          id: rule.id,
          scope: rule.scope,
          priority: rule.priority,
          instruction: rule.content ?? '',
        }
      : {
          id: rule.id,
          scope: rule.scope,
          priority: rule.priority,
          role: rule.scope === 'global' ? 'system' : 'developer',
          content: rule.content ?? '',
        }),
    providers: (registry.providers ?? []).map((provider) => ({
      id: provider.id,
      provider: provider.provider,
      configRef: provider.configRef,
      baseUrlRef: provider.baseUrlRef,
      runtime,
    })),
    tools: (registry.tools ?? [])
      .filter((tool) => runtimeSupportIncludes(tool.runtimeSupport, runtime))
      .map((tool) => ({
        id: tool.id,
        command: tool.command,
        permissions: tool.permissions ?? [],
        runtime,
      })),
    hooks: (registry.hooks ?? [])
      .filter((hook) => runtimeSupportIncludes(hook.runtimeSupport, runtime))
      .map((hook) => ({
        id: hook.id,
        event: hook.event,
        command: hook.command,
        runtime,
      })),
  };
}

function buildSharedConfigAdapters(registry: HermesClawSharedConfigRegistry): HermesClawSharedConfigAdapterBundle {
  return {
    openclaw: adaptSharedConfigForRuntime(registry, 'openclaw'),
    hermes: adaptSharedConfigForRuntime(registry, 'hermes'),
  };
}

function normalizeManifest(value: HermesClawRuntimeManifest): HermesClawRuntimeManifest {
  return {
    schemaVersion: MANIFEST_SCHEMA_VERSION,
    activeChannel: normalizeChannel(value.activeChannel),
    channels: value.channels && typeof value.channels === 'object' ? value.channels : {},
    rollbackStack: Array.isArray(value.rollbackStack) ? value.rollbackStack : [],
  };
}

function normalizeActiveRuntimesState(value: HermesClawActiveRuntimesState): HermesClawActiveRuntimesState {
  return {
    schemaVersion: 1,
    runtimes: value.runtimes && typeof value.runtimes === 'object' ? value.runtimes : {},
  };
}

function normalizeCompatibilityMatrix(value: HermesClawCompatibilityMatrix): HermesClawCompatibilityMatrix {
  const hermesVersions = Array.isArray(value.hermes?.versions) ? value.hermes.versions : [];
  const openClawVersions = Array.isArray(value.openclaw?.versions) ? value.openclaw.versions : [];
  return {
    schemaVersion: 1,
    bridgeProtocol: typeof value.bridgeProtocol === 'string' ? value.bridgeProtocol : undefined,
    hermes: {
      manifestUrl: typeof value.hermes?.manifestUrl === 'string' ? value.hermes.manifestUrl : undefined,
      latestVersion: typeof value.hermes?.latestVersion === 'string' ? value.hermes.latestVersion : undefined,
      trustedSignatures: Array.isArray(value.hermes?.trustedSignatures) ? value.hermes.trustedSignatures.filter((signature) => typeof signature === 'string') : undefined,
      versions: hermesVersions,
    },
    openclaw: {
      manifestUrl: typeof value.openclaw?.manifestUrl === 'string' ? value.openclaw.manifestUrl : undefined,
      latestVersion: typeof value.openclaw?.latestVersion === 'string' ? value.openclaw.latestVersion : undefined,
      trustedSignatures: Array.isArray(value.openclaw?.trustedSignatures) ? value.openclaw.trustedSignatures.filter((signature) => typeof signature === 'string') : undefined,
      versions: openClawVersions,
    },
    updatedAt: typeof value.updatedAt === 'number' ? value.updatedAt : undefined,
  };
}

function normalizeInstallHistory(value: HermesClawInstallHistory): HermesClawInstallHistory {
  return {
    schemaVersion: 1,
    entries: Array.isArray(value.entries) ? value.entries : [],
  };
}

export function getHermesClawActiveRuntimes(): HermesClawActiveRuntimesState {
  const layout = ensureHermesClawRuntimeLayout();
  const state = normalizeActiveRuntimesState(readJsonFile(layout.activeRuntimesPath, defaultActiveRuntimesState()));
  if (!existsSync(layout.activeRuntimesPath)) {
    writeJsonFile(layout.activeRuntimesPath, state);
  }
  return state;
}

export function saveHermesClawActiveRuntimes(state: HermesClawActiveRuntimesState): HermesClawActiveRuntimesState {
  const layout = ensureHermesClawRuntimeLayout();
  const normalized = normalizeActiveRuntimesState(state);
  writeJsonFile(layout.activeRuntimesPath, normalized);
  return normalized;
}

export function getHermesClawCompatibilityMatrix(): HermesClawCompatibilityMatrix {
  const layout = ensureHermesClawRuntimeLayout();
  const matrix = normalizeCompatibilityMatrix(readJsonFile(layout.compatibilityMatrixPath, defaultCompatibilityMatrix()));
  if (!existsSync(layout.compatibilityMatrixPath)) {
    writeJsonFile(layout.compatibilityMatrixPath, matrix);
  }
  return matrix;
}

export function saveHermesClawCompatibilityMatrix(matrix: HermesClawCompatibilityMatrix): HermesClawCompatibilityMatrix {
  const layout = ensureHermesClawRuntimeLayout();
  const normalized = normalizeCompatibilityMatrix(matrix);
  writeJsonFile(layout.compatibilityMatrixPath, normalized);
  return normalized;
}

export function getHermesClawInstallHistory(): HermesClawInstallHistory {
  const layout = ensureHermesClawRuntimeLayout();
  const history = normalizeInstallHistory(readJsonFile(layout.installHistoryPath, defaultInstallHistory()));
  if (!existsSync(layout.installHistoryPath)) {
    writeJsonFile(layout.installHistoryPath, history);
  }
  return history;
}

function appendHermesClawInstallHistory(entry: Omit<HermesClawInstallHistoryEntry, 'id' | 'createdAt'>): HermesClawInstallHistory {
  const layout = ensureHermesClawRuntimeLayout();
  const history = getHermesClawInstallHistory();
  history.entries.push({
    ...entry,
    id: `${entry.action}-${entry.runtime}-${Date.now()}`,
    createdAt: now(),
  });
  writeJsonFile(layout.installHistoryPath, history);
  return history;
}

export function getHermesClawManifest(): HermesClawRuntimeManifest {
  const layout = ensureHermesClawRuntimeLayout();
  const manifest = normalizeManifest(readJsonFile(layout.manifestPath, defaultManifest()));
  if (!existsSync(layout.manifestPath)) {
    writeJsonFile(layout.manifestPath, manifest);
  }
  return manifest;
}

export function saveHermesClawManifest(manifest: HermesClawRuntimeManifest): HermesClawRuntimeManifest {
  const layout = ensureHermesClawRuntimeLayout();
  const normalized = normalizeManifest(manifest);
  writeJsonFile(layout.manifestPath, normalized);
  return normalized;
}

export async function getHermesClawLocalStatus(gatewayManager?: GatewayManager): Promise<HermesClawLocalStatus> {
  const layout = ensureHermesClawRuntimeLayout();
  const settings = await getAllSettings();
  const installStatus = getHermesInstallStatus({
    windowsHermesPreferredMode: settings.runtime.windowsHermesPreferredMode,
    windowsHermesNativePath: settings.runtime.windowsHermesNativePath,
    windowsHermesWslDistro: settings.runtime.windowsHermesWslDistro,
    installedKinds: settings.runtime.installedKinds,
  });
  const bridge = await new HermesOpenClawBridge(gatewayManager).getStatus();
  return {
    layout,
    manifest: getHermesClawManifest(),
    runtimeState: getHermesClawActiveRuntimes(),
    compatibilityMatrix: getHermesClawCompatibilityMatrix(),
    installHistory: getHermesClawInstallHistory(),
    installStatus,
    bridge,
  };
}

function currentHermesVersion(
  manifest: HermesClawRuntimeManifest,
  activeRuntimes: HermesClawActiveRuntimesState,
  channel: HermesClawVersionChannel,
): string | undefined {
  return activeRuntimes.runtimes.hermes?.version ?? manifest.channels[channel]?.version;
}

function latestHermesVersion(
  matrix: HermesClawCompatibilityMatrix,
  channel: HermesClawVersionChannel,
): string | undefined {
  const channelVersions = matrix.hermes.versions
    .filter((version) => !version.channel || version.channel === channel)
    .map((version) => version.version)
    .filter(Boolean);
  return matrix.hermes.latestVersion ?? channelVersions.at(-1);
}

function currentOpenClawVersion(
  activeRuntimes: HermesClawActiveRuntimesState,
): string | undefined {
  return activeRuntimes.runtimes.openclaw?.version;
}

function latestOpenClawVersion(
  matrix: HermesClawCompatibilityMatrix,
  channel: HermesClawVersionChannel,
): string | undefined {
  const channelVersions = (matrix.openclaw?.versions ?? [])
    .filter((version) => !version.channel || version.channel === channel)
    .map((version) => version.version)
    .filter(Boolean);
  return matrix.openclaw?.latestVersion ?? channelVersions.at(-1);
}

function findHermesVersion(
  matrix: HermesClawCompatibilityMatrix,
  channel: HermesClawVersionChannel,
  version?: string,
): HermesClawCompatibleVersion | undefined {
  const targetVersion = version ?? latestHermesVersion(matrix, channel);
  return matrix.hermes.versions.find((candidate) => candidate.version === targetVersion && (!candidate.channel || candidate.channel === channel));
}

function findOpenClawVersion(
  matrix: HermesClawCompatibilityMatrix,
  channel: HermesClawVersionChannel,
  version?: string,
): HermesClawCompatibleVersion | undefined {
  const targetVersion = version ?? latestOpenClawVersion(matrix, channel);
  return (matrix.openclaw?.versions ?? []).find((candidate) => candidate.version === targetVersion && (!candidate.channel || candidate.channel === channel));
}

function updateManifestUrl(matrix: HermesClawCompatibilityMatrix): string | undefined {
  return matrix.hermes.manifestUrl ?? process.env.HERMESCLAW_UPDATE_MANIFEST_URL;
}

async function fetchRemoteCompatibilityMatrix(matrix: HermesClawCompatibilityMatrix): Promise<HermesClawCompatibilityMatrix> {
  const manifestUrl = updateManifestUrl(matrix);
  if (!manifestUrl) {
    return matrix;
  }

  const response = await proxyAwareFetch(manifestUrl, { method: 'GET' });
  if (!response.ok) {
    throw new Error(`Failed to fetch HermesClaw update manifest: HTTP ${response.status}`);
  }
  const remote = normalizeCompatibilityMatrix(await response.json() as HermesClawCompatibilityMatrix);
  return saveHermesClawCompatibilityMatrix({
    ...remote,
    hermes: {
      ...remote.hermes,
      manifestUrl,
      trustedSignatures: matrix.hermes.trustedSignatures ?? remote.hermes.trustedSignatures,
    },
    openclaw: {
      ...(remote.openclaw ?? { versions: [] }),
      trustedSignatures: matrix.openclaw?.trustedSignatures ?? remote.openclaw?.trustedSignatures,
    },
    updatedAt: now(),
  });
}

function sha256Hex(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

function trustedSignatureFor(version: HermesClawCompatibleVersion, matrix: HermesClawCompatibilityMatrix): boolean {
  const trustedSignatures = matrix.hermes.trustedSignatures ?? [];
  return Boolean(version.signature && trustedSignatures.includes(version.signature));
}

function trustedOpenClawSignatureFor(version: HermesClawCompatibleVersion, matrix: HermesClawCompatibilityMatrix): boolean {
  const trustedSignatures = matrix.openclaw?.trustedSignatures ?? [];
  return Boolean(version.signature && trustedSignatures.includes(version.signature));
}

async function downloadAndVerifyHermesRuntime(
  version: HermesClawCompatibleVersion,
  matrix: HermesClawCompatibilityMatrix,
  runtimeDir: string,
): Promise<void> {
  if (!version.downloadUrl) {
    writeDefaultRuntimeDescriptor(runtimeDir, version.version);
    return;
  }

  if (!trustedSignatureFor(version, matrix)) {
    throw new Error(`HermesClaw update ${version.version} is missing a trusted signature`);
  }

  const response = await proxyAwareFetch(version.downloadUrl, { method: 'GET' });
  if (!response.ok) {
    throw new Error(`Failed to download HermesClaw runtime ${version.version}: HTTP ${response.status}`);
  }
  const payload = await response.text();
  if (version.checksum && sha256Hex(payload) !== version.checksum) {
    throw new Error(`Checksum mismatch for HermesClaw runtime ${version.version}`);
  }

  writeFileSync(join(runtimeDir, 'downloaded-runtime.json'), payload, 'utf-8');
  try {
    const parsed = JSON.parse(payload) as { runtimeDescriptor?: unknown; entry?: unknown };
    const descriptor = parsed.runtimeDescriptor ?? parsed;
    writeJsonFile(join(runtimeDir, 'runtime.json'), descriptor);
  } catch {
    writeDefaultRuntimeDescriptor(runtimeDir, version.version);
  }
}

async function downloadAndVerifyOpenClawRuntime(
  version: HermesClawCompatibleVersion,
  matrix: HermesClawCompatibilityMatrix,
  runtimeDir: string,
): Promise<void> {
  if (!version.downloadUrl) {
    writeDefaultOpenClawRuntimeDescriptor(runtimeDir, version.version);
    return;
  }

  if (!trustedOpenClawSignatureFor(version, matrix)) {
    throw new Error(`OpenClaw update ${version.version} is missing a trusted signature`);
  }

  const response = await proxyAwareFetch(version.downloadUrl, { method: 'GET' });
  if (!response.ok) {
    throw new Error(`Failed to download OpenClaw runtime ${version.version}: HTTP ${response.status}`);
  }
  const payload = await response.text();
  if (version.checksum && sha256Hex(payload) !== version.checksum) {
    throw new Error(`Checksum mismatch for OpenClaw runtime ${version.version}`);
  }

  writeFileSync(join(runtimeDir, 'downloaded-runtime.json'), payload, 'utf-8');
  try {
    const parsed = JSON.parse(payload) as { runtimeDescriptor?: unknown };
    writeJsonFile(join(runtimeDir, 'runtime.json'), parsed.runtimeDescriptor ?? parsed);
  } catch {
    writeDefaultOpenClawRuntimeDescriptor(runtimeDir, version.version);
  }
}

function writeDefaultRuntimeDescriptor(runtimeDir: string, version: string): void {
  const descriptorPath = join(runtimeDir, 'runtime.json');
  if (existsSync(descriptorPath)) {
    return;
  }
  writeJsonFile(descriptorPath, {
    schemaVersion: 1,
    version,
    entry: {
      type: 'python',
      command: 'python',
      args: ['-m', 'hermes.gateway.run', '--port', '{port}'],
    },
    health: {
      url: getHermesEndpoint(),
    },
  });
}

function writeDefaultOpenClawRuntimeDescriptor(runtimeDir: string, version: string): void {
  // Idempotent rewriter: always writes the current default (schemaVersion: 2)
  // so stale on-disk descriptors get refreshed whenever Apply Update or
  // rollback flows reach this writer. Read-side migration in paths.ts
  // (readOpenClawRuntimeDescriptor) covers the cold-start case where this
  // writer is not invoked.
  writeJsonFile(join(runtimeDir, 'runtime.json'), {
    schemaVersion: 2,
    version,
    entry: {
      type: 'node',
      command: 'node',
      args: ['dist/entry.js'],
    },
    health: {
      url: 'http://127.0.0.1:18789/health',
    },
  });
}

function buildHermesRecord(input: {
  channel: HermesClawVersionChannel;
  version: string;
  runtimeDir: string;
  status: HermesClawRuntimeStateStatus;
  previous?: HermesClawActiveRuntimeRecord;
  lastError?: string;
}): HermesClawActiveRuntimeRecord {
  return {
    runtime: 'hermes',
    channel: input.channel,
    version: input.version,
    runtimeDir: input.runtimeDir,
    status: input.status,
    lastKnownGoodVersion: input.status === 'ready'
      ? input.version
      : input.previous?.lastKnownGoodVersion ?? input.previous?.version,
    lastKnownGoodRuntimeDir: input.status === 'ready'
      ? input.runtimeDir
      : input.previous?.lastKnownGoodRuntimeDir ?? input.previous?.runtimeDir,
    updatedAt: now(),
    lastError: input.lastError,
  };
}

function buildOpenClawRecord(input: {
  channel: HermesClawVersionChannel;
  version: string;
  runtimeDir: string;
  status: HermesClawRuntimeStateStatus;
  previous?: HermesClawActiveRuntimeRecord;
  lastError?: string;
}): HermesClawActiveRuntimeRecord {
  return {
    runtime: 'openclaw',
    channel: input.channel,
    version: input.version,
    runtimeDir: input.runtimeDir,
    status: input.status,
    lastKnownGoodVersion: input.status === 'ready'
      ? input.version
      : input.previous?.lastKnownGoodVersion ?? input.previous?.version,
    lastKnownGoodRuntimeDir: input.status === 'ready'
      ? input.runtimeDir
      : input.previous?.lastKnownGoodRuntimeDir ?? input.previous?.runtimeDir,
    updatedAt: now(),
    lastError: input.lastError,
  };
}

function versionParts(version: string): number[] {
  return version.split('.').map((part) => Number.parseInt(part, 10)).map((part) => Number.isFinite(part) ? part : 0);
}

function compareVersions(left: string, right: string): number {
  const leftParts = versionParts(left);
  const rightParts = versionParts(right);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index] ?? 0;
    const rightPart = rightParts[index] ?? 0;
    if (leftPart !== rightPart) {
      return leftPart > rightPart ? 1 : -1;
    }
  }
  return 0;
}

function satisfiesVersionRange(version: string | undefined, range: string): boolean {
  if (!version) {
    return false;
  }
  const trimmed = range.trim();
  if (trimmed.startsWith('>=')) {
    return compareVersions(version, trimmed.slice(2).trim()) >= 0;
  }
  if (trimmed.startsWith('>')) {
    return compareVersions(version, trimmed.slice(1).trim()) > 0;
  }
  if (trimmed.startsWith('<=')) {
    return compareVersions(version, trimmed.slice(2).trim()) <= 0;
  }
  if (trimmed.startsWith('<')) {
    return compareVersions(version, trimmed.slice(1).trim()) < 0;
  }
  if (trimmed.startsWith('=')) {
    return compareVersions(version, trimmed.slice(1).trim()) === 0;
  }
  return compareVersions(version, trimmed) === 0;
}

function assertHermesCandidateCompatible(
  candidate: HermesClawCompatibleVersion,
  matrix: HermesClawCompatibilityMatrix,
  activeRuntimes: HermesClawActiveRuntimesState,
): void {
  if (candidate.bridgeProtocol && matrix.bridgeProtocol && candidate.bridgeProtocol !== matrix.bridgeProtocol) {
    throw new Error(`Hermes runtime ${candidate.version} requires bridge protocol ${candidate.bridgeProtocol}, but HermesClaw provides ${matrix.bridgeProtocol}`);
  }
  if (candidate.compatibleOpenClaw && !satisfiesVersionRange(activeRuntimes.runtimes.openclaw?.version, candidate.compatibleOpenClaw)) {
    throw new Error(`Hermes runtime ${candidate.version} requires OpenClaw ${candidate.compatibleOpenClaw}, but active OpenClaw is ${activeRuntimes.runtimes.openclaw?.version ?? 'not installed'}`);
  }
}

async function restartAndCheckHermes(timeoutMs = 30_000): Promise<{ ok: boolean; error?: string }> {
  const manager = getHermesStandaloneManager();
  await manager.restart();
  const deadline = Date.now() + timeoutMs;
  let lastError: string | undefined;
  while (Date.now() < deadline) {
    const health = await manager.checkHealth();
    if (health.ok) return { ok: true };
    lastError = health.error;
    await new Promise<void>((resolve) => setTimeout(resolve, 250));
  }
  return { ok: false, error: lastError ?? 'Hermes health check failed after runtime update' };
}

function checkPython(): HermesClawDoctorCheck {
  for (const command of ['python', 'python3', 'py']) {
    try {
      const version = execFileSync(command, ['--version'], { stdio: ['ignore', 'pipe', 'pipe'] }).toString().trim();
      return { id: 'python', status: 'pass', label: 'Python runtime', detail: version || command };
    } catch {
      // Try the next common executable name.
    }
  }
  return { id: 'python', status: 'warn', label: 'Python runtime', detail: 'Python executable was not found on PATH' };
}

function checkHermesExecutable(status: HermesClawLocalStatus): HermesClawDoctorCheck {
  const activeRuntime = status.runtimeState.runtimes.hermes;
  const descriptorPath = activeRuntime?.runtimeDir ? join(activeRuntime.runtimeDir, 'runtime.json') : undefined;
  if (descriptorPath && existsSync(descriptorPath)) {
    return { id: 'executable', status: 'pass', label: 'Hermes executable descriptor', detail: descriptorPath };
  }
  if (status.installStatus.installPath && existsSync(status.installStatus.installPath)) {
    return { id: 'executable', status: 'pass', label: 'Hermes executable descriptor', detail: status.installStatus.installPath };
  }
  return {
    id: 'executable',
    status: 'fail',
    label: 'Hermes executable descriptor',
    detail: descriptorPath ?? status.installStatus.installPath ?? 'No active Hermes runtime descriptor found',
    repairAction: 'Run HermesClaw runtime repair or apply a known-good Hermes runtime update.',
  };
}

async function checkHermesPort(endpoint: string): Promise<HermesClawDoctorCheck> {
  if (!endpoint.startsWith('http://127.0.0.1:')) {
    return {
      id: 'port',
      status: 'warn',
      label: 'Hermes endpoint policy',
      detail: endpoint,
      repairAction: 'Configure Hermes to bind to the local loopback endpoint managed by Electron Main.',
    };
  }

  try {
    const response = await proxyAwareFetch(`${endpoint.replace(/\/$/, '')}/health`, { method: 'GET' });
    return {
      id: 'port',
      status: response.ok ? 'pass' : 'warn',
      label: 'Hermes port health',
      detail: response.ok ? endpoint : `${endpoint} returned HTTP ${response.status}`,
      repairAction: response.ok ? undefined : 'Restart Hermes from Settings or run runtime repair.',
    };
  } catch (error) {
    return {
      id: 'port',
      status: 'warn',
      label: 'Hermes port health',
      detail: error instanceof Error ? error.message : String(error),
      repairAction: 'Start Hermes from Settings or check whether another process owns the configured port.',
    };
  }
}

function buildSyncStatusCheck(status: HermesClawLocalStatus): HermesClawDoctorCheck {
  const issues = validateSharedConfigRegistry(getHermesClawSharedConfigSnapshot(status.layout));
  const conflicts = detectSharedConfigConflicts(getHermesClawSharedConfigSnapshot(status.layout));
  const adapterPaths = [
    join(status.layout.sharedConfigDir, 'openclaw-adapter.json'),
    join(status.layout.sharedConfigDir, 'hermes-adapter.json'),
  ];
  const adaptersReady = adapterPaths.every((path) => existsSync(path));
  if (issues.some((issue) => issue.severity === 'error') || conflicts.length > 0) {
    return {
      id: 'sync-status',
      status: 'fail',
      label: 'Shared config sync status',
      detail: [...issues.filter((issue) => issue.severity === 'error').map((issue) => issue.message), ...conflicts.map((conflict) => conflict.message)].join('; '),
      repairAction: 'Resolve shared config validation errors and conflicts, then run dry-run sync again.',
    };
  }
  return {
    id: 'sync-status',
    status: adaptersReady ? 'pass' : 'warn',
    label: 'Shared config sync status',
    detail: adaptersReady ? 'Runtime adapter files are present' : 'Runtime adapter files have not been generated yet',
    repairAction: adaptersReady ? undefined : 'Run HermesClaw dry-run sync, then apply sync when validation is clean.',
  };
}

function getHermesClawSharedConfigSnapshot(layout: HermesClawRuntimeLayout): HermesClawSharedConfigRegistry {
  return readJsonFile(getSharedConfigRegistryPath(layout), defaultSharedConfigRegistry());
}

function buildRuntimeStateCheck(status: HermesClawLocalStatus): HermesClawDoctorCheck {
  const runtimeOrder: Array<{ kind: HermesClawRuntimeKind; label: string }> = [
    { kind: 'openclaw', label: 'OpenClaw' },
    { kind: 'hermes', label: 'Hermes' },
  ];
  const activeRecords = runtimeOrder.map(({ kind, label }) => ({ kind, label, record: status.runtimeState.runtimes[kind] }));
  const missing = activeRecords.filter(({ record }) => !record);
  const failed = activeRecords.filter(({ record }) => record?.status === 'rollback-required' || record?.status === 'error');

  if (failed.length > 0) {
    return {
      id: 'runtime-state',
      status: 'fail',
      label: 'Runtime state',
      detail: failed
        .map(({ label, record }) => `${label} ${record?.version} is ${record?.status}${record?.lastError ? `: ${record.lastError}` : ''}`)
        .join('; '),
      repairAction: failed
        .map(({ label }) => `Run rollback or repair the active ${label} runtime before starting it again.`)
        .join(' '),
    };
  }

  if (missing.length > 0) {
    return {
      id: 'runtime-state',
      status: 'warn',
      label: 'Runtime state',
      detail: missing.map(({ label }) => `No active ${label} runtime is recorded`).join('; '),
      repairAction: `Apply or repair ${missing.map(({ label }) => label).join(' and ')} runtime state to create active-runtimes.json.`,
    };
  }

  return {
    id: 'runtime-state',
    status: 'pass',
    label: 'Runtime state',
    detail: activeRecords
      .map(({ label, record }) => `${label} ${record?.version} is ${record?.status}`)
      .join('; '),
  };
}

function buildCompatibilityCheck(status: HermesClawLocalStatus): HermesClawDoctorCheck {
  const channel = status.manifest.activeChannel;
  const latestOpenClaw = latestOpenClawVersion(status.compatibilityMatrix, channel);
  const latestHermes = latestHermesVersion(status.compatibilityMatrix, channel);
  const missing = [
    latestOpenClaw ? undefined : `Missing latest OpenClaw metadata for ${channel}`,
    latestHermes ? undefined : `Missing latest Hermes metadata for ${channel}`,
  ].filter((detail): detail is string => Boolean(detail));

  if (missing.length > 0) {
    return {
      id: 'compatibility',
      status: 'warn',
      label: 'Compatibility matrix',
      detail: missing.join('; '),
      repairAction: 'Refresh or repair compatibility-matrix.json before applying updates.',
    };
  }

  return {
    id: 'compatibility',
    status: 'pass',
    label: 'Compatibility matrix',
    detail: `Latest OpenClaw ${latestOpenClaw}; Latest Hermes ${latestHermes}`,
  };
}

function writeHermesClawDoctorReport(layout: HermesClawRuntimeLayout, result: Omit<HermesClawDoctorResult, 'reportPath'>): string {
  const reportPath = join(layout.logsDir, `hermesclaw-doctor-${result.checkedAt}.json`);
  writeJsonFile(reportPath, result);
  return reportPath;
}

export async function runHermesClawDoctor(gatewayManager?: GatewayManager): Promise<HermesClawDoctorResult> {
  const checkedAt = Date.now();
  const status = await getHermesClawLocalStatus(gatewayManager);
  const endpoint = getHermesEndpoint();
  const checks: HermesClawDoctorCheck[] = [
    {
      id: 'runtime-directories',
      status: existsSync(status.layout.rootDir)
        && existsSync(status.layout.userRuntimesDir)
        && existsSync(status.layout.sharedConfigDir)
        ? 'pass'
        : 'fail',
      label: 'Runtime directories',
      detail: status.layout.rootDir,
    },
    {
      id: 'manifest',
      status: status.manifest.schemaVersion === MANIFEST_SCHEMA_VERSION ? 'pass' : 'fail',
      label: 'Runtime manifest',
      detail: status.layout.manifestPath,
    },
    {
      id: 'install-status',
      status: status.installStatus.installed ? 'pass' : 'warn',
      label: 'Hermes installation',
      detail: status.installStatus.installPath ?? status.installStatus.error,
    },
    {
      id: 'port',
      status: endpoint.startsWith('http://127.0.0.1:') ? 'pass' : 'warn',
      label: 'Hermes endpoint policy',
      detail: endpoint,
    },
    {
      id: 'config',
      status: existsSync(status.layout.sharedConfigDir) ? 'pass' : 'fail',
      label: 'Shared config directory',
      detail: status.layout.sharedConfigDir,
    },
    checkPython(),
    {
      id: 'bridge',
      status: status.bridge.enabled
        ? (status.bridge.attached ? 'pass' : 'warn')
        : 'pass',
      label: 'Hermes OpenClaw bridge',
      detail: status.bridge.reasonCode ?? status.bridge.error,
    },
    checkHermesExecutable(status),
    buildRuntimeStateCheck(status),
    buildCompatibilityCheck(status),
    buildSyncStatusCheck(status),
    {
      id: 'repair',
      status: 'pass',
      label: 'Repair plan export',
      detail: status.layout.logsDir,
    },
  ];
  const portHealth = await checkHermesPort(endpoint);
  checks.splice(checks.findIndex((check) => check.id === 'port'), 1, portHealth);
  const repairPlan = checks
    .map((check) => check.repairAction)
    .filter((action): action is string => Boolean(action));
  const resultWithoutPath = {
    ok: checks.every((check) => check.status !== 'fail'),
    checkedAt,
    checks,
    repairPlan,
  };
  const reportPath = writeHermesClawDoctorReport(status.layout, resultWithoutPath);

  return {
    ...resultWithoutPath,
    reportPath,
  };
}

export async function checkHermesClawUpdate(channelInput?: unknown): Promise<{
  channel: HermesClawVersionChannel;
  currentVersion?: string;
  latestVersion?: string;
  updateAvailable: boolean;
  releaseNotes?: string;
  risk?: 'low' | 'medium' | 'high';
}> {
  const channel = normalizeChannel(channelInput);
  const manifest = getHermesClawManifest();
  const activeRuntimes = getHermesClawActiveRuntimes();
  const matrix = await fetchRemoteCompatibilityMatrix(getHermesClawCompatibilityMatrix());
  const currentVersion = currentHermesVersion(manifest, activeRuntimes, channel);
  const latestVersion = latestHermesVersion(matrix, channel) ?? currentVersion;
  const latest = findHermesVersion(matrix, channel, latestVersion);
  appendHermesClawInstallHistory({
    runtime: 'hermes',
    channel,
    version: latestVersion,
    action: 'check',
    status: 'success',
  });
  return {
    channel,
    currentVersion,
    latestVersion,
    updateAvailable: Boolean(latestVersion && latestVersion !== currentVersion),
    releaseNotes: latest?.releaseNotes,
    risk: latest?.risk,
  };
}

export async function checkOpenClawRuntimeUpdate(channelInput?: unknown): Promise<{
  supported: true;
  runtime: 'openclaw';
  action: 'check-update';
  channel: HermesClawVersionChannel;
  currentVersion?: string;
  latestVersion?: string;
  updateAvailable: boolean;
  releaseNotes?: string;
  risk?: 'low' | 'medium' | 'high';
}> {
  const channel = normalizeChannel(channelInput);
  const activeRuntimes = getHermesClawActiveRuntimes();
  const matrix = await fetchRemoteCompatibilityMatrix(getHermesClawCompatibilityMatrix());
  const currentVersion = currentOpenClawVersion(activeRuntimes);
  const latestVersion = latestOpenClawVersion(matrix, channel) ?? currentVersion;
  const latest = findOpenClawVersion(matrix, channel, latestVersion);
  appendHermesClawInstallHistory({
    runtime: 'openclaw',
    channel,
    version: latestVersion,
    action: 'check',
    status: 'success',
  });
  return {
    supported: true,
    runtime: 'openclaw',
    action: 'check-update',
    channel,
    currentVersion,
    latestVersion,
    updateAvailable: Boolean(latestVersion && latestVersion !== currentVersion),
    releaseNotes: latest?.releaseNotes,
    risk: latest?.risk,
  };
}

export async function applyHermesClawUpdate(input: { channel?: unknown; version?: unknown }): Promise<{
  success: boolean;
  channel: HermesClawVersionChannel;
  version: string;
  backupId: string;
  rolledBack?: boolean;
  restoredVersion?: string;
  rollbackRequired?: boolean;
  error?: string;
}> {
  const layout = ensureHermesClawRuntimeLayout();
  const manifest = getHermesClawManifest();
  const activeRuntimes = getHermesClawActiveRuntimes();
  const matrix = await fetchRemoteCompatibilityMatrix(getHermesClawCompatibilityMatrix());
  const channel = normalizeChannel(input.channel);
  const previous = manifest.channels[channel];
  const previousActive = activeRuntimes.runtimes.hermes;
  const version = typeof input.version === 'string' && input.version.trim().length > 0
    ? input.version.trim()
    : latestHermesVersion(matrix, channel) ?? previousActive?.version ?? previous?.version ?? 'local';
  const candidate = findHermesVersion(matrix, channel, version) ?? { version, channel };
  assertHermesCandidateCompatible(candidate, matrix, activeRuntimes);
  const backupId = `${channel}-${Date.now()}`;
  const runtimeDir = join(layout.userRuntimesDir, 'hermes', version);
  ensureDir(runtimeDir);
  ensureDir(join(layout.backupsDir, backupId));
  await downloadAndVerifyHermesRuntime(candidate, matrix, runtimeDir);

  manifest.rollbackStack.push({
    id: backupId,
    runtime: 'hermes',
    channel,
    version: previous?.version,
    runtimeDir: previous?.runtimeDir,
    createdAt: Date.now(),
  });
  manifest.activeChannel = channel;
  manifest.channels[channel] = {
    version,
    runtimeDir,
    updatedAt: Date.now(),
    backupId,
  };
  saveHermesClawManifest(manifest);
  activeRuntimes.runtimes.hermes = buildHermesRecord({
    channel,
    version,
    runtimeDir,
    status: 'updating',
    previous: previousActive,
  });
  saveHermesClawActiveRuntimes(activeRuntimes);

  const health = await restartAndCheckHermes();
  if (health.ok) {
    const readyState = getHermesClawActiveRuntimes();
    readyState.runtimes.hermes = buildHermesRecord({
      channel,
      version,
      runtimeDir,
      status: 'ready',
      previous: readyState.runtimes.hermes,
    });
    saveHermesClawActiveRuntimes(readyState);
    appendHermesClawInstallHistory({
      runtime: 'hermes',
      channel,
      version,
      action: 'apply',
      status: 'success',
      runtimeDir,
      backupId,
    });
    return { success: true, channel, version, backupId };
  }

  appendHermesClawInstallHistory({
    runtime: 'hermes',
    channel,
    version,
    action: 'failed-update',
    status: 'failure',
    runtimeDir,
    backupId,
    error: health.error,
  });

  const rollbackManifest = getHermesClawManifest();
  rollbackManifest.rollbackStack = rollbackManifest.rollbackStack.filter((entry) => entry.id !== backupId);
  if (previous?.version || previous?.runtimeDir) {
    rollbackManifest.channels[channel] = {
      version: previous?.version,
      runtimeDir: previous?.runtimeDir,
      updatedAt: now(),
      backupId,
    };
  } else {
    delete rollbackManifest.channels[channel];
  }
  rollbackManifest.activeChannel = channel;
  saveHermesClawManifest(rollbackManifest);

  const rollbackState = getHermesClawActiveRuntimes();
  if (previousActive) {
    rollbackState.runtimes.hermes = {
      ...previousActive,
      status: 'starting',
      updatedAt: now(),
      lastError: health.error,
    };
  } else {
    delete rollbackState.runtimes.hermes;
  }
  saveHermesClawActiveRuntimes(rollbackState);

  const rollbackHealth = previousActive ? await restartAndCheckHermes() : { ok: true };
  if (rollbackHealth.ok) {
    const restoredState = getHermesClawActiveRuntimes();
    if (previousActive) {
      restoredState.runtimes.hermes = {
        ...previousActive,
        status: 'ready',
        updatedAt: now(),
        lastError: undefined,
      };
      saveHermesClawActiveRuntimes(restoredState);
    }
    appendHermesClawInstallHistory({
      runtime: 'hermes',
      channel,
      version: previousActive?.version ?? previous?.version,
      action: 'auto-rollback',
      status: 'success',
      runtimeDir: previousActive?.runtimeDir ?? previous?.runtimeDir,
      backupId,
    });
    return {
      success: false,
      channel,
      version,
      backupId,
      rolledBack: true,
      restoredVersion: previousActive?.version ?? previous?.version,
      error: health.error,
    };
  }

  const failedRollbackState = getHermesClawActiveRuntimes();
  if (previousActive) {
    failedRollbackState.runtimes.hermes = {
      ...previousActive,
      status: 'rollback-required',
      updatedAt: now(),
      lastError: rollbackHealth.error,
    };
    saveHermesClawActiveRuntimes(failedRollbackState);
  }
  appendHermesClawInstallHistory({
    runtime: 'hermes',
    channel,
    version: previousActive?.version ?? previous?.version,
    action: 'auto-rollback',
    status: 'failure',
    runtimeDir: previousActive?.runtimeDir ?? previous?.runtimeDir,
    backupId,
    error: rollbackHealth.error,
  });
  return {
    success: false,
    channel,
    version,
    backupId,
    rolledBack: false,
    rollbackRequired: true,
    restoredVersion: previousActive?.version ?? previous?.version,
    error: rollbackHealth.error,
  };
}

export async function rollbackHermesClawRuntime(): Promise<{
  success: boolean;
  restoredVersion?: string;
  backupId?: string;
  error?: string;
}> {
  const manifest = getHermesClawManifest();
  const activeRuntimes = getHermesClawActiveRuntimes();
  const backup = manifest.rollbackStack.pop();
  if (!backup) {
    return { success: false, error: 'No HermesClaw runtime backup is available for rollback' };
  }

  if (backup.version || backup.runtimeDir) {
    manifest.channels[backup.channel] = {
      version: backup.version,
      runtimeDir: backup.runtimeDir,
      updatedAt: Date.now(),
      backupId: backup.id,
    };
  } else {
    delete manifest.channels[backup.channel];
  }
  manifest.activeChannel = backup.channel;
  saveHermesClawManifest(manifest);
  if (backup.version && backup.runtimeDir) {
    activeRuntimes.runtimes.hermes = buildHermesRecord({
      channel: backup.channel,
      version: backup.version,
      runtimeDir: backup.runtimeDir,
      status: 'starting',
      previous: activeRuntimes.runtimes.hermes,
    });
  } else {
    delete activeRuntimes.runtimes.hermes;
  }
  saveHermesClawActiveRuntimes(activeRuntimes);

  const health = backup.version && backup.runtimeDir ? await restartAndCheckHermes() : { ok: true };
  if (!health.ok) {
    const failedState = getHermesClawActiveRuntimes();
    if (failedState.runtimes.hermes) {
      failedState.runtimes.hermes = {
        ...failedState.runtimes.hermes,
        status: 'rollback-required',
        updatedAt: now(),
        lastError: health.error,
      };
      saveHermesClawActiveRuntimes(failedState);
    }
    appendHermesClawInstallHistory({
      runtime: 'hermes',
      channel: backup.channel,
      version: backup.version,
      action: 'rollback',
      status: 'failure',
      runtimeDir: backup.runtimeDir,
      backupId: backup.id,
      error: health.error,
    });
    return { success: false, restoredVersion: backup.version, backupId: backup.id, error: health.error };
  }

  const restoredState = getHermesClawActiveRuntimes();
  if (restoredState.runtimes.hermes) {
    restoredState.runtimes.hermes = {
      ...restoredState.runtimes.hermes,
      status: 'ready',
      updatedAt: now(),
      lastError: undefined,
    };
    saveHermesClawActiveRuntimes(restoredState);
  }
  appendHermesClawInstallHistory({
    runtime: 'hermes',
    channel: backup.channel,
    version: backup.version,
    action: 'rollback',
    status: 'success',
    runtimeDir: backup.runtimeDir,
    backupId: backup.id,
  });
  return { success: true, restoredVersion: backup.version, backupId: backup.id };
}

export async function applyOpenClawRuntimeUpdate(input: { channel?: unknown; version?: unknown }): Promise<{
  supported: true;
  success: boolean;
  runtime: 'openclaw';
  action: 'apply-update';
  channel: HermesClawVersionChannel;
  version: string;
  backupId: string;
  error?: string;
}> {
  const layout = ensureHermesClawRuntimeLayout();
  const manifest = getHermesClawManifest();
  const activeRuntimes = getHermesClawActiveRuntimes();
  const matrix = await fetchRemoteCompatibilityMatrix(getHermesClawCompatibilityMatrix());
  const channel = normalizeChannel(input.channel);
  const previousActive = activeRuntimes.runtimes.openclaw;
  const version = typeof input.version === 'string' && input.version.trim().length > 0
    ? input.version.trim()
    : latestOpenClawVersion(matrix, channel) ?? previousActive?.version ?? 'local';
  const candidate = findOpenClawVersion(matrix, channel, version) ?? { version, channel };
  const backupId = `openclaw-${channel}-${Date.now()}`;
  const runtimeDir = join(layout.userRuntimesDir, 'openclaw', version);
  ensureDir(runtimeDir);
  ensureDir(join(layout.backupsDir, backupId));
  await downloadAndVerifyOpenClawRuntime(candidate, matrix, runtimeDir);

  manifest.rollbackStack.push({
    id: backupId,
    runtime: 'openclaw',
    channel,
    version: previousActive?.version,
    runtimeDir: previousActive?.runtimeDir,
    createdAt: Date.now(),
  });
  saveHermesClawManifest(manifest);

  activeRuntimes.runtimes.openclaw = buildOpenClawRecord({
    channel,
    version,
    runtimeDir,
    status: 'ready',
    previous: previousActive,
  });
  saveHermesClawActiveRuntimes(activeRuntimes);
  appendHermesClawInstallHistory({
    runtime: 'openclaw',
    channel,
    version,
    action: 'apply',
    status: 'success',
    runtimeDir,
    backupId,
  });
  return { supported: true, success: true, runtime: 'openclaw', action: 'apply-update', channel, version, backupId };
}

export async function rollbackOpenClawRuntime(): Promise<{
  supported: true;
  success: boolean;
  runtime: 'openclaw';
  action: 'rollback';
  restoredVersion?: string;
  backupId?: string;
  error?: string;
}> {
  const manifest = getHermesClawManifest();
  const activeRuntimes = getHermesClawActiveRuntimes();
  const backupIndex = [...manifest.rollbackStack].reverse().findIndex((entry) => (entry.runtime ?? 'hermes') === 'openclaw');
  if (backupIndex < 0) {
    return { supported: true, success: false, runtime: 'openclaw', action: 'rollback', error: 'No OpenClaw runtime backup is available for rollback' };
  }
  const index = manifest.rollbackStack.length - 1 - backupIndex;
  const backup = manifest.rollbackStack[index];
  manifest.rollbackStack.splice(index, 1);
  saveHermesClawManifest(manifest);

  if (backup.version && backup.runtimeDir) {
    activeRuntimes.runtimes.openclaw = buildOpenClawRecord({
      channel: backup.channel,
      version: backup.version,
      runtimeDir: backup.runtimeDir,
      status: 'ready',
      previous: activeRuntimes.runtimes.openclaw,
    });
  } else {
    delete activeRuntimes.runtimes.openclaw;
  }
  saveHermesClawActiveRuntimes(activeRuntimes);
  appendHermesClawInstallHistory({
    runtime: 'openclaw',
    channel: backup.channel,
    version: backup.version,
    action: 'rollback',
    status: 'success',
    runtimeDir: backup.runtimeDir,
    backupId: backup.id,
  });
  return { supported: true, success: true, runtime: 'openclaw', action: 'rollback', restoredVersion: backup.version, backupId: backup.id };
}

export function getHermesClawLogsLocation(): HermesClawLogsLocation {
  const layout = ensureHermesClawRuntimeLayout();
  ensureDir(layout.logsDir);
  return { dir: layout.logsDir };
}

export async function repairHermesClawInstallation(gatewayManager?: GatewayManager): Promise<HermesClawRepairResult> {
  const layout = ensureHermesClawRuntimeLayout();
  const repaired: string[] = [];

  if (!existsSync(layout.manifestPath)) {
    writeJsonFile(layout.manifestPath, defaultManifest());
    repaired.push('runtime-manifest');
  }

  if (!existsSync(layout.activeRuntimesPath)) {
    writeJsonFile(layout.activeRuntimesPath, defaultActiveRuntimesState());
    repaired.push('active-runtimes');
  }

  if (!existsSync(layout.compatibilityMatrixPath)) {
    writeJsonFile(layout.compatibilityMatrixPath, defaultCompatibilityMatrix());
    repaired.push('compatibility-matrix');
  }

  if (!existsSync(layout.installHistoryPath)) {
    writeJsonFile(layout.installHistoryPath, defaultInstallHistory());
    repaired.push('install-history');
  }

  const registryPath = getSharedConfigRegistryPath(layout);
  if (!existsSync(registryPath)) {
    writeJsonFile(registryPath, { ...defaultSharedConfigRegistry(), updatedAt: now() });
    repaired.push('shared-config-registry');
  }

  const syncResult = await syncHermesClawSharedConfig({ dryRun: false, scope: 'repair' });
  for (const change of syncResult.changes) {
    repaired.push(`shared-config:${change.path}`);
  }

  ensureDir(layout.logsDir);
  repaired.push('logs-directory');

  const doctor = await runHermesClawDoctor(gatewayManager);
  return {
    success: doctor.ok,
    repaired: [...new Set(repaired)],
    doctor,
  };
}

export async function getHermesClawSharedConfig(): Promise<HermesClawSharedConfigRegistry> {
  const layout = ensureHermesClawRuntimeLayout();
  const path = getSharedConfigRegistryPath(layout);
  const registry = readJsonFile(path, defaultSharedConfigRegistry());
  if (!existsSync(path)) {
    writeJsonFile(path, registry);
  }
  return registry;
}

export async function syncHermesClawSharedConfig(input: { dryRun?: boolean; scope?: unknown } = {}): Promise<HermesClawSharedConfigSyncResult> {
  const dryRun = input.dryRun !== false;
  const scope = normalizeSharedConfigSyncScope(input.scope);
  const layout = ensureHermesClawRuntimeLayout();
  const registryPath = getSharedConfigRegistryPath(layout);
  const registryExists = existsSync(registryPath);
  const changes: Array<{ type: 'create' | 'update'; path: string }> = [];
  const registry = await getHermesClawSharedConfig();
  const issues = validateSharedConfigRegistry(registry);
  const conflicts = detectSharedConfigConflicts(registry);
  const adapters = buildSharedConfigAdapters(registry);

  if (!registryExists) {
    changes.push({ type: 'create', path: basename(registryPath) });
    if (!dryRun) {
      writeJsonFile(registryPath, { ...defaultSharedConfigRegistry(), updatedAt: Date.now() });
    }
  }

  for (const [runtime, output] of [
    ['openclaw', adapters.openclaw],
    ['hermes', adapters.hermes],
  ] as const) {
    const adapterPath = join(layout.sharedConfigDir, `${runtime}-adapter.json`);
    changes.push({ type: existsSync(adapterPath) ? 'update' : 'create', path: basename(adapterPath) });
    if (!dryRun && issues.every((issue) => issue.severity !== 'error') && conflicts.length === 0) {
      writeJsonFile(adapterPath, output);
    }
  }

  const blockingMessages = [
    ...issues.filter((issue) => issue.severity === 'error').map((issue) => issue.message),
    ...conflicts.map((conflict) => conflict.message),
  ];

  return {
    dryRun,
    scope,
    changes,
    log: blockingMessages.length > 0
      ? blockingMessages.map((message) => `Blocked shared-config sync: ${message}`)
      : changes.map((change) => `${dryRun ? 'Would write' : 'Wrote'} ${change.path}`),
    validation: {
      ok: issues.every((issue) => issue.severity !== 'error'),
      issues,
    },
    conflicts,
    adapters,
  };
}
