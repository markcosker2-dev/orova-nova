export type InstallChoice = 'openclaw' | 'hermes' | 'both';

export type RuntimeMode = 'openclaw' | 'hermes' | 'hermesclaw-both' | 'openclaw-with-hermes-agent';

export type RuntimeKind = 'openclaw' | 'hermes';

export type RuntimeInstallStepId = 'openclaw' | 'hermes' | 'bridge';

export type RuntimeInstallStepKind = 'runtime' | 'bridge';

export type RuntimeInstallStepStatus = 'pending' | 'installing' | 'completed' | 'failed' | 'skipped';

export type InstallMode = 'native' | 'wsl2';

export type HermesWindowsPreferredMode = InstallMode;

export interface InstallStatus {
  installed: boolean;
  version?: string;
  installPath?: string;
  installMode?: InstallMode;
}

export interface RuntimeStatus {
  kind: RuntimeKind;
  installed: boolean;
  running: boolean;
  healthy: boolean;
  version?: string;
  endpoint?: string;
  lastCheckedAt?: number;
  error?: string;
}

export type BridgeReasonCode =
  | 'bridge_disabled'
  | 'hermes_not_installed'
  | 'bridge_config_missing'
  | 'openclaw_gateway_stopped'
  | 'openclaw_recognition_pending'
  | 'openclaw_health_failed'
  | 'hermes_home_unreachable';

export interface BridgeStatus {
  enabled: boolean;
  attached: boolean;
  hermesInstalled: boolean;
  hermesHealthy: boolean;
  openclawRecognized: boolean;
  reasonCode?: BridgeReasonCode;
  lastSyncAt?: number;
  error?: string;
}

export interface RuntimeSettings {
  installChoice: InstallChoice;
  mode: RuntimeMode;
  installedKinds: RuntimeKind[];
  windowsHermesPreferredMode?: HermesWindowsPreferredMode;
  windowsHermesNativePath?: string;
  windowsHermesWslDistro?: string;
  lastStandaloneRuntime?: 'openclaw' | 'hermes';
}

export interface HermesAsOpenClawAgentSettings {
  enabled: boolean;
  attached: boolean;
  hermesInstalled?: boolean;
  hermesHealthy?: boolean;
  openclawRecognized?: boolean;
  reasonCode?: BridgeReasonCode;
  lastSyncAt?: number;
  lastError?: string;
}

export interface BridgeSettings {
  hermesAsOpenClawAgent: HermesAsOpenClawAgentSettings;
}
