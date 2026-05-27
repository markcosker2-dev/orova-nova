import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { getAllSettings } from '../../utils/store';
import { getHermesClawRuntimeLayout, getHermesEndpoint, getHermesInstallStatus } from '../../utils/paths';
import { proxyAwareFetch } from '../../utils/proxy-fetch';

export interface HermesStandaloneHealth {
  ok: boolean;
  error?: string;
  uptime?: number;
  pid?: number;
  state?: HermesStandaloneProcessState;
}

export type HermesStandaloneProcessState = 'stopped' | 'starting' | 'running' | 'stopping' | 'error';

interface HermesRuntimeEntry {
  type?: 'python' | 'node' | 'binary' | string;
  command?: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
}

interface HermesRuntimeDescriptor {
  entry?: HermesRuntimeEntry;
  command?: string;
  args?: string[];
  packageName?: string;
}

interface HermesClawManifestFile {
  activeChannel?: string;
  channels?: Record<string, { runtimeDir?: string }>;
}

interface HermesLaunchPlan {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

export interface HermesStandaloneManager {
  start(): Promise<void>;
  stop(): Promise<void>;
  restart(): Promise<void>;
  reload(): Promise<void>;
  debouncedRestart(delayMs?: number): void;
  debouncedReload(delayMs?: number): void;
  checkHealth(): Promise<HermesStandaloneHealth>;
  rpc<T>(method: string, params?: unknown, timeoutMs?: number): Promise<T>;
  forceTerminateOwnedProcessForQuit(): Promise<boolean>;
}

class InstallStatusBackedHermesStandaloneManager implements HermesStandaloneManager {
  private restartTimer: ReturnType<typeof setTimeout> | undefined;

  private reloadTimer: ReturnType<typeof setTimeout> | undefined;

  private child: ChildProcessWithoutNullStreams | undefined;

  private state: HermesStandaloneProcessState = 'stopped';

  private lastError: string | undefined;

  private stderrTail = '';

  private async getInstallStatus() {
    const settings = await getAllSettings();
    const runtime = settings.runtime;
    return getHermesInstallStatus({
      windowsHermesPreferredMode: runtime.windowsHermesPreferredMode,
      windowsHermesNativePath: runtime.windowsHermesNativePath,
      windowsHermesWslDistro: runtime.windowsHermesWslDistro,
      installedKinds: runtime.installedKinds,
    });
  }

  private async checkHealthAtEndpoint(endpoint: string): Promise<HermesStandaloneHealth> {
    const normalizedEndpoint = endpoint.replace(/\/$/, '');

    try {
      const response = await proxyAwareFetch(`${normalizedEndpoint}/health`, { method: 'GET' });
      if (!response.ok) {
        return { ok: false, error: `Hermes health check failed with HTTP ${response.status}` };
      }

      const payload = await response.json().catch(() => ({} as Record<string, unknown>));
      const ok = payload && typeof payload === 'object' && 'ok' in payload
        ? Boolean((payload as { ok?: unknown }).ok)
        : true;
      const uptime = payload && typeof payload === 'object' && 'uptime' in payload
        && typeof (payload as { uptime?: unknown }).uptime === 'number'
        ? (payload as { uptime: number }).uptime
        : undefined;
      const error = payload && typeof payload === 'object' && 'error' in payload
        && typeof (payload as { error?: unknown }).error === 'string'
        ? (payload as { error: string }).error
        : undefined;

      return {
        ok,
        uptime,
        pid: this.child?.pid,
        state: this.state,
        error: ok ? undefined : error ?? 'Hermes endpoint is unreachable',
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        ok: false,
        pid: this.child?.pid,
        state: this.state,
        error: `Failed to reach Hermes endpoint ${normalizedEndpoint}: ${message}`,
      };
    }
  }

  private endpointPort(endpoint: string): string {
    try {
      return new URL(endpoint).port || '8642';
    } catch {
      return '8642';
    }
  }

  private expandArgs(args: string[], endpoint: string): string[] {
    const port = this.endpointPort(endpoint);
    return args.map((arg) => arg.replaceAll('{port}', port).replaceAll('{endpoint}', endpoint));
  }

  private readJson<T>(path: string): T | undefined {
    if (!existsSync(path)) return undefined;
    try {
      return JSON.parse(readFileSync(path, 'utf-8')) as T;
    } catch {
      return undefined;
    }
  }

  private findRuntimeDirFromHermesClawManifest(): string | undefined {
    const layout = getHermesClawRuntimeLayout();
    const manifest = this.readJson<HermesClawManifestFile>(layout.manifestPath);
    const activeChannel = manifest?.activeChannel;
    if (!activeChannel) return undefined;
    return manifest.channels?.[activeChannel]?.runtimeDir;
  }

  private readRuntimeDescriptor(runtimeDir: string): HermesRuntimeDescriptor | undefined {
    return this.readJson<HermesRuntimeDescriptor>(join(runtimeDir, 'runtime.json'))
      ?? this.readJson<HermesRuntimeDescriptor>(join(runtimeDir, 'manifest.json'));
  }

  private resolveEntryFromDescriptor(descriptor: HermesRuntimeDescriptor | undefined): HermesRuntimeEntry | undefined {
    if (!descriptor) return undefined;
    if (descriptor.entry?.command) return descriptor.entry;
    if (descriptor.command) {
      return { command: descriptor.command, args: descriptor.args ?? [] };
    }
    return undefined;
  }

  private bundledHermesAgentPythonPath(runtimeDir: string): string {
    if (process.platform === 'win32') {
      return join(runtimeDir, '.venv', 'Scripts', 'python.exe');
    }
    return join(runtimeDir, '.venv', 'bin', 'python');
  }

  private resolveBundledHermesAgentEntry(
    runtimeDir: string,
    descriptor: HermesRuntimeDescriptor | undefined,
  ): HermesRuntimeEntry | undefined {
    if (descriptor?.packageName !== 'hermes-agent') {
      return undefined;
    }

    const pythonPath = this.bundledHermesAgentPythonPath(runtimeDir);
    if (!existsSync(pythonPath)) {
      return undefined;
    }

    return {
      type: 'python',
      command: pythonPath,
      args: ['-m', 'hermes.gateway.run', '--port', '{port}'],
      cwd: runtimeDir,
    };
  }

  private async resolveLaunchPlan(endpoint: string): Promise<HermesLaunchPlan> {
    const installStatus = await this.getInstallStatus();
    if (!installStatus.installed) {
      throw new Error(installStatus.error ?? 'Hermes standalone runtime is not installed');
    }

    const candidateDirs = [
      this.findRuntimeDirFromHermesClawManifest(),
      installStatus.installPath,
    ].filter((value): value is string => Boolean(value));

    for (const runtimeDir of candidateDirs) {
      const descriptor = this.readRuntimeDescriptor(runtimeDir);
      const entry = this.resolveEntryFromDescriptor(descriptor)
        ?? this.resolveBundledHermesAgentEntry(runtimeDir, descriptor);
      if (!entry?.command) continue;
      return {
        command: entry.command,
        args: this.expandArgs(entry.args ?? [], endpoint),
        cwd: entry.cwd ?? runtimeDir,
        env: {
          ...process.env,
          ...(entry.env ?? {}),
          HERMES_ENDPOINT: endpoint,
          HERMES_PORT: this.endpointPort(endpoint),
        },
      };
    }

    throw new Error('Hermes runtime manifest entry was not found. Install or repair HermesClaw runtime before starting it.');
  }

  private markChildExit(code: number | null, signal: NodeJS.Signals | null): void {
    this.child = undefined;
    if (this.state === 'stopping') {
      this.state = 'stopped';
      return;
    }
    this.state = code === 0 ? 'stopped' : 'error';
    this.lastError = code === 0 ? undefined : `Hermes process exited with code ${code ?? 'null'}${signal ? ` (${signal})` : ''}`;
  }

  private appendStderr(chunk: Buffer): void {
    this.stderrTail = `${this.stderrTail}${chunk.toString('utf-8')}`.slice(-4000);
  }

  async start(): Promise<void> {
    if (this.child && (this.state === 'starting' || this.state === 'running')) {
      return;
    }

    const endpoint = getHermesEndpoint();
    const plan = await this.resolveLaunchPlan(endpoint);
    this.state = 'starting';
    this.lastError = undefined;
    this.stderrTail = '';

    await new Promise<void>((resolve, reject) => {
      const child = spawn(plan.command, plan.args, {
        cwd: plan.cwd,
        env: plan.env,
        stdio: 'pipe',
        windowsHide: true,
      });
      this.child = child;

      const onError = (error: Error) => {
        this.child = undefined;
        this.state = 'error';
        this.lastError = error.message;
        reject(error);
      };

      child.once('error', onError);
      child.once('spawn', () => {
        child.off('error', onError);
        this.state = 'running';
        resolve();
      });
      child.once('exit', (code, signal) => this.markChildExit(code, signal));
      child.stderr.on('data', (chunk: Buffer) => this.appendStderr(chunk));
    });
  }

  async stop(): Promise<void> {
    if (!this.child) {
      this.state = 'stopped';
      return;
    }

    const child = this.child;
    this.state = 'stopping';
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        if (this.child === child) child.kill('SIGKILL');
      }, 5000);

      child.once('exit', () => {
        clearTimeout(timeout);
        resolve();
      });
      child.kill('SIGTERM');
    });
  }

  async restart(): Promise<void> {
    await this.stop();
    await this.start();
  }

  async reload(): Promise<void> {
    await this.restart();
  }

  debouncedRestart(delayMs = 250): void {
    if (this.restartTimer) clearTimeout(this.restartTimer);
    this.restartTimer = setTimeout(() => {
      this.restartTimer = undefined;
      void this.restart();
    }, delayMs);
  }

  debouncedReload(delayMs = 250): void {
    if (this.reloadTimer) clearTimeout(this.reloadTimer);
    this.reloadTimer = setTimeout(() => {
      this.reloadTimer = undefined;
      void this.reload();
    }, delayMs);
  }

  async checkHealth(): Promise<HermesStandaloneHealth> {
    const installStatus = await this.getInstallStatus();
    if (!installStatus.installed) {
      return {
        ok: false,
        pid: this.child?.pid,
        state: this.state,
        error: installStatus.error ?? 'Hermes standalone runtime is not installed',
      };
    }

    const health = await this.checkHealthAtEndpoint(installStatus.endpoint ?? getHermesEndpoint());
    if (!health.ok && this.lastError) {
      return {
        ...health,
        error: `${health.error}; process state=${this.state}; last error=${this.lastError}${this.stderrTail ? `; stderr=${this.stderrTail}` : ''}`,
      };
    }
    return health;
  }

  async rpc<T>(method: string, params?: unknown, timeoutMs = 15000): Promise<T> {
    const installStatus = await this.getInstallStatus();
    if (!installStatus.installed) {
      throw new Error(installStatus.error ?? 'Hermes standalone runtime is not installed');
    }
    const endpoint = (installStatus.endpoint ?? getHermesEndpoint()).replace(/\/$/, '');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await proxyAwareFetch(`${endpoint}/rpc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: Date.now(), method, params }),
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({} as Record<string, unknown>));
      if (!response.ok) {
        throw new Error(`Hermes RPC ${method} failed with HTTP ${response.status}`);
      }
      if (payload && typeof payload === 'object' && 'error' in payload) {
        throw new Error(`Hermes RPC ${method} failed: ${JSON.stringify((payload as { error?: unknown }).error)}`);
      }
      return payload && typeof payload === 'object' && 'result' in payload
        ? (payload as { result: T }).result
        : payload as T;
    } finally {
      clearTimeout(timeout);
    }
  }

  async forceTerminateOwnedProcessForQuit(): Promise<boolean> {
    if (!this.child) return false;
    this.child.kill('SIGKILL');
    this.child = undefined;
    this.state = 'stopped';
    return true;
  }
}

let singleton: HermesStandaloneManager | undefined;

export function getHermesStandaloneManager(): HermesStandaloneManager {
  singleton ??= new InstallStatusBackedHermesStandaloneManager();
  return singleton;
}
