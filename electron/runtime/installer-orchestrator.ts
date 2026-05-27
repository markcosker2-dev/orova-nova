import type { GatewayManager } from '../gateway/manager';
import { getAllSettings, setSetting } from '../utils/store';
import { logger } from '../utils/logger';
import { HermesStandaloneAdapter } from './adapters/hermes-standalone-adapter';
import { OpenClawHostAdapter } from './adapters/openclaw-host-adapter';
import { HermesOpenClawBridge } from './services/hermes-openclaw-bridge-service';
import { getHermesStandaloneManager } from './services/hermes-standalone-manager';
import type {
  InstallChoice,
  RuntimeInstallStepId,
  RuntimeInstallStepKind,
  RuntimeInstallStepStatus,
} from './types';
import { buildRuntimeInstallState } from './services/runtime-install-orchestrator';
import { getRuntimeFoundationSnapshot, type RuntimeFoundationSnapshot } from './services/runtime-status-service';

interface RuntimeInstallEventBus {
  emit(eventName: string, payload: unknown): void;
}

export interface RuntimeInstallStep {
  id: RuntimeInstallStepId;
  kind: RuntimeInstallStepKind;
  status: RuntimeInstallStepStatus;
  label: string;
  error?: string;
}

export interface RuntimeInstallResult {
  success: boolean;
  installChoice: InstallChoice;
  steps: RuntimeInstallStep[];
  snapshot: RuntimeFoundationSnapshot;
  error?: string;
}

export interface RuntimeInstallProgressEvent {
  installChoice: InstallChoice;
  activeStepId: RuntimeInstallStepId;
  steps: RuntimeInstallStep[];
}

function buildInstallSteps(installChoice: InstallChoice): RuntimeInstallStep[] {
  return [
    {
      id: 'openclaw',
      kind: 'runtime',
      status: installChoice === 'hermes' ? 'skipped' : 'pending',
      label: 'OpenClaw runtime installation',
    },
    {
      id: 'hermes',
      kind: 'runtime',
      status: installChoice === 'openclaw' ? 'skipped' : 'pending',
      label: 'Hermes runtime installation',
    },
    {
      id: 'bridge',
      kind: 'bridge',
      status: installChoice === 'both' ? 'pending' : 'skipped',
      label: 'Hermes as OpenClaw agent bridge preparation',
    },
  ];
}

function cloneSteps(steps: RuntimeInstallStep[]): RuntimeInstallStep[] {
  return steps.map((step) => ({ ...step }));
}

function updateStep(
  steps: RuntimeInstallStep[],
  stepId: RuntimeInstallStepId,
  updater: (step: RuntimeInstallStep) => RuntimeInstallStep,
): RuntimeInstallStep[] {
  return steps.map((step) => (step.id === stepId ? updater(step) : step));
}

function isMissingHermesRuntimeManifestEntry(error: unknown): boolean {
  return error instanceof Error
    && error.message.includes('Hermes runtime manifest entry was not found');
}

export class InstallerOrchestrator {
  constructor(
    private readonly gatewayManager: GatewayManager,
    private readonly readSettings: typeof getAllSettings = getAllSettings,
    private readonly writeSetting: typeof setSetting = setSetting,
    private readonly readSnapshot: typeof getRuntimeFoundationSnapshot = getRuntimeFoundationSnapshot,
    private readonly eventBus?: RuntimeInstallEventBus,
  ) {}

  async install(installChoice: InstallChoice): Promise<RuntimeInstallResult> {
    let steps = cloneSteps(buildInstallSteps(installChoice));
    let degradedBridgeError: string | undefined;
    let refreshedBridgeStatus:
      | {
          enabled: boolean;
          attached: boolean;
          hermesInstalled: boolean;
          hermesHealthy: boolean;
          openclawRecognized: boolean;
          reasonCode?: string;
          lastSyncAt?: number;
          error?: string;
        }
      | undefined;

    const emitProgress = (activeStepId: RuntimeInstallStepId) => {
      this.eventBus?.emit('runtime:install:progress', {
        installChoice,
        activeStepId,
        steps: cloneSteps(steps),
      } satisfies RuntimeInstallProgressEvent);
    };

    const markStep = (
      stepId: RuntimeInstallStepId,
      status: RuntimeInstallStepStatus,
      error?: string,
    ) => {
      steps = updateStep(steps, stepId, (step) => ({
        ...step,
        status,
        error,
      }));
      emitProgress(stepId);
    };

    const startStep = (stepId: RuntimeInstallStepId) => {
      const target = steps.find((step) => step.id === stepId);
      if (!target || target.status === 'skipped') return;
      markStep(stepId, 'installing');
    };

    let settings = await this.readSettings();
    const openclawAdapter = new OpenClawHostAdapter(this.gatewayManager);
    const hermesAdapter = new HermesStandaloneAdapter(undefined, getHermesStandaloneManager());
    const bridgeService = new HermesOpenClawBridge(this.gatewayManager);

    try {
      if (installChoice !== 'hermes') {
        startStep('openclaw');
        await openclawAdapter.start();
        markStep('openclaw', 'completed');
      }

      if (installChoice !== 'openclaw') {
        startStep('hermes');
        try {
          await hermesAdapter.start();
        } catch (error) {
          if (!isMissingHermesRuntimeManifestEntry(error)) {
            throw error;
          }

          logger.warn(
            'Hermes install completed without starting the runtime because no launchable Hermes runtime is installed yet. Finish Hermes prerequisites, then start Hermes from Settings when ready.',
          );
        }
        markStep('hermes', 'completed');
      }

      if (installChoice === 'both') {
        startStep('bridge');
        try {
          await bridgeService.attach();
          refreshedBridgeStatus = await bridgeService.recheck();
          markStep('bridge', 'completed');
          settings = await this.readSettings();
        } catch (error) {
          degradedBridgeError = error instanceof Error ? error.message : String(error);
          markStep('bridge', 'failed', degradedBridgeError);
        }
      }

      const nextState = buildRuntimeInstallState(
        {
          runtime: settings.runtime,
          bridge: settings.bridge,
        },
        installChoice,
      );

      await this.writeSetting('runtime', nextState.runtime);
      await this.writeSetting('bridge', refreshedBridgeStatus
        ? {
            ...nextState.bridge,
            hermesAsOpenClawAgent: {
              ...nextState.bridge.hermesAsOpenClawAgent,
              enabled: refreshedBridgeStatus.enabled,
              attached: refreshedBridgeStatus.attached,
              hermesInstalled: refreshedBridgeStatus.hermesInstalled,
              hermesHealthy: refreshedBridgeStatus.hermesHealthy,
              openclawRecognized: refreshedBridgeStatus.openclawRecognized,
              reasonCode: refreshedBridgeStatus.reasonCode,
              lastSyncAt: refreshedBridgeStatus.lastSyncAt,
              lastError: refreshedBridgeStatus.error,
            },
          }
        : degradedBridgeError
          ? {
              ...nextState.bridge,
              hermesAsOpenClawAgent: {
                ...nextState.bridge.hermesAsOpenClawAgent,
                enabled: true,
                attached: false,
                hermesInstalled: true,
                hermesHealthy: false,
                openclawRecognized: false,
                lastError: degradedBridgeError,
              },
            }
        : nextState.bridge);

      return {
        success: true,
        installChoice,
        steps,
        snapshot: await this.readSnapshot(this.gatewayManager),
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const activeStep = [...steps].reverse().find((step) => step.status === 'installing');
      if (activeStep) {
        markStep(activeStep.id, 'failed', message);
      }

      return {
        success: false,
        installChoice,
        steps,
        snapshot: await this.readSnapshot(this.gatewayManager),
        error: message,
      };
    }
  }
}
