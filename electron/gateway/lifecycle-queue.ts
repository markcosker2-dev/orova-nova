/**
 * Gateway Lifecycle Queue
 * 
 * Manages sequential execution of gateway lifecycle mutations (start, restart, reload, stop)
 * with shared operation deduplication to prevent concurrent conflicts.
 * 
 * Based on QClaw pattern:
 * https://github.com/qiuzhi2046/Qclaw/blob/c494768977f4e48b8eacbfae7ae390af11fc015f/electron/main/gateway-lifecycle-controller.ts
 */

import { logger } from '../utils/logger';

export type LifecycleMutationAction = 'ensure' | 'start' | 'restart' | 'reload' | 'stop';

export interface LifecycleMutation {
  key: string;
  action: LifecycleMutationAction;
  reason: string;
  startedAt: number;
}

export interface LifecycleQueueState {
  busy: boolean;
  inFlight: {
    key: string;
    action: LifecycleMutationAction;
    reason: string;
    startedAt: string;
  } | null;
  sharedKeys: string[];
}

export interface CliResult {
  ok: boolean;
  code?: number | null;
  stdout?: string;
  stderr?: string;
}

export interface GatewayReloadResult extends CliResult {
  running?: boolean;
  summary?: string;
  stateCode?: string;
}

export interface GatewayEnsureRunningResult extends CliResult {
  running?: boolean;
  summary?: string;
  stateCode?: string;
}

export class GatewayLifecycleQueue {
  private mutationQueue: Promise<void> = Promise.resolve();
  private inFlightMutation: LifecycleMutation | null = null;
  private sharedMutations = new Map<string, Promise<unknown>>();

  private enqueueLifecycleMutation<T>(task: () => Promise<T>): Promise<T> {
    const runTask = this.mutationQueue.then(task, task);
    this.mutationQueue = runTask.then(
      () => undefined,
      () => undefined
    );
    return runTask;
  }

  private runSharedLifecycleMutation<T>(
    key: string,
    action: LifecycleMutationAction,
    reason: string,
    task: () => Promise<T>
  ): Promise<T> {
    const existing = this.sharedMutations.get(key);
    if (existing) {
      logger.debug(`Gateway lifecycle mutation already in flight (key=${key}, action=${action})`);
      return existing as Promise<T>;
    }

    const mutation: LifecycleMutation = {
      key,
      action,
      reason,
      startedAt: Date.now(),
    };

    const scheduled = this.enqueueLifecycleMutation(async () => {
      this.inFlightMutation = mutation;
      logger.info(`Gateway lifecycle mutation started (key=${key}, action=${action}, reason=${reason})`);
      try {
        return await task();
      } finally {
        if (this.inFlightMutation === mutation) {
          this.inFlightMutation = null;
        }
        logger.info(`Gateway lifecycle mutation completed (key=${key}, action=${action})`);
      }
    });

    this.sharedMutations.set(key, scheduled);
    return scheduled.finally(() => {
      if (this.sharedMutations.get(key) === scheduled) {
        this.sharedMutations.delete(key);
      }
    });
  }

  getState(): LifecycleQueueState {
    return {
      busy: Boolean(this.inFlightMutation),
      inFlight: this.inFlightMutation
        ? {
            key: this.inFlightMutation.key,
            action: this.inFlightMutation.action,
            reason: this.inFlightMutation.reason,
            startedAt: new Date(this.inFlightMutation.startedAt).toISOString(),
          }
        : null,
      sharedKeys: Array.from(this.sharedMutations.keys()),
    };
  }

  async ensureGatewayReady(
    task: () => Promise<GatewayEnsureRunningResult>,
    reason = 'ensure-ready'
  ): Promise<GatewayEnsureRunningResult> {
    const key = 'ensure:strict';
    return this.runSharedLifecycleMutation(key, 'ensure', reason, task);
  }

  async startGateway(
    task: () => Promise<CliResult>,
    reason = 'start'
  ): Promise<CliResult> {
    return this.runSharedLifecycleMutation('start', 'start', reason, task);
  }

  async restartGateway(
    task: () => Promise<CliResult>,
    reason = 'restart'
  ): Promise<CliResult> {
    return this.runSharedLifecycleMutation('restart', 'restart', reason, task);
  }

  async reloadGatewayForConfigChange(
    task: () => Promise<GatewayReloadResult>,
    reason: string
  ): Promise<GatewayReloadResult> {
    return this.runSharedLifecycleMutation('reload', 'reload', reason, task);
  }

  async stopGateway(
    task: () => Promise<CliResult>,
    reason = 'stop'
  ): Promise<CliResult> {
    return this.runSharedLifecycleMutation('stop', 'stop', reason, task);
  }
}
