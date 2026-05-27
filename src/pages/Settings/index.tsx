/**
 * Settings Page
 * Application configuration
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Sun,
  Moon,
  Monitor,
  RefreshCw,
  ExternalLink,
  FileText,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { useSettingsStore } from '@/stores/settings';
import { useGatewayStore } from '@/stores/gateway';
import { useUpdateStore } from '@/stores/update';
import {
  invokeIpc,
  toUserMessage,
} from '@/lib/api-client';
import { useTranslation } from 'react-i18next';
import { SUPPORTED_LANGUAGES } from '@/i18n';
import {
  applyOpenClawUpdate,
  attachHermesOpenClawBridge,
  checkOpenClawUpdate,
  detachHermesOpenClawBridge,
  getHermesClawLocalStatus,
  getHermesClawSharedConfig,
  getRuntimeStatus,
  hostApiFetch,
  installRuntime,
  restartOpenClawRuntime,
  recheckHermesOpenClawBridge,
  restartHermesRuntime,
  repairHermesClawInstallation,
  rollbackOpenClawRuntime,
  runHermesClawDoctor,
  startOpenClawRuntime,
  startHermesRuntime,
  stopOpenClawRuntime,
  stopHermesRuntime,
  type HermesClawDoctorResult,
  type HermesClawLocalStatus,
  type HermesClawSharedConfigRegistry,
  type RuntimeInstallResult,
  type RuntimeStatusSnapshot,
} from '@/lib/host-api';
import { cn } from '@/lib/utils';

type SettingsTab = 'overview' | 'appearance' | 'runtime' | 'updates' | 'integration' | 'advanced' | 'about';

const settingsTabs: Array<{ id: SettingsTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'appearance', label: 'Appearance & Startup' },
  { id: 'runtime', label: 'Runtime' },
  { id: 'updates', label: 'Updates' },
  { id: 'integration', label: 'HermesClaw Integration' },
  { id: 'advanced', label: 'Advanced & Diagnostics' },
  { id: 'about', label: 'About' },
];

export function Settings() {
  const { t } = useTranslation('settings');
  const [_autoCheckUpdate, _setAutoCheckUpdate] = useSettingsStore((state) => [state.autoCheckUpdate, state.setAutoCheckUpdate]);
  const [_autoDownloadUpdate, _setAutoDownloadUpdate] = useSettingsStore((state) => [state.autoDownloadUpdate, state.setAutoDownloadUpdate]);
  const [_openClawUpdateResult, _setOpenClawUpdateResult] = useSettingsStore((state) => [state.updateChannel, state.setUpdateChannel]);

  const { status: gatewayStatus, restart: restartGateway } = useGatewayStore();
  const currentVersion = useUpdateStore((state) => state.currentVersion);
  const [_updateSetAutoDownload, _setUpdateAutoDownload] = useUpdateStore((state) => [state.setAutoDownload, state.setAutoDownload]);

const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatusSnapshot | null>(null);
  const [hermesClawStatus, setHermesClawStatus] = useState<HermesClawLocalStatus | null>(null);
  const [hermesClawDoctorResult, setHermesClawDoctorResult] = useState<HermesClawDoctorResult | null>(null);
  const [hermesClawSharedConfig, setHermesClawSharedConfig] = useState<HermesClawSharedConfigRegistry | null>(null);

const [runtimeStatusLoading, setRuntimeStatusLoading] = useState(false);
  const [runtimeStatusError, setRuntimeStatusError] = useState<string | null>(null);
  const runtimeStatusRefreshInFlightRef = useRef<Promise<void> | null>(null);
  const [bridgeActionLoading, setBridgeActionLoading] = useState<'attach' | 'detach' | 'recheck' | null>(null);
  const [openClawRuntimeActionLoading, setOpenClawRuntimeActionLoading] = useState<'install' | 'start' | 'stop' | 'restart' | 'check-update' | 'apply-update' | 'rollback' | null>(null);
  const [hermesRuntimeActionLoading, setHermesRuntimeActionLoading] = useState<'install' | 'start' | 'stop' | 'restart' | null>(null);
  const [hermesClawActionLoading, setHermesClawActionLoading] = useState<'doctor' | 'repair' | null>(null);
  const [runtimeConfigSaving, setRuntimeConfigSaving] = useState(false);
  const [windowsHermesPreferredModeDraft, setWindowsHermesPreferredModeDraft] = useState<'native' | 'wsl2'>('wsl2');
  const [windowsHermesNativePathDraft, setWindowsHermesNativePathDraft] = useState('');
  const [windowsHermesWslDistroDraft, setWindowsHermesWslDistroDraft] = useState('');
  const [orovaBackendUrlDraft, setOrovaBackendUrlDraft] = useState('');
  const [orovaApiKeyDraft, setOrovaApiKeyDraft] = useState('');
const [savingOrova, setSavingOrova] = useState(false);

  const isWindows = window.electron.platform === 'win32';
  const [showLogs, setShowLogs] = useState(false);
  const [logContent, setLogContent] = useState('');

  const [theme, setTheme] = useSettingsStore((state) => [state.theme, state.setTheme]);
  const [language, setLanguage] = useSettingsStore((state) => [state.language, state.setLanguage]);
  const [launchAtStartup, setLaunchAtStartup] = useSettingsStore((state) => [state.launchAtStartup, state.setLaunchAtStartup]);
  const [gatewayAutoStart, setGatewayAutoStart] = useSettingsStore((state) => [state.gatewayAutoStart, state.setGatewayAutoStart]);
  const [orovaBackendUrl, setOrovaBackendUrl] = useSettingsStore((state) => [state.orovaBackendUrl, state.setOrovaBackendUrl]);
  const [orovaApiKey, setOrovaApiKey] = useSettingsStore((state) => [state.orovaApiKey, state.setOrovaApiKey]);
  const [devModeUnlocked, setDevModeUnlocked] = useSettingsStore((state) => [state.devModeUnlocked, state.setDevModeUnlocked]);
  const [telemetryEnabled, setTelemetryEnabled] = useSettingsStore((state) => [state.telemetryEnabled, state.setTelemetryEnabled]);

  const handleShowLogs = async () => {
    try {
      const logs = await hostApiFetch<{ content: string }>('/api/logs?tailLines=100');
      setLogContent(logs.content);
      setShowLogs(true);
    } catch {
      setLogContent('(Failed to load logs)');
      setShowLogs(true);
    }
  };

  const handleOpenLogDir = async () => {
    try {
      const { dir: logDir } = await hostApiFetch<{ dir: string | null }>('/api/logs/dir');
      if (logDir) {
        await invokeIpc('shell:showItemInFolder', logDir);
      }
    } catch {
      // ignore
    }
  };

  const refreshRuntimeStatus = useCallback(async () => {
    if (runtimeStatusRefreshInFlightRef.current) {
      return runtimeStatusRefreshInFlightRef.current;
    }

    const refreshPromise = (async () => {
      setRuntimeStatusLoading(true);
      try {
        const [result, localStatus, sharedConfig] = await Promise.all([
          getRuntimeStatus(),
          getHermesClawLocalStatus(),
          getHermesClawSharedConfig(),
        ]);
        setRuntimeStatus(result);
        setHermesClawStatus(localStatus);
        setHermesClawSharedConfig(sharedConfig);
        setRuntimeStatusError(null);
      } catch (error) {
        setRuntimeStatusError(toUserMessage(error) || t('gateway.runtimeStatusLoadFailed'));
      } finally {
        setRuntimeStatusLoading(false);
      }
    })();

    runtimeStatusRefreshInFlightRef.current = refreshPromise;
    try {
      return await refreshPromise;
    } finally {
      if (runtimeStatusRefreshInFlightRef.current === refreshPromise) {
        runtimeStatusRefreshInFlightRef.current = null;
      }
    }
  }, [t]);

  const refreshHermesClawStatus = useCallback(async () => {
    const [localStatus, sharedConfig] = await Promise.all([
      getHermesClawLocalStatus(),
      getHermesClawSharedConfig(),
    ]);
    setHermesClawStatus(localStatus);
    setHermesClawSharedConfig(sharedConfig);
  }, []);

  const handleHermesClawDoctor = async () => {
    setHermesClawActionLoading('doctor');
    try {
      const result = await runHermesClawDoctor();
      setHermesClawDoctorResult(result);
      toast.success(result.ok ? 'HermesClaw doctor completed' : 'HermesClaw doctor completed with warnings');
    } catch (error) {
      toast.error(toUserMessage(error) || 'Failed to run HermesClaw doctor');
    } finally {
      setHermesClawActionLoading(null);
    }
  };

  const handleHermesClawRepair = async () => {
    setHermesClawActionLoading('repair');
    try {
      const result = await repairHermesClawInstallation();
      setHermesClawDoctorResult(result.doctor);
      await refreshHermesClawStatus();
      if (result.success) {
        toast.success(`HermesClaw repair completed (${result.repaired.length} actions)`);
      } else {
        toast.error(result.doctor.repairPlan[0] ?? 'HermesClaw repair completed with remaining issues');
      }
} catch (error) {
      toast.error(toUserMessage(error) || 'Failed to repair HermesClaw installation');
    } finally {
      setHermesClawActionLoading(null);
    }
  };

  const applyRuntimeInstallResult = async (result: RuntimeInstallResult) => {
    setRuntimeStatus(result.snapshot);
    await refreshHermesClawStatus();
    if (!result.success) {
      throw new Error(result.error ?? 'Runtime installation failed');
    }
  };

  const handleRuntimeInstall = async (_runtimeKind: 'openclaw' | 'hermes') => {
    const installChoice = 'both';
    setOpenClawRuntimeActionLoading('install');
    setHermesRuntimeActionLoading('install');

    try {
      const result = await installRuntime(installChoice);
      await applyRuntimeInstallResult(result);
      toast.success('OpenClaw + Hermes runtime install completed');
    } catch (error) {
      toast.error(toUserMessage(error) || 'Failed to install OpenClaw + Hermes runtime');
    } finally {
      setOpenClawRuntimeActionLoading(null);
      setHermesRuntimeActionLoading(null);
    }
  };

  const handleHermesRuntimeAction = async (action: 'start' | 'stop' | 'restart') => {
    setHermesRuntimeActionLoading(action);
    try {
      const result = action === 'start'
        ? await startHermesRuntime()
        : action === 'stop'
          ? await stopHermesRuntime()
          : await restartHermesRuntime();
      if (!result.success) {
        throw new Error(result.error ?? `Hermes runtime ${action} failed`);
      }
      setRuntimeStatus(result.snapshot);
      await refreshHermesClawStatus();
      toast.success(`Hermes runtime ${action} completed`);
    } catch (error) {
      toast.error(toUserMessage(error) || `Failed to ${action} Hermes runtime`);
    } finally {
      setHermesRuntimeActionLoading(null);
    }
  };

  const handleOpenClawRuntimeAction = async (action: 'start' | 'stop' | 'restart' | 'check-update' | 'apply-update' | 'rollback') => {
    setOpenClawRuntimeActionLoading(action);
    try {
      if (action === 'start' || action === 'stop' || action === 'restart') {
        const result = action === 'start'
          ? await startOpenClawRuntime()
          : action === 'stop'
            ? await stopOpenClawRuntime()
            : await restartOpenClawRuntime();
if (!result.success) {
          throw new Error(result.error ?? `OpenClaw runtime ${action} failed`);
        }
        setRuntimeStatus(result.snapshot);
        toast.success(`OpenClaw runtime ${action} completed`);
        return;
      }

      const result = action === 'check-update'
        ? await checkOpenClawUpdate()
        : action === 'apply-update'
          ? await applyOpenClawUpdate()
          : await rollbackOpenClawRuntime();
      setRuntimeStatus(result.snapshot);
      if (result.success === false) {
        toast.error(result.error ?? 'OpenClaw runtime management action failed');
      } else {
        toast.success('OpenClaw runtime management action completed');
      }
    } catch (error) {
      toast.error(toUserMessage(error) || `Failed to ${action} OpenClaw runtime`);
    } finally {
      setOpenClawRuntimeActionLoading(null);
    }
  };

  const handleBridgeAction = async (action: 'attach' | 'detach' | 'recheck') => {
    setBridgeActionLoading(action);
    try {
      if (action === 'attach') {
        await attachHermesOpenClawBridge();
      } else if (action === 'detach') {
        await detachHermesOpenClawBridge();
      } else {
        await recheckHermesOpenClawBridge();
      }
      await refreshRuntimeStatus();
      toast.success(
        action === 'attach'
          ? t('gateway.bridgeAttachSucceeded')
          : action === 'detach'
            ? 'Bridge disconnected'
            : t('gateway.bridgeRecheckSucceeded'),
      );
    } catch (error) {
      toast.error(toUserMessage(error) || t('gateway.runtimeStatusLoadFailed'));
    } finally {
      setBridgeActionLoading(null);
    }
  };

  const runtimeConfigSource = runtimeStatus?.runtime ?? { windowsHermesPreferredMode: 'wsl2', windowsHermesNativePath: undefined, windowsHermesWslDistro: undefined };

  useEffect(() => {
    setWindowsHermesPreferredModeDraft(runtimeConfigSource.windowsHermesPreferredMode ?? 'wsl2');
    setWindowsHermesNativePathDraft(runtimeConfigSource.windowsHermesNativePath ?? '');
    setWindowsHermesWslDistroDraft(runtimeConfigSource.windowsHermesWslDistro ?? '');
  }, [
    runtimeConfigSource.windowsHermesNativePath,
    runtimeConfigSource.windowsHermesPreferredMode,
    runtimeConfigSource.windowsHermesWslDistro,
  ]);

  const runtimeConfigDirty = useMemo(() => {
    return (
      (windowsHermesPreferredModeDraft ?? 'wsl2') !== (runtimeConfigSource.windowsHermesPreferredMode ?? 'wsl2')
      || windowsHermesNativePathDraft.trim() !== (runtimeConfigSource.windowsHermesNativePath ?? '')
      || windowsHermesWslDistroDraft.trim() !== (runtimeConfigSource.windowsHermesWslDistro ?? '')
    );
  }, [
    runtimeConfigSource.windowsHermesNativePath,
    runtimeConfigSource.windowsHermesPreferredMode,
    runtimeConfigSource.windowsHermesWslDistro,
    windowsHermesNativePathDraft,
    windowsHermesPreferredModeDraft,
    windowsHermesWslDistroDraft,
  ]);

  const handleSaveWindowsHermesRuntimeConfig = async () => {
    setRuntimeConfigSaving(true);
    try {
      const nextRuntime = {
        ...runtimeConfigSource,
        windowsHermesPreferredMode: windowsHermesPreferredModeDraft,
        windowsHermesNativePath: windowsHermesNativePathDraft.trim() || undefined,
        windowsHermesWslDistro: windowsHermesWslDistroDraft.trim() || undefined,
      };

      await hostApiFetch('/api/settings/runtime', {
        method: 'PUT',
        body: JSON.stringify({ value: nextRuntime }),
      });

      await refreshRuntimeStatus();
      toast.success(t('gateway.runtimeWindowsConfigSaved'));
    } catch (error) {
      toast.error(toUserMessage(error) || t('gateway.runtimeWindowsConfigSaveFailed'));
    } finally {
      setRuntimeConfigSaving(false);
    }
  };

  useEffect(() => {
    void refreshRuntimeStatus();
  }, [gatewayStatus.gatewayReady, gatewayStatus.state, refreshRuntimeStatus]);

  useEffect(() => {
    const unsubscribe = window.electron.ipcRenderer.on(
      'openclaw:cli-installed',
      (...args: unknown[]) => {
        const installedPath = typeof args[0] === 'string' ? args[0] : '';
        toast.success(`openclaw CLI installed at ${installedPath}`);
      },
    );
    return () => { unsubscribe?.(); };
  }, []);

  const [activeTab, setActiveTab] = useState<SettingsTab>('overview');

  const openClawRuntime = runtimeStatus?.runtimes.find((r) => r.kind === 'openclaw');
  const hermesRuntime = runtimeStatus?.runtimes.find((r) => r.kind === 'hermes');

  const hermesAgentVersion = hermesRuntime?.version;

  const bridgeStateLabel = useMemo(() => {
    if (!runtimeStatus) return '—';
    const { bridge } = runtimeStatus;
    if (bridge.enabled && bridge.attached) return t('gateway.bridgeStates.connected');
    if (bridge.enabled && !bridge.attached) return t('gateway.bridgeStates.disconnected');
    return t('gateway.bridgeStates.disabled');
  }, [runtimeStatus, t]);

  const runtimeModeLabel = useMemo(() => {
    const mode = runtimeStatus?.runtime.mode;
    if (!mode) return '—';
    const labels: Record<string, string> = {
      openclaw: t('gateway.runtimeModes.openclaw'),
      hermes: t('gateway.runtimeModes.hermes'),
      'hermesclaw-both': t('gateway.runtimeModes.hermesclawBoth'),
      'openclaw-with-hermes-agent': t('gateway.runtimeModes.openclawWithHermesAgent'),
    };
    return labels[mode] ?? mode;
  }, [runtimeStatus, t]);

  const hermesPathDisplay = useMemo(() => {
    const isNative = runtimeStatus?.runtime.windowsHermesPreferredMode === 'native';
    const nativePath = runtimeStatus?.runtime.windowsHermesNativePath;
    const wslDistro = runtimeStatus?.runtime.windowsHermesWslDistro;
    if (isNative && nativePath) return nativePath;
    if (!isNative && wslDistro) return `${wslDistro}:/home/${process.env.USER ?? 'user'}/.hermes`;
    return '$HOME/.hermes';
  }, [runtimeStatus]);

  const hermesClawActiveChannel = useMemo(() => {
    return hermesClawStatus?.runtimeState?.runtimes?.hermes?.channel ?? '—';
  }, [hermesClawStatus]);

  const hermesClawActiveRuntime = useMemo(() => {
    return hermesClawStatus?.runtimeState?.runtimes?.hermes;
  }, [hermesClawStatus]);

  const hermesClawDoctorSummary = useMemo(() => {
    if (!hermesClawDoctorResult?.checks) return null;
    const failed = hermesClawDoctorResult.checks.filter((c) => c.status === 'fail').length;
    const warned = hermesClawDoctorResult.checks.filter((c) => c.status === 'warn').length;
    return `${failed} failed, ${warned} warnings`;
  }, [hermesClawDoctorResult]);

  return (
    <div data-testid="settings-page" className="flex flex-col -m-6 dark:bg-background h-[calc(100vh-2.5rem)] overflow-hidden">
      <div className="w-full max-w-6xl mx-auto flex h-full">

        {/* Left Navigation */}
        <div className="w-64 border-r border-black/10 dark:border-white/10 flex flex-col p-6 space-y-1 shrink-0 overflow-y-auto">
          <h1 className="text-3xl font-serif text-foreground mb-8 font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
            {t('title')}
          </h1>
          {settingsTabs.map((tab) => (
            <button
              key={tab.id}
              data-testid={`settings-tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "text-left px-4 py-2 rounded-lg text-[15px] transition-colors",
                activeTab === tab.id
                  ? "bg-black/5 dark:bg-white/10 text-foreground font-medium"
                  : "text-foreground/70 hover:bg-black/5 dark:hover:bg-white/5"
              )}
            >
              {t(`tabs.${tab.id}`)}
            </button>
          ))}
        </div>

        {/* Right Content Area */}
        <div className="flex-1 overflow-y-auto p-10 pt-16 min-h-0">
          
          {activeTab === 'overview' && (
            <div className="space-y-12">
              <div className="mb-12">
                <h2 className="text-4xl font-serif text-foreground mb-3 font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>Overview</h2>
                <p className="text-[17px] text-foreground/70 font-medium">{t('subtitle')}</p>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-3">
                  <Label className="text-[13px] text-muted-foreground">Gateway</Label>
                  <div className="text-2xl font-serif text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                    {gatewayStatus.state}
                  </div>
                  <p className="text-[12px] text-muted-foreground">{t('gateway.port')}: {gatewayStatus.port}</p>
                </div>
                <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-3">
                  <Label className="text-[13px] text-muted-foreground">OpenClaw</Label>
                  <div className="text-2xl font-serif text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                    {runtimeStatus === null
                      ? <span className="inline-block w-20 h-7 rounded bg-foreground/10 animate-pulse" />
                      : openClawRuntime?.running ? t('common:running') : openClawRuntime?.installed ? t('common:stopped') : 'Not installed'}
                  </div>
                  <p className="text-[12px] text-muted-foreground">{runtimeStatus === null ? '—' : (openClawRuntime?.version ?? 'local')}</p>
                </div>
                <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-3">
                  <Label className="text-[13px] text-muted-foreground">HermesAgent</Label>
                  <div className="text-2xl font-serif text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                    {runtimeStatus === null
                      ? <span className="inline-block w-20 h-7 rounded bg-foreground/10 animate-pulse" />
                      : hermesRuntime?.running ? t('common:running') : hermesRuntime?.installed ? t('common:stopped') : 'Not installed'}
</div>
                <p className="text-[12px] text-muted-foreground">{runtimeStatus === null ? '—' : hermesAgentVersion}</p>
                </div>
                <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-3">
                  <Label className="text-[13px] text-muted-foreground">Bridge</Label>
                  <div className="text-2xl font-serif text-foreground" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                    {bridgeStateLabel}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'appearance' && (
            <section className="space-y-6">
              <h2 className="text-2xl md:text-3xl font-serif text-foreground font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                {t('appearance.title')}
              </h2>
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 flex flex-col divide-y divide-black/5 dark:divide-white/5">
                <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <Label className="text-[15px] font-medium text-foreground/90">{t('appearance.theme')}</Label>
                    <p className="text-[13px] text-muted-foreground mt-1">
                      {t('appearance.themeDesc')}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant={theme === 'light' ? 'secondary' : 'outline'}
                      className={cn("rounded-full px-5 h-10 border-black/10 dark:border-white/10", theme === 'light' ? "bg-black/5 dark:bg-white/10 text-foreground" : "bg-transparent text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5")}
                      onClick={() => setTheme('light')}
                    >
                      <Sun className="h-4 w-4 mr-2" />
                      {t('appearance.light')}
                    </Button>
                    <Button
                      variant={theme === 'dark' ? 'secondary' : 'outline'}
                      className={cn("rounded-full px-5 h-10 border-black/10 dark:border-white/10", theme === 'dark' ? "bg-black/5 dark:bg-white/10 text-foreground" : "bg-transparent text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5")}
                      onClick={() => setTheme('dark')}
                    >
                      <Moon className="h-4 w-4 mr-2" />
                      {t('appearance.dark')}
                    </Button>
                    <Button
                      variant={theme === 'system' ? 'secondary' : 'outline'}
                      className={cn("rounded-full px-5 h-10 border-black/10 dark:border-white/10", theme === 'system' ? "bg-black/5 dark:bg-white/10 text-foreground" : "bg-transparent text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5")}
                      onClick={() => setTheme('system')}
                    >
                      <Monitor className="h-4 w-4 mr-2" />
                      {t('appearance.system')}
                    </Button>
                  </div>
                </div>
                <div className="p-5 space-y-4">
                  <Label className="text-[15px] font-medium text-foreground/90">{t('appearance.language')}</Label>
                  <div className="flex flex-wrap gap-2">
{SUPPORTED_LANGUAGES.map((lang) => (
                      <Button
                        key={lang.code}
                        variant={language === lang.code ? 'secondary' : 'outline'}
                        className={cn("rounded-full px-5 h-10 border-black/10 dark:border-white/10", language === lang.code ? "bg-black/5 dark:bg-white/10 text-foreground" : "bg-transparent text-muted-foreground hover:bg-black/5 dark:hover:bg-white/5")}
                        onClick={() => setLanguage(lang.code)}
                      >
                        {lang.label}
                      </Button>
                    ))}
                  </div>
                  <div className="space-y-1 pt-4 border-t border-black/5 dark:border-white/5 mt-4">
                    <Label className="text-[15px] font-medium text-foreground/90">OROVA Backend</Label>
                    <p className="text-[12px] text-muted-foreground">Connect HermesClaw to OROVA's multi-agent engine</p>
                  </div>
                  <div className="pt-4">
                    <Switch
                      checked={launchAtStartup}
                      onCheckedChange={setLaunchAtStartup}
                    />
                  </div>
                </div>
              </div>

              <Separator className="bg-black/5 dark:bg-white/5" />
            </section>
)}

          {activeTab === 'runtime' && (
            <div className="space-y-12">
              <section className="space-y-6">
            <h2 className="text-2xl md:text-3xl font-serif text-foreground font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
              {t('gateway.title')}
            </h2>
            <div className="space-y-6">
              
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 flex flex-col divide-y divide-black/5 dark:divide-white/5">
                <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <Label className="text-[15px] font-medium text-foreground/90">{t('gateway.status')}</Label>
                    <p className="text-[13px] text-muted-foreground mt-1">
                      {t('gateway.port')}: {gatewayStatus.port}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className={cn(
                      "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[13px] font-medium border",
                      gatewayStatus.state === 'running' ? "bg-green-500/10 text-green-600 dark:text-green-500 border-green-500/20" :
                        gatewayStatus.state === 'error' ? "bg-red-500/10 text-red-600 dark:text-red-500 border-red-500/20" :
                          "bg-black/5 dark:bg-white/5 text-muted-foreground border-transparent"
                    )}>
                      <div className={cn("w-1.5 h-1.5 rounded-full",
                        gatewayStatus.state === 'running' ? "bg-green-500" :
                          gatewayStatus.state === 'error' ? "bg-red-500" : "bg-muted-foreground"
                      )} />
                      {gatewayStatus.state}
                    </div>
                    <Button variant="outline" size="sm" onClick={restartGateway} className="rounded-full h-8 px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5">
                      <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                      {t('common:actions.restart')}
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleShowLogs} className="rounded-full h-8 px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5">
                      <FileText className="h-3.5 w-3.5 mr-1.5" />
                      {t('gateway.logs')}
                    </Button>
                  </div>
                </div>

                <div className="p-5 flex items-center justify-between gap-4">
                  <div>
                    <Label className="text-[15px] font-medium text-foreground/90">{t('gateway.autoStart')}</Label>
                    <p className="text-[13px] text-muted-foreground mt-1">
                      {t('gateway.autoStartDesc')}
                    </p>
                  </div>
                  <Switch
                    checked={gatewayAutoStart}
                    onCheckedChange={setGatewayAutoStart}
                  />
                </div>
              </div>

              <div
                data-testid="settings-runtime-panel"
                className="rounded-2xl border border-black/10 dark:border-white/10 p-5 bg-black/5 dark:bg-white/5 space-y-4"
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div>
                    <Label className="text-[15px] font-medium text-foreground">{t('gateway.runtimeStatusTitle')}</Label>
                     {runtimeStatusError && (
                       <p className="text-[13px] text-muted-foreground mt-1" data-testid="settings-runtime-hint">
                         {runtimeStatusError}
                       </p>
                     )}
                     {!runtimeStatusError && !runtimeStatus && (
                       <p className="text-[13px] text-muted-foreground mt-1" data-testid="settings-runtime-hint">
                         {runtimeStatusLoading
                           ? t('gateway.runtimeStatusLoading')
                           : t('gateway.runtimeStatusUnavailable')}
                       </p>
                     )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void refreshRuntimeStatus()}
                    data-testid="settings-runtime-refresh-button"
                    className="rounded-full h-8 px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5"
                  >
                    <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', runtimeStatusLoading && 'animate-spin')} />
                    {t('gateway.runtimeStatusRefresh')}
                  </Button>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label className="text-[13px] text-foreground/80">{t('gateway.runtimeMode')}</Label>
                    <Badge
                      variant="outline"
                      className="rounded-full px-3 py-1 bg-white dark:bg-card border-black/5 dark:border-white/5"
                      data-testid="settings-runtime-mode-value"
                    >
                      {runtimeModeLabel}
                    </Badge>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[13px] text-foreground/80">{t('gateway.installedRuntimes')}</Label>
                    <div className="flex flex-wrap gap-2">
                      {runtimeStatus?.runtime.installedKinds.length ? runtimeStatus.runtime.installedKinds.map((kind) => (
                        <Badge
                          key={kind}
                          variant="outline"
                          className="rounded-full px-3 py-1 bg-white dark:bg-card border-black/5 dark:border-white/5"
                          data-testid={`settings-installed-runtime-${kind}`}
                        >
                          {kind === 'openclaw' ? t('gateway.runtimeLabels.openclaw') : t('gateway.runtimeLabels.hermes')}
                        </Badge>
                      )) : (
                        <span className="text-[13px] text-muted-foreground">—</span>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[13px] text-foreground/80">{t('gateway.hermesBridge')}</Label>
                    <Badge
                      variant="outline"
                      className="rounded-full px-3 py-1 bg-white dark:bg-card border-black/5 dark:border-white/5"
                      data-testid="settings-runtime-bridge-badge"
                    >
                      {bridgeStateLabel}
                    </Badge>
                  </div>
                </div>

                {runtimeStatus?.runtimes.length ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    {runtimeStatus.runtimes.map((runtime) => (
                      <div
                        key={runtime.kind}
                        className="rounded-2xl border border-black/5 dark:border-white/5 bg-white dark:bg-card p-4 space-y-2"
                        data-testid={`settings-runtime-entry-${runtime.kind}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <Label className="text-[13px] text-foreground/80">
                            {runtime.kind === 'openclaw' ? t('gateway.runtimeLabels.openclaw') : t('gateway.runtimeLabels.hermes')}
                          </Label>
                          <div className="flex flex-wrap gap-2 justify-end">
                            <Badge
                              variant="outline"
                              className="rounded-full px-3 py-1 bg-white dark:bg-card border-black/5 dark:border-white/5"
                            >
                              {runtime.running ? t('common:running') : t('common:stopped')}
                            </Badge>
                            <Badge
                              variant="outline"
                              className="rounded-full px-3 py-1 bg-white dark:bg-card border-black/5 dark:border-white/5"
                            >
                              {runtime.healthy ? t('gateway.runtimeHealthStates.healthy') : t('gateway.runtimeHealthStates.degraded')}
                            </Badge>
                          </div>
                        </div>

                        {runtime.endpoint && (
                          <p className="text-[12px] text-muted-foreground break-all">
                            {runtime.endpoint}
                          </p>
                        )}

                        {runtime.kind === 'hermes' && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            {!runtime.installed && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                data-testid="settings-runtime-hermes-install-button"
                                  disabled={hermesRuntimeActionLoading !== null || openClawRuntimeActionLoading !== null}
                                onClick={() => void handleRuntimeInstall('hermes')}
                                className="h-8 rounded-full px-3"
                              >
                                {hermesRuntimeActionLoading === 'install' ? (
                                  <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                ) : null}
                                Install
                              </Button>
                            )}
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              data-testid="settings-runtime-hermes-start-button"
                              disabled={!runtime.installed || runtime.running || hermesRuntimeActionLoading !== null}
                              onClick={() => void handleHermesRuntimeAction('start')}
                              className="h-8 rounded-full px-3"
                            >
                              {hermesRuntimeActionLoading === 'start' ? (
                                <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                              ) : null}
                              Start
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              data-testid="settings-runtime-hermes-stop-button"
                              disabled={!runtime.installed || !runtime.running || hermesRuntimeActionLoading !== null}
                              onClick={() => void handleHermesRuntimeAction('stop')}
                              className="h-8 rounded-full px-3"
                            >
                              Stop
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              data-testid="settings-runtime-hermes-restart-button"
                              disabled={!runtime.installed || hermesRuntimeActionLoading !== null}
                              onClick={() => void handleHermesRuntimeAction('restart')}
                              className="h-8 rounded-full px-3"
                            >
                              {hermesRuntimeActionLoading === 'restart' ? (
                                <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                              ) : null}
                              Restart
                            </Button>
                          </div>
                        )}

                        {runtime.kind === 'openclaw' && (
                          <div className="space-y-2 pt-1">
                            <div className="flex flex-wrap gap-2">
                              {!runtime.installed && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  data-testid="settings-runtime-openclaw-install-button"
                                  disabled={openClawRuntimeActionLoading !== null || hermesRuntimeActionLoading !== null}
                                  onClick={() => void handleRuntimeInstall('openclaw')}
                                  className="h-8 rounded-full px-3"
                                >
                                  {openClawRuntimeActionLoading === 'install' ? (
                                    <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                  ) : null}
                                  Install
                                </Button>
                              )}
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                data-testid="settings-runtime-openclaw-start-button"
                                disabled={!runtime.installed || runtime.running || openClawRuntimeActionLoading !== null}
                                onClick={() => void handleOpenClawRuntimeAction('start')}
                                className="h-8 rounded-full px-3"
                              >
                                {openClawRuntimeActionLoading === 'start' ? (
                                  <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                ) : null}
                                Start
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                data-testid="settings-runtime-openclaw-stop-button"
                                disabled={!runtime.installed || !runtime.running || openClawRuntimeActionLoading !== null}
                                onClick={() => void handleOpenClawRuntimeAction('stop')}
                                className="h-8 rounded-full px-3"
                              >
                                Stop
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                data-testid="settings-runtime-openclaw-restart-button"
                                disabled={!runtime.installed || openClawRuntimeActionLoading !== null}
                                onClick={() => void handleOpenClawRuntimeAction('restart')}
                                className="h-8 rounded-full px-3"
                              >
                                {openClawRuntimeActionLoading === 'restart' ? (
                                  <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                ) : null}
                                Restart
                              </Button>
                            </div>
                          </div>
                        )}

                        {runtime.error && (
                          <p className="text-[12px] text-muted-foreground">
                            {runtime.error}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}

                {isWindows && (
                  <div
                    data-testid="settings-runtime-config-panel"
                    className="rounded-2xl border border-black/5 dark:border-white/5 bg-white dark:bg-card p-4 space-y-4"
                  >
                    <div className="space-y-1">
                      <Label className="text-[13px] text-foreground/80">{t('gateway.runtimeWindowsConfigTitle')}</Label>
                      <p className="text-[12px] text-muted-foreground">{t('gateway.runtimeWindowsConfigHint')}</p>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-[13px] text-foreground/80">{t('gateway.runtimeWindowsMode')}</Label>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant={windowsHermesPreferredModeDraft === 'native' ? 'default' : 'outline'}
                          data-testid="settings-runtime-mode-native"
                          onClick={() => setWindowsHermesPreferredModeDraft('native')}
                          className="rounded-full h-8 px-4"
                        >
                          {t('gateway.runtimeWindowsModeOptions.native')}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant={windowsHermesPreferredModeDraft === 'wsl2' ? 'default' : 'outline'}
                          data-testid="settings-runtime-mode-wsl2"
                          onClick={() => setWindowsHermesPreferredModeDraft('wsl2')}
                          className="rounded-full h-8 px-4"
                        >
                          {t('gateway.runtimeWindowsModeOptions.wsl2')}
                        </Button>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="settings-runtime-native-path" className="text-[13px] text-foreground/80">
                        {t('gateway.runtimeWindowsNativePath')}
                      </Label>
                      <Input
                        id="settings-runtime-native-path"
                        data-testid="settings-runtime-native-path"
                        value={windowsHermesNativePathDraft}
                        onChange={(event) => setWindowsHermesNativePathDraft(event.target.value)}
                        placeholder="%USERPROFILE%\\.hermes"
                      />
                      <p className="text-[12px] text-muted-foreground">{t('gateway.runtimeWindowsNativePathHelp')}</p>
                      <p className="text-[12px] text-muted-foreground break-all" data-testid="settings-runtime-hermes-path-display">
                        Hermes default path: {hermesPathDisplay}
                      </p>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="settings-runtime-wsl-distro" className="text-[13px] text-foreground/80">
                        {t('gateway.runtimeWindowsWslDistro')}
                      </Label>
                      <Input
                        id="settings-runtime-wsl-distro"
                        data-testid="settings-runtime-wsl-distro"
                        value={windowsHermesWslDistroDraft}
                        onChange={(event) => setWindowsHermesWslDistroDraft(event.target.value)}
                        placeholder="Ubuntu-24.04"
                      />
                      <p className="text-[12px] text-muted-foreground">{t('gateway.runtimeWindowsWslDistroHelp')}</p>
                    </div>

                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[12px] text-muted-foreground">{t('gateway.runtimeWindowsConfigSaveHint')}</p>
                      <Button
                        type="button"
                        size="sm"
                        data-testid="settings-runtime-save-button"
                        disabled={!runtimeConfigDirty || runtimeConfigSaving}
                        onClick={() => void handleSaveWindowsHermesRuntimeConfig()}
                        className="rounded-full h-8 px-4"
                      >
                        <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', runtimeConfigSaving && 'animate-spin')} />
                        {runtimeConfigSaving ? t('common:status.saving') : t('common:actions.save')}
                      </Button>
                    </div>
                  </div>
                )}

                {runtimeStatus?.bridge.error && (
                  <p className="text-[12px] text-muted-foreground" data-testid="settings-runtime-bridge-error">
                    {runtimeStatus.bridge.error}
                  </p>
                )}

                {runtimeStatus?.bridge.enabled && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleBridgeAction('attach')}
                      data-testid="settings-runtime-bridge-attach-button"
                      disabled={bridgeActionLoading != null}
                      className="rounded-full h-8 px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5"
                    >
                      {t('gateway.bridgeAttach')}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleBridgeAction('detach')}
                      data-testid="settings-runtime-bridge-detach-button"
                      disabled={bridgeActionLoading != null || !runtimeStatus.bridge.attached}
                      className="rounded-full h-8 px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5"
                    >
                      {bridgeActionLoading === 'detach' ? (
                        <RefreshCw className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      ) : null}
                      Disconnect Bridge
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleBridgeAction('recheck')}
                      data-testid="settings-runtime-bridge-recheck-button"
                      disabled={bridgeActionLoading != null}
                      className="rounded-full h-8 px-4 border-black/10 dark:border-white/10 bg-transparent hover:bg-black/5 dark:hover:bg-white/5"
                    >
                      <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', bridgeActionLoading === 'recheck' && 'animate-spin')} />
                      {t('gateway.bridgeRecheck')}
                    </Button>
                  </div>
                )}
              </div>

              {showLogs && (
                <div className="p-4 rounded-2xl bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5">
                  <div className="flex items-center justify-between mb-3">
                    <p className="font-medium text-[14px]">{t('gateway.appLogs')}</p>
                    <div className="flex gap-2">
                      <Button variant="ghost" size="sm" className="h-7 text-[12px] rounded-full hover:bg-black/5 dark:hover:bg-white/10" onClick={handleOpenLogDir}>
                        <ExternalLink className="h-3 w-3 mr-1.5" />
                        {t('gateway.openFolder')}
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 text-[12px] rounded-full hover:bg-black/5 dark:hover:bg-white/10" onClick={() => setShowLogs(false)}>
                        {t('common:actions.close')}
                      </Button>
                    </div>
                  </div>
                  <pre className="text-[12px] text-muted-foreground bg-white dark:bg-card p-4 rounded-xl max-h-60 overflow-auto whitespace-pre-wrap font-mono border border-black/5 dark:border-white/5 shadow-inner">
                    {logContent || t('chat:noLogs')}
                  </pre>
                </div>
              )}

            </div>
          </section>
            </div>
          )}

          {activeTab === 'integration' && (
            <div className="space-y-12">
              <h2 className="text-2xl md:text-3xl font-serif text-foreground font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
HermesClaw Integration
              </h2>
              <div
                data-testid="settings-hermesclaw-panel"
                className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-5"
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div className="space-y-1">
                    <Label className="text-[15px] font-medium text-foreground/90">HermesClaw Local Integration</Label>
                    <p className="text-[12px] text-muted-foreground break-all" data-testid="settings-hermesclaw-root">
                      {hermesClawStatus?.layout.rootDir ?? '—'}
                    </p>
                  </div>
                  <Badge variant="outline" className="rounded-full px-3 py-1 bg-white dark:bg-card border-black/5 dark:border-white/5" data-testid="settings-hermesclaw-channel">
                     {hermesClawActiveChannel}
                   </Badge>
                 </div>

                 <div className="grid gap-3 md:grid-cols-4">
                   <div className="space-y-1 rounded-2xl border border-black/5 dark:border-white/5 bg-white dark:bg-card p-4">
                     <p className="text-[12px] text-muted-foreground">Active version</p>
                     <p className="text-[13px] text-foreground" data-testid="settings-hermesclaw-version">
                       {hermesClawActiveRuntime?.version ?? '—'}
                     </p>
                   </div>
                   <div className="space-y-1 rounded-2xl border border-black/5 dark:border-white/5 bg-white dark:bg-card p-4">
                     <p className="text-[12px] text-muted-foreground">Shared config</p>
                     <p className="text-[13px] text-foreground" data-testid="settings-hermesclaw-shared-config-count">
                       {(hermesClawSharedConfig?.skills.length ?? 0)
                         + (hermesClawSharedConfig?.agents.length ?? 0)
                         + (hermesClawSharedConfig?.rules.length ?? 0)
                         + (hermesClawSharedConfig?.providers.length ?? 0)
                         + (hermesClawSharedConfig?.tools.length ?? 0)
                         + (hermesClawSharedConfig?.hooks.length ?? 0)} entries
                     </p>
                   </div>
                   <div className="space-y-1 rounded-2xl border border-black/5 dark:border-white/5 bg-white dark:bg-card p-4">
                     <p className="text-[12px] text-muted-foreground">Install status</p>
                     <p className="text-[13px] text-foreground" data-testid="settings-hermesclaw-install-status">
                        {hermesClawStatus?.installStatus.installed ? 'Installed' : 'Not installed'}
                      </p>
                    </div>
                  </div>
                </div>

                <div
                  data-testid="settings-orova-panel"
                  className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-5"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                    <div className="space-y-1">
                      <Label className="text-[15px] font-medium text-foreground/90">OROVA Backend</Label>
                      <p className="text-[12px] text-muted-foreground">Connect HermesClaw to OROVA's multi-agent engine</p>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="orova-backend-url" className="text-[13px] text-foreground/80">Backend URL</Label>
                      <Input
                        id="orova-backend-url"
                        data-testid="settings-orova-backend-url"
                        value={orovaBackendUrlDraft}
                        onChange={(event) => setOrovaBackendUrlDraft(event.target.value)}
                        placeholder="http://127.0.0.1:18790"
                        className="h-10 rounded-xl bg-black/5 dark:bg-white/5 border-transparent font-mono text-[13px]"
                      />
                      <p className="text-[11px] text-muted-foreground">The URL of the OROVA backend service.</p>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="orova-api-key" className="text-[13px] text-foreground/80">API Key</Label>
                      <Input
                        id="orova-api-key"
                        data-testid="settings-orova-api-key"
                        value={orovaApiKeyDraft}
                        onChange={(event) => setOrovaApiKeyDraft(event.target.value)}
                        type="password"
                        className="h-10 rounded-xl bg-black/5 dark:bg-white/5 border-transparent font-mono text-[13px]"
                      />
                      <p className="text-[11px] text-muted-foreground">API key for authenticating with the OROVA backend.</p>
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3">
                    <Button
                      type="button"
                      size="sm"
                      onClick={async () => {
                        setSavingOrova(true);
                        try {
                          await Promise.all([
                            hostApiFetch('/api/settings/orovaBackendUrl', {
                              method: 'PUT',
                              body: JSON.stringify({ value: orovaBackendUrlDraft.trim() }),
                            }),
                            hostApiFetch('/api/settings/orovaApiKey', {
                              method: 'PUT',
                              body: JSON.stringify({ value: orovaApiKeyDraft.trim() }),
                            }),
                          ]);
                          setOrovaBackendUrl(orovaBackendUrlDraft.trim());
                          setOrovaApiKey(orovaApiKeyDraft.trim());
                          toast.success('OROVA settings saved');
                        } catch (error) {
                          toast.error(`Failed to save OROVA settings: ${toUserMessage(error)}`);
                        } finally {
                          setSavingOrova(false);
                        }
                      }}
                     disabled={savingOrova || (orovaBackendUrlDraft.trim() === orovaBackendUrl && orovaApiKeyDraft.trim() === orovaApiKey)}
                     data-testid="settings-orova-save-button"
                     className="rounded-full h-8 px-4"
                   >
                     <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', savingOrova && 'animate-spin')} />
                     {savingOrova ? t('common:status.saving') : t('common:actions.save')}
                   </Button>
                 </div>
               </div>
             </div>
           )}

          {activeTab === 'advanced' && (
            <div className="space-y-12">
              <section className="space-y-6">
                <h2 className="text-2xl md:text-3xl font-serif text-foreground font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                  Advanced & Diagnostics
                </h2>
                <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 flex flex-col divide-y divide-black/5 dark:divide-white/5">
                  <div className="p-5 flex items-center justify-between gap-4">
                    <div>
                      <Label className="text-[15px] font-medium text-foreground/90">{t('advanced.devMode')}</Label>
                      <p className="text-[13px] text-muted-foreground mt-1">
                        {t('advanced.devModeDesc')}
                      </p>
                    </div>
                    <Switch
                      checked={devModeUnlocked}
                      onCheckedChange={setDevModeUnlocked}
                      data-testid="settings-dev-mode-switch"
                    />
                  </div>

                  <div className="p-5 flex items-center justify-between gap-4">
                    <div>
                      <Label className="text-[15px] font-medium text-foreground/90">{t('advanced.telemetry')}</Label>
                      <p className="text-[13px] text-muted-foreground mt-1">
                        {t('advanced.telemetryDesc')}
                      </p>
                    </div>
                    <Switch
                      checked={telemetryEnabled}
                      onCheckedChange={setTelemetryEnabled}
                    />
                  </div>
                </div>

                <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-5 space-y-4">
                  <div>
                    <Label className="text-[15px] font-medium text-foreground/90">HermesClaw Doctor</Label>
                    <p className="text-[13px] text-muted-foreground mt-1">Repair and diagnostic tools for local HermesAgent integration.</p>
                  </div>
<div className="flex flex-wrap gap-2">
                     <Button type="button" variant="outline" size="sm" data-testid="settings-hermesclaw-doctor-button" disabled={hermesClawActionLoading != null} onClick={() => void handleHermesClawDoctor()} className="rounded-full h-8 px-4">
                       <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', hermesClawActionLoading === 'doctor' && 'animate-spin')} />
                       Run Doctor
                     </Button>
                     <Button type="button" variant="outline" size="sm" data-testid="settings-hermesclaw-repair-button" disabled={hermesClawActionLoading != null} onClick={() => void handleHermesClawRepair()} className="rounded-full h-8 px-4">
                       <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', hermesClawActionLoading === 'repair' && 'animate-spin')} />
                       Repair Install
                     </Button>
                   </div>
                   {hermesClawDoctorSummary && (
                     <div className="space-y-1 text-[12px] text-muted-foreground">
                       <p data-testid="settings-hermesclaw-doctor-result">
                         {hermesClawDoctorSummary}
                       </p>
                       {hermesClawDoctorResult?.reportPath && (
                         <p className="break-all" data-testid="settings-hermesclaw-report-path">
                           Diagnostic report: {hermesClawDoctorResult.reportPath}
                         </p>
                       )}
                     </div>
                   )}
                 </div>
               </section>
             </div>
          )}

          {activeTab === 'about' && (
            <div className="space-y-12">
              <div>
                <h2 className="text-3xl font-serif text-foreground mb-6 font-normal tracking-tight" style={{ fontFamily: 'Georgia, Cambria, "Times New Roman", Times, serif' }}>
                  {t('about.title')}
                </h2>
                <div className="space-y-3 text-[14px] text-muted-foreground">
                  <p>
                    <strong className="text-foreground font-semibold">{t('about.appName')}</strong> - {t('about.tagline')}
                  </p>
                  <p>{t('about.basedOn')}</p>
                  <p>{t('about.version', { version: currentVersion })}</p>
                  <div className="flex gap-4 pt-3">
                    <Button
                      variant="link"
                      className="h-auto p-0 text-[14px] text-blue-500 hover:text-blue-600 font-medium"
                      onClick={() => window.electron.openExternal('https://github.com/NextAgentX/HermesClaw')}
                    >
                      {t('about.docs')}
                    </Button>
                    <Button
                      variant="link"
                      className="h-auto p-0 text-[14px] text-blue-500 hover:text-blue-600 font-medium"
                      onClick={() => window.electron.openExternal('https://github.com/NextAgentX/HermesClaw')}
                    >
                      {t('about.github')}
                    </Button>
                    <Button
                      variant="link"
                      className="h-auto p-0 text-[14px] text-blue-500 hover:text-blue-600 font-medium"
                      onClick={() => window.electron.openExternal('https://github.com/NextAgentX/HermesClaw/issues')}
                    >
                      {t('about.faq')}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Settings;
