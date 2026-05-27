/**
 * Settings State Store
 * Manages application settings
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import i18n from '@/i18n';
import { hostApiFetch } from '@/lib/host-api';
import { resolveSupportedLanguage } from '../../shared/language';

type Theme = 'light' | 'dark' | 'system';
type UpdateChannel = 'stable' | 'beta' | 'dev';
type InstallChoice = 'openclaw' | 'hermes' | 'both';
type RuntimeMode = 'openclaw' | 'hermes' | 'hermesclaw-both' | 'openclaw-with-hermes-agent';
type RuntimeKind = 'openclaw' | 'hermes';
type HermesWindowsPreferredMode = 'native' | 'wsl2';
type BridgeReasonCode =
  | 'bridge_disabled'
  | 'hermes_not_installed'
  | 'bridge_config_missing'
  | 'openclaw_gateway_stopped'
  | 'openclaw_recognition_pending'
  | 'openclaw_health_failed'
  | 'hermes_home_unreachable';

interface RuntimeSettingsState {
  installChoice: InstallChoice;
  mode: RuntimeMode;
  installedKinds: RuntimeKind[];
  windowsHermesPreferredMode?: HermesWindowsPreferredMode;
  windowsHermesNativePath?: string;
  windowsHermesWslDistro?: string;
  lastStandaloneRuntime?: 'openclaw' | 'hermes';
}

interface HermesAsOpenClawAgentSettingsState {
  enabled: boolean;
  attached: boolean;
  hermesInstalled?: boolean;
  hermesHealthy?: boolean;
  openclawRecognized?: boolean;
  reasonCode?: BridgeReasonCode;
  lastSyncAt?: number;
  lastError?: string;
}

interface BridgeSettingsState {
  hermesAsOpenClawAgent: HermesAsOpenClawAgentSettingsState;
}

interface SettingsSnapshot {
  // General
  theme: Theme;
  language: string;
  startMinimized: boolean;
  launchAtStartup: boolean;
  telemetryEnabled: boolean;

  // Gateway
  gatewayAutoStart: boolean;
  gatewayPort: number;
  proxyEnabled: boolean;
  proxyServer: string;
  proxyHttpServer: string;
  proxyHttpsServer: string;
  proxyAllServer: string;
  proxyBypassRules: string;

  // Update
  updateChannel: UpdateChannel;
  autoCheckUpdate: boolean;
  autoDownloadUpdate: boolean;

  // UI State
  sidebarCollapsed: boolean;
  devModeUnlocked: boolean;

  // Setup
  setupComplete: boolean;

  // Runtime
  runtime: RuntimeSettingsState;
  bridge: BridgeSettingsState;

  // OROVA Settings
  orovaBackendUrl: string;
  orovaApiKey: string;
  orovaRuntimeMode: 'orova' | 'openclaw' | 'combined';
  orovaAutoStart: boolean;
}

interface SettingsState extends SettingsSnapshot {
  // Actions
  init: () => Promise<void>;
  setTheme: (theme: Theme) => void;
  setLanguage: (language: string) => void;
  setStartMinimized: (value: boolean) => void;
  setLaunchAtStartup: (value: boolean) => void;
  setTelemetryEnabled: (value: boolean) => void;
  setGatewayAutoStart: (value: boolean) => void;
  setGatewayPort: (port: number) => void;
  setProxyEnabled: (value: boolean) => void;
  setProxyServer: (value: string) => void;
  setProxyHttpServer: (value: string) => void;
  setProxyHttpsServer: (value: string) => void;
  setProxyAllServer: (value: string) => void;
  setProxyBypassRules: (value: string) => void;
  setUpdateChannel: (channel: UpdateChannel) => void;
  setAutoCheckUpdate: (value: boolean) => void;
  setAutoDownloadUpdate: (value: boolean) => void;
  setSidebarCollapsed: (value: boolean) => void;
  setDevModeUnlocked: (value: boolean) => void;
  markSetupComplete: () => void;
  resetSettings: () => void;

  setOrovaBackendUrl: (url: string) => void;
  setOrovaApiKey: (key: string) => void;
  setOrovaRuntimeMode: (mode: 'orova' | 'openclaw' | 'combined') => void;
  setOrovaAutoStart: (value: boolean) => void;
}

const defaultSettings: SettingsSnapshot = {
  theme: 'system' as Theme,
  language: resolveSupportedLanguage(typeof navigator !== 'undefined' ? navigator.language : undefined),
  startMinimized: false,
  launchAtStartup: false,
  telemetryEnabled: true,
  gatewayAutoStart: true,
  gatewayPort: 18789,
  proxyEnabled: false,
  proxyServer: '',
  proxyHttpServer: '',
  proxyHttpsServer: '',
  proxyAllServer: '',
  proxyBypassRules: '<local>;localhost;127.0.0.1;::1',
  updateChannel: 'stable' as UpdateChannel,
  autoCheckUpdate: true,
  autoDownloadUpdate: false,
  sidebarCollapsed: false,
  devModeUnlocked: false,
  setupComplete: false,
  runtime: {
    installChoice: 'both',
    mode: 'hermesclaw-both',
    installedKinds: ['openclaw', 'hermes'],
    windowsHermesPreferredMode: 'wsl2',
    lastStandaloneRuntime: 'openclaw',
  },
  bridge: {
    hermesAsOpenClawAgent: {
      enabled: true,
      attached: false,
    },
  },
  orovaBackendUrl: 'http://127.0.0.1:18790',
  orovaApiKey: 'nova_admin_2026',
  orovaRuntimeMode: 'combined',
  orovaAutoStart: true,
};

export { defaultSettings };

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      ...defaultSettings,

      init: async () => {
        try {
          const settings = await hostApiFetch<Partial<SettingsSnapshot>>('/api/settings');
          const resolvedLanguage = settings.language
            ? resolveSupportedLanguage(settings.language)
            : undefined;
          set((state) => ({
            ...state,
            ...settings,
            ...(resolvedLanguage ? { language: resolvedLanguage } : {}),
          }));
          if (resolvedLanguage) {
            i18n.changeLanguage(resolvedLanguage);
          }
        } catch {
          // Keep renderer-persisted settings as a fallback when the main
          // process store is not reachable.
        }
      },

      setTheme: (theme) => {
        set({ theme });
        void hostApiFetch('/api/settings/theme', {
          method: 'PUT',
          body: JSON.stringify({ value: theme }),
        }).catch(() => { });
      },
      setLanguage: (language) => {
        const resolvedLanguage = resolveSupportedLanguage(language);
        i18n.changeLanguage(resolvedLanguage);
        set({ language: resolvedLanguage });
        void hostApiFetch('/api/settings/language', {
          method: 'PUT',
          body: JSON.stringify({ value: resolvedLanguage }),
        }).catch(() => { });
      },
      setStartMinimized: (startMinimized) => set({ startMinimized }),
      setLaunchAtStartup: (launchAtStartup) => {
        set({ launchAtStartup });
        void hostApiFetch('/api/settings/launchAtStartup', {
          method: 'PUT',
          body: JSON.stringify({ value: launchAtStartup }),
        }).catch(() => { });
      },
      setTelemetryEnabled: (telemetryEnabled) => {
        set({ telemetryEnabled });
        void hostApiFetch('/api/settings/telemetryEnabled', {
          method: 'PUT',
          body: JSON.stringify({ value: telemetryEnabled }),
        }).catch(() => { });
      },
      setGatewayAutoStart: (gatewayAutoStart) => {
        set({ gatewayAutoStart });
        void hostApiFetch('/api/settings/gatewayAutoStart', {
          method: 'PUT',
          body: JSON.stringify({ value: gatewayAutoStart }),
        }).catch(() => { });
      },
      setGatewayPort: (gatewayPort) => {
        set({ gatewayPort });
        void hostApiFetch('/api/settings/gatewayPort', {
          method: 'PUT',
          body: JSON.stringify({ value: gatewayPort }),
        }).catch(() => { });
      },
      setProxyEnabled: (proxyEnabled) => set({ proxyEnabled }),
      setProxyServer: (proxyServer) => set({ proxyServer }),
      setProxyHttpServer: (proxyHttpServer) => set({ proxyHttpServer }),
      setProxyHttpsServer: (proxyHttpsServer) => set({ proxyHttpsServer }),
      setProxyAllServer: (proxyAllServer) => set({ proxyAllServer }),
      setProxyBypassRules: (proxyBypassRules) => set({ proxyBypassRules }),
      setUpdateChannel: (updateChannel) => set({ updateChannel }),
      setAutoCheckUpdate: (autoCheckUpdate) => set({ autoCheckUpdate }),
      setAutoDownloadUpdate: (autoDownloadUpdate) => set({ autoDownloadUpdate }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setDevModeUnlocked: (devModeUnlocked) => {
        set({ devModeUnlocked });
        void hostApiFetch('/api/settings/devModeUnlocked', {
          method: 'PUT',
          body: JSON.stringify({ value: devModeUnlocked }),
        }).catch(() => { });
      },
      markSetupComplete: () => set({ setupComplete: true }),
      resetSettings: () => set(defaultSettings),

      setOrovaBackendUrl: (orovaBackendUrl) => {
        set({ orovaBackendUrl });
        void hostApiFetch('/api/settings/orovaBackendUrl', {
          method: 'PUT',
          body: JSON.stringify({ value: orovaBackendUrl }),
        }).catch(() => { });
      },
      setOrovaApiKey: (orovaApiKey) => {
        set({ orovaApiKey });
        void hostApiFetch('/api/settings/orovaApiKey', {
          method: 'PUT',
          body: JSON.stringify({ value: orovaApiKey }),
        }).catch(() => { });
      },
      setOrovaRuntimeMode: (orovaRuntimeMode) => {
        set({ orovaRuntimeMode });
        void hostApiFetch('/api/settings/orovaRuntimeMode', {
          method: 'PUT',
          body: JSON.stringify({ value: orovaRuntimeMode }),
        }).catch(() => { });
      },
      setOrovaAutoStart: (orovaAutoStart) => {
        set({ orovaAutoStart });
        void hostApiFetch('/api/settings/orovaAutoStart', {
          method: 'PUT',
          body: JSON.stringify({ value: orovaAutoStart }),
        }).catch(() => { });
      },
    }),
    {
      name: 'hermesclaw-settings',
    }
  )
);
