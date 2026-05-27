/**
 * Path Utilities
 * Cross-platform path resolution helpers
 */
import { createRequire } from 'node:module';
import { execFileSync } from 'child_process';
import { isAbsolute, join } from 'path';
import { homedir } from 'os';
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'fs';
import type { HermesWindowsPreferredMode, InstallStatus } from '../runtime/types';

const require = createRequire(import.meta.url);

type ElectronAppLike = Pick<typeof import('electron').app, 'isPackaged' | 'getPath' | 'getAppPath'>;

export {
  quoteForCmd,
  needsWinShell,
  prepareWinSpawn,
  normalizeNodeRequirePathForNodeOptions,
  appendNodeRequireToNodeOptions,
} from './win-shell';

function getElectronApp() {
  if (process.versions?.electron) {
    const electronApp = (require('electron') as typeof import('electron')).app;
    if (electronApp && typeof electronApp.isPackaged === 'boolean') {
      return electronApp;
    }
  }

  const fallbackUserData = process.env.HERMESCLAW_USER_DATA_DIR?.trim() || join(homedir(), '.hermesclaw');
  const fallbackAppPath = process.cwd();
  const fallbackApp: ElectronAppLike = {
    isPackaged: false,
    getPath: (name) => {
      if (name === 'userData') return fallbackUserData;
      return fallbackUserData;
    },
    getAppPath: () => fallbackAppPath,
  };
  return fallbackApp;
}

/**
 * Expand ~ to home directory
 */
export function expandPath(path: string): string {
  if (path.startsWith('~')) {
    return path.replace('~', homedir());
  }
  return path;
}

/**
 * Get OpenClaw config directory
 */
export function getOpenClawConfigDir(): string {
  return join(homedir(), '.openclaw');
}

export const HERMES_DEFAULT_ENDPOINT = 'http://127.0.0.1:8642';

export interface HermesInstallStatus extends InstallStatus {
  endpoint?: string;
  error?: string;
}

export interface HermesInstallStatusOptions {
  windowsHermesPreferredMode?: HermesWindowsPreferredMode;
  windowsHermesNativePath?: string;
  windowsHermesWslDistro?: string;
  installedKinds?: string[];
}

export function getHermesHomeDir(): string {
  return join(homedir(), '.hermes');
}

export function getHermesEndpoint(): string {
  return HERMES_DEFAULT_ENDPOINT;
}

export interface HermesClawRuntimeLayout {
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
}

interface ActiveOpenClawRuntimeRecord {
  runtimeDir?: string;
  version?: string;
}

interface OpenClawRuntimeDescriptor {
  schemaVersion?: number;
  version?: string;
  entry?: {
    type?: string;
    command?: string;
    args?: string[];
  };
  health?: {
    url?: string;
  };
}

/**
 * Current schema version for OpenClaw runtime.json descriptors.
 *
 * History:
 *   v1 (legacy): entry.args could contain the obsolete `dist/gateway.js` entrypoint.
 *   v2: entry.args MUST point at the current `dist/entry.js` entrypoint.
 *
 * On read, descriptors with schemaVersion < 2 are auto-migrated by overwriting
 * with the current default so stale on-disk state self-heals.
 */
const OPENCLAW_DESCRIPTOR_SCHEMA_VERSION = 2;

function buildDefaultOpenClawDescriptor(version: string | undefined): OpenClawRuntimeDescriptor {
  return {
    schemaVersion: OPENCLAW_DESCRIPTOR_SCHEMA_VERSION,
    version: version ?? 'local',
    entry: {
      type: 'node',
      command: 'node',
      args: ['dist/entry.js'],
    },
    health: {
      url: 'http://127.0.0.1:18789/health',
    },
  };
}

export function getHermesClawRootDir(): string {
  return join(getElectronApp().getPath('userData'), 'HermesClaw');
}

export function getHermesClawPackagedBaselineDir(): string {
  if (getElectronApp().isPackaged) {
    return join(process.resourcesPath, 'hermesclaw');
  }
  return join(getElectronApp().getAppPath(), 'node_modules', '@hermesclaw');
}

export function getHermesClawRuntimeLayout(): HermesClawRuntimeLayout {
  const rootDir = getHermesClawRootDir();
  const runtimeStateDir = join(rootDir, 'runtime-state');
  return {
    rootDir,
    packagedBaselineDir: getHermesClawPackagedBaselineDir(),
    baselineRuntimesDir: join(rootDir, 'runtimes', 'baseline'),
    userRuntimesDir: join(rootDir, 'runtimes', 'user'),
    runtimeStateDir,
    activeRuntimesPath: join(runtimeStateDir, 'active-runtimes.json'),
    compatibilityMatrixPath: join(runtimeStateDir, 'compatibility-matrix.json'),
    installHistoryPath: join(runtimeStateDir, 'install-history.json'),
    sharedConfigDir: join(rootDir, 'shared-config'),
    manifestPath: join(rootDir, 'runtime-manifest.json'),
    backupsDir: join(rootDir, 'backups'),
    logsDir: join(rootDir, 'logs'),
    cacheDir: join(rootDir, 'cache'),
  };
}

export function ensureHermesClawRuntimeLayout(): HermesClawRuntimeLayout {
  const layout = getHermesClawRuntimeLayout();
  ensureDir(layout.rootDir);
  ensureDir(layout.baselineRuntimesDir);
  ensureDir(layout.userRuntimesDir);
  ensureDir(layout.runtimeStateDir);
  ensureDir(layout.sharedConfigDir);
  ensureDir(layout.backupsDir);
  ensureDir(layout.logsDir);
  ensureDir(layout.cacheDir);
  // Best-effort, idempotent heal: legacy installs may have written
  // hermes.runtimeDir pointing at the OpenClaw directory. Rewrite it now so
  // every consumer of the layout sees consistent state.
  healActiveHermesRuntimePathIfMisPointed();
  return layout;
}

function hasWslExecutable(): boolean {
  const systemRoot = process.env.SystemRoot || 'C:\\Windows';
  return existsSync(join(systemRoot, 'System32', 'wsl.exe'));
}

function getBundledHermesAgentDir(): string {
  if (getElectronApp().isPackaged) {
    return join(process.resourcesPath, 'hermes-agent');
  }
  return join(getElectronApp().getAppPath(), 'build', 'hermes-agent');
}

function getBundledHermesAgentPythonPath(runtimeDir: string): string {
  if (process.platform === 'win32') {
    return join(runtimeDir, '.venv', 'Scripts', 'python.exe');
  }
  return join(runtimeDir, '.venv', 'bin', 'python');
}

function readBundledHermesAgentVersion(runtimeDir: string): string | undefined {
  try {
    const manifestPath = join(runtimeDir, 'manifest.json');
    if (existsSync(manifestPath)) {
      const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as { version?: string };
      if (manifest.version) return manifest.version;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

function readResourcesHermesAgentVersion(): string | undefined {
  try {
    const resourcesManifestPath = join(getElectronApp().getAppPath(), 'resources', 'hermes-agent', 'manifest.json');
    if (existsSync(resourcesManifestPath)) {
      const manifest = JSON.parse(readFileSync(resourcesManifestPath, 'utf-8')) as { version?: string };
      return manifest.version;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

function buildBundledHermesInstallStatus(): HermesInstallStatus | undefined {
  const runtimeDir = getBundledHermesAgentDir();
  const manifestPath = join(runtimeDir, 'manifest.json');
  const pythonPath = getBundledHermesAgentPythonPath(runtimeDir);

  if (!existsSync(runtimeDir) || !existsSync(manifestPath) || !existsSync(pythonPath)) {
    return undefined;
  }

  return {
    installed: true,
    installMode: 'native',
    installPath: runtimeDir,
    endpoint: getHermesEndpoint(),
    version: readBundledHermesAgentVersion(runtimeDir),
  };
}

function getHermesWslHomeLabel(distro: string): string {
  return `~/.hermes (WSL:${distro})`;
}

function getHermesNativeHomeLabel(configuredPath?: string): string {
  const candidate = configuredPath?.trim();
  return expandPath(candidate && candidate.length > 0 ? candidate : getHermesHomeDir());
}

function probeHermesHomeInWsl(distro: string): boolean {
  try {
    execFileSync('wsl.exe', ['-d', distro, '--', 'sh', '-lc', 'test -d ~/.hermes'], {
      stdio: 'ignore',
    });
    return true;
  } catch {
    return false;
  }
}

function parseWslDistroOutput(output: string): string[] {
  return output
    .replaceAll('\0', '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^Windows Subsystem for Linux Distributions:/i.test(line));
}

export function listWslDistros(): string[] {
  if (process.platform !== 'win32' || !hasWslExecutable()) {
    return [];
  }

  try {
    const output = execFileSync('wsl.exe', ['-l', '-q'], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });

    const decodedUtf16 = parseWslDistroOutput(output.toString('utf16le'));
    if (decodedUtf16.length > 0) {
      return decodedUtf16;
    }

    return parseWslDistroOutput(output.toString('utf8'));
  } catch {
    return [];
  }
}

function buildNativeHermesInstallStatus(configuredPath?: string): HermesInstallStatus {
  const installPath = getHermesNativeHomeLabel(configuredPath);
  const reachable = existsSync(installPath);
  const installed = reachable;

  return {
    installed,
    installMode: 'native',
    installPath: installed ? installPath : undefined,
    endpoint: getHermesEndpoint(),
    error: installed ? undefined : `Hermes native home directory was not found at ${installPath}`,
  };
}

function buildWslHermesInstallStatus(distro?: string): HermesInstallStatus {
  if (!distro) {
    return {
      installed: false,
      installMode: 'wsl2',
      endpoint: getHermesEndpoint(),
      error: 'Hermes on Windows requires a configured WSL2 distro',
    };
  }

  const installPath = getHermesWslHomeLabel(distro);

  if (!hasWslExecutable()) {
    return {
      installed: false,
      installMode: 'wsl2',
      installPath,
      endpoint: getHermesEndpoint(),
      error: 'WSL2 is not available on this system',
    };
  }

  const reachable = probeHermesHomeInWsl(distro);
  const installed = reachable;

  return {
    installed,
    installMode: 'wsl2',
    installPath: installed ? installPath : undefined,
    endpoint: getHermesEndpoint(),
    error: installed ? undefined : `Hermes home directory is not reachable in WSL distro "${distro}"`,
  };
}

function mergeHermesProbeErrors(statuses: HermesInstallStatus[]): string | undefined {
  const errors = Array.from(new Set(statuses.map((status) => status.error).filter(Boolean)));
  if (errors.length === 0) {
    return undefined;
  }
  return errors.join(' | ');
}

export function getHermesInstallStatus(options: HermesInstallStatusOptions = {}): HermesInstallStatus {
  const bundledStatus = buildBundledHermesInstallStatus();
  const resourcesVersion = readResourcesHermesAgentVersion();

  const withVersionFallback = (status: HermesInstallStatus): HermesInstallStatus => {
    if (!status.version && resourcesVersion) {
      return { ...status, version: resourcesVersion };
    }
    return status;
  };

  if (process.platform === 'win32') {
    const preferredMode = options.windowsHermesPreferredMode ?? 'wsl2';
    const nativeStatus = buildNativeHermesInstallStatus(options.windowsHermesNativePath);
    const wslStatus = buildWslHermesInstallStatus(options.windowsHermesWslDistro);
    const orderedStatuses = preferredMode === 'native'
      ? [nativeStatus, wslStatus]
      : [wslStatus, nativeStatus];

    const installedStatus = orderedStatuses.find((status) => status.installed);
    if (installedStatus) {
      return withVersionFallback(installedStatus);
    }

    if (bundledStatus) {
      return withVersionFallback(bundledStatus);
    }

    const primaryStatus = orderedStatuses[0];
    return withVersionFallback({
      ...primaryStatus,
      error: mergeHermesProbeErrors(orderedStatuses) ?? primaryStatus.error,
    });
  }

  const nativeStatus = buildNativeHermesInstallStatus(options.windowsHermesNativePath);
  if (nativeStatus.installed) {
    return withVersionFallback(nativeStatus);
  }
  return withVersionFallback(bundledStatus ?? nativeStatus);
}

/**
 * Get OpenClaw skills directory
 */
export function getOpenClawSkillsDir(): string {
  return join(getOpenClawConfigDir(), 'skills');
}

/**
 * Get HermesClaw config directory
 */
export function getHermesClawConfigDir(): string {
  return join(homedir(), '.hermesclaw');
}

/**
 * Get HermesClaw logs directory
 */
export function getLogsDir(): string {
  return join(getElectronApp().getPath('userData'), 'logs');
}

/**
 * Get HermesClaw data directory
 */
export function getDataDir(): string {
  return getElectronApp().getPath('userData');
}

/**
 * Ensure directory exists
 */
export function ensureDir(dir: string): void {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

/**
 * Get resources directory (for bundled assets)
 */
export function getResourcesDir(): string {
  if (getElectronApp().isPackaged) {
    return join(process.resourcesPath, 'resources');
  }
  return join(__dirname, '../../resources');
}

function getBundledOpenClawDir(): string {
  if (getElectronApp().isPackaged) {
    return join(process.resourcesPath, 'openclaw');
  }
  return join(__dirname, '../../node_modules/openclaw');
}

function readActiveOpenClawRuntimeRecord(): ActiveOpenClawRuntimeRecord | undefined {
  try {
    const layout = getHermesClawRuntimeLayout();
    if (!existsSync(layout.activeRuntimesPath)) {
      return undefined;
    }

    const parsed = JSON.parse(readFileSync(layout.activeRuntimesPath, 'utf-8')) as {
      runtimes?: {
        openclaw?: ActiveOpenClawRuntimeRecord;
      };
    };
    const activeRuntime = parsed.runtimes?.openclaw;
    if (!activeRuntime?.runtimeDir || !existsSync(activeRuntime.runtimeDir)) {
      return undefined;
    }
    return activeRuntime;
  } catch {
    return undefined;
  }
}

function readOpenClawRuntimeDescriptor(runtimeDir: string): OpenClawRuntimeDescriptor | undefined {
  try {
    const descriptorPath = join(runtimeDir, 'runtime.json');
    if (!existsSync(descriptorPath)) {
      return undefined;
    }
    const parsed = JSON.parse(readFileSync(descriptorPath, 'utf-8')) as OpenClawRuntimeDescriptor;

    // Migrate legacy v1 descriptors (which may point at the obsolete
    // `dist/gateway.js` entrypoint) by rewriting with current defaults.
    // Preserves the recorded version so callers downstream still see it.
    const currentSchemaVersion = parsed.schemaVersion ?? 1;
    if (currentSchemaVersion < OPENCLAW_DESCRIPTOR_SCHEMA_VERSION) {
      const migrated = buildDefaultOpenClawDescriptor(parsed.version);
      try {
        writeFileSync(descriptorPath, JSON.stringify(migrated, null, 2), 'utf-8');
      } catch {
        // If we cannot rewrite (e.g. read-only fs), still return the migrated
        // shape in-memory so the launcher uses the correct entrypoint.
      }
      return migrated;
    }

    return parsed;
  } catch {
    return undefined;
  }
}

interface ActiveHermesRuntimeRecord {
  runtimeDir?: string;
  version?: string;
  status?: string;
}

interface ActiveRuntimesFile {
  schemaVersion?: number;
  runtimes?: {
    openclaw?: ActiveOpenClawRuntimeRecord;
    hermes?: ActiveHermesRuntimeRecord & Record<string, unknown>;
  };
  [key: string]: unknown;
}

/**
 * Heal active-runtimes.json when an old code path mis-pointed the Hermes
 * runtime record at the OpenClaw runtime directory. The signature is the
 * literal `\openclaw\` (or `/openclaw/`) path segment in the recorded
 * `hermes.runtimeDir`. We rewrite it to the symmetric `\hermes\` path under
 * `userRuntimesDir` and clear `status: 'rollback-required'` so the gateway
 * can be restarted without manual intervention.
 *
 * Idempotent: returns immediately if no mis-pointed record is found.
 */
export function healActiveHermesRuntimePathIfMisPointed(): void {
  try {
    const layout = getHermesClawRuntimeLayout();
    if (!existsSync(layout.activeRuntimesPath)) {
      return;
    }

    const raw = readFileSync(layout.activeRuntimesPath, 'utf-8');
    const parsed = JSON.parse(raw) as ActiveRuntimesFile;
    const hermesRecord = parsed.runtimes?.hermes;
    const hermesDir = hermesRecord?.runtimeDir;
    if (!hermesRecord || typeof hermesDir !== 'string' || hermesDir.length === 0) {
      return;
    }

    const containsOpenClawSegment = /[\\/]openclaw[\\/]/i.test(hermesDir);
    if (!containsOpenClawSegment) {
      return;
    }

    // Rewrite by swapping the first `\openclaw\` segment for `\hermes\`.
    const healedDir = hermesDir.replace(/([\\/])openclaw([\\/])/i, '$1hermes$2');
    hermesRecord.runtimeDir = healedDir;

    if (hermesRecord.status === 'rollback-required') {
      hermesRecord.status = 'ready';
      delete (hermesRecord as Record<string, unknown>).lastError;
    }

    writeFileSync(layout.activeRuntimesPath, JSON.stringify(parsed, null, 2), 'utf-8');
  } catch {
    // Healing is best-effort; never block startup on a heal failure.
  }
}

function resolveOpenClawRuntimeEntryFromDescriptor(runtimeDir: string): string | undefined {
  const descriptor = readOpenClawRuntimeDescriptor(runtimeDir);
  const entryArg = descriptor?.entry?.args?.[0];
  if (!entryArg || descriptor?.entry?.type !== 'node') {
    return undefined;
  }
  return isAbsolute(entryArg) ? entryArg : join(runtimeDir, entryArg);
}

function resolveOpenClawRuntimeEntry(runtimeDir: string): string {
  return resolveOpenClawRuntimeEntryFromDescriptor(runtimeDir) ?? join(runtimeDir, 'openclaw.mjs');
}

function isLaunchableOpenClawRuntimeDir(runtimeDir: string): boolean {
  return existsSync(resolveOpenClawRuntimeEntry(runtimeDir));
}

/**
 * Get preload script path
 */
export function getPreloadPath(): string {
  return join(__dirname, '../preload/index.js');
}

/**
 * Get OpenClaw package directory
 * - Production (packaged): from resources/openclaw (copied by electron-builder extraResources)
 * - Development: from node_modules/openclaw
 */
export function getOpenClawDir(): string {
  return getBundledOpenClawDir();
}

/**
 * Get OpenClaw package directory resolved to a real path.
 * Useful when consumers need deterministic module resolution under pnpm symlinks.
 */
export function getOpenClawResolvedDir(): string {
  const dir = getOpenClawDir();
  if (!existsSync(dir)) {
    return dir;
  }
  try {
    return realpathSync(dir);
  } catch {
    return dir;
  }
}

/**
 * Get the active OpenClaw runtime directory when HermesClaw runtime state has
 * switched to a downloaded runtime; otherwise fall back to the bundled package.
 */
export function getOpenClawRuntimeDir(): string {
  const activeRuntimeDir = readActiveOpenClawRuntimeRecord()?.runtimeDir;
  if (activeRuntimeDir && isLaunchableOpenClawRuntimeDir(activeRuntimeDir)) {
    return activeRuntimeDir;
  }
  return getBundledOpenClawDir();
}

/**
 * Get the active OpenClaw runtime directory resolved to a real path.
 */
export function getOpenClawRuntimeResolvedDir(): string {
  const dir = getOpenClawRuntimeDir();
  if (!existsSync(dir)) {
    return dir;
  }
  try {
    return realpathSync(dir);
  } catch {
    return dir;
  }
}

/**
 * Get OpenClaw entry script path (openclaw.mjs)
 */
export function getOpenClawEntryPath(): string {
  return join(getOpenClawDir(), 'openclaw.mjs');
}

/**
 * Get the entry script for the active OpenClaw runtime. Downloaded runtimes may
 * provide a runtime.json descriptor instead of the packaged openclaw.mjs entry.
 */
export function getOpenClawRuntimeEntryPath(): string {
  const runtimeDir = getOpenClawRuntimeDir();
  return resolveOpenClawRuntimeEntry(runtimeDir);
}

/**
 * Get ClawHub CLI entry script path (clawdhub.js)
 */
export function getClawHubCliEntryPath(): string {
  return join(getElectronApp().getAppPath(), 'node_modules', 'clawhub', 'bin', 'clawdhub.js');
}

/**
 * Get ClawHub CLI binary path (node_modules/.bin)
 */
export function getClawHubCliBinPath(): string {
  const binName = process.platform === 'win32' ? 'clawhub.cmd' : 'clawhub';
  return join(getElectronApp().getAppPath(), 'node_modules', '.bin', binName);
}

/**
 * Check if OpenClaw package exists
 */
export function isOpenClawPresent(): boolean {
  const dir = getOpenClawDir();
  const pkgJsonPath = join(dir, 'package.json');
  return existsSync(dir) && existsSync(pkgJsonPath);
}

export function isOpenClawRuntimePresent(): boolean {
  const dir = getOpenClawRuntimeDir();
  const runtimeEntryPath = getOpenClawRuntimeEntryPath();
  const pkgJsonPath = join(dir, 'package.json');
  return existsSync(dir) && (existsSync(runtimeEntryPath) || existsSync(pkgJsonPath));
}

/**
 * Check if OpenClaw is built (has dist folder)
 * For the npm package, this should always be true since npm publishes the built dist.
 */
export function isOpenClawBuilt(): boolean {
  const dir = getOpenClawDir();
  const distDir = join(dir, 'dist');
  const hasDist = existsSync(distDir);
  return hasDist;
}

/**
 * Get OpenClaw status for environment check
 */
export interface OpenClawStatus {
  packageExists: boolean;
  isBuilt: boolean;
  entryPath: string;
  dir: string;
  version?: string;
}

export function getOpenClawStatus(): OpenClawStatus {
  const dir = getOpenClawDir();
  let version: string | undefined;

  // Try to read version from package.json
  try {
    const pkgPath = join(dir, 'package.json');
    if (existsSync(pkgPath)) {
      const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'));
      version = pkg.version;
    }
  } catch {
    // Ignore version read errors
  }

  const status: OpenClawStatus = {
    packageExists: isOpenClawPresent(),
    isBuilt: isOpenClawBuilt(),
    entryPath: getOpenClawEntryPath(),
    dir,
    version,
  };

  try {
    const { logger } = require('./logger') as typeof import('./logger');
    logger.info('OpenClaw status:', status);
  } catch {
    // Ignore logger bootstrap issues in non-Electron contexts such as unit tests.
  }
  return status;
}

export function getOpenClawRuntimeStatus(): OpenClawStatus {
  const dir = getOpenClawRuntimeDir();
  const entryPath = getOpenClawRuntimeEntryPath();
  const activeRuntime = readActiveOpenClawRuntimeRecord();
  const descriptor = readOpenClawRuntimeDescriptor(dir);
  const usingActiveRuntime = activeRuntime?.runtimeDir === dir;
  let version = (usingActiveRuntime ? activeRuntime?.version : undefined) ?? descriptor?.version;

  if (!version) {
    try {
      const pkgPath = join(dir, 'package.json');
      if (existsSync(pkgPath)) {
        const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8')) as { version?: string };
        version = pkg.version;
      }
    } catch {
      // Ignore version read errors.
    }
  }

  return {
    packageExists: isOpenClawRuntimePresent(),
    isBuilt: existsSync(entryPath) || existsSync(join(dir, 'dist')),
    entryPath,
    dir,
    version,
  };
}
