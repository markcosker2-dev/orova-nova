/**
 * Setup Wizard Page
 * First-time setup experience for new users
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
  AlertCircle,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ExternalLink,
} from 'lucide-react';
import { TitleBar } from '@/components/layout/TitleBar';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useGatewayStore } from '@/stores/gateway';
import { useSettingsStore } from '@/stores/settings';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { SUPPORTED_LANGUAGES } from '@/i18n';
import { toast } from 'sonner';
import { invokeIpc } from '@/lib/api-client';
import { hostApiFetch, installRuntime, setRuntimeInstallChoice } from '@/lib/host-api';
import type { RuntimeInstallResult } from '@/lib/host-api';
import { subscribeHostEvent } from '@/lib/host-events';

interface SetupStep {
  id: string;
  title: string;
  description: string;
}

type SetupInstallChoice = 'openclaw' | 'hermes' | 'both';

const STEP = {
  WELCOME: 0,
  RUNTIME: 1,
  INSTALLING: 2,
  COMPLETE: 3,
} as const;

const getSteps = (t: TFunction): SetupStep[] => [
  {
    id: 'welcome',
    title: t('steps.welcome.title'),
    description: t('steps.welcome.description'),
  },
  {
    id: 'runtime',
    title: t('steps.runtime.title'),
    description: t('steps.runtime.description'),
  },
  {
    id: 'installing',
    title: t('steps.installing.title'),
    description: t('steps.installing.description'),
  },
  {
    id: 'complete',
    title: t('steps.complete.title'),
    description: t('steps.complete.description'),
  },
];

import hermesclawIcon from '@/assets/logo.png';

// NOTE: Channel types moved to Settings > Channels page
// NOTE: Skill bundles moved to Settings > Skills page - auto-install essential skills during setup

export function Setup() {
  const { t } = useTranslation(['setup', 'channels']);
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<number>(STEP.WELCOME);

  // Setup state
  // Installation state for the Installing step
  const [installedSkills, setInstalledSkills] = useState<string[]>([]);
  // Runtime check status
  const [runtimeChecksPassed, setRuntimeChecksPassed] = useState(false);
  const [installChoice, setInstallChoice] = useState<SetupInstallChoice>('both');

  const steps = getSteps(t);
  const safeStepIndex = Number.isInteger(currentStep)
    ? Math.min(Math.max(currentStep, STEP.WELCOME), steps.length - 1)
    : STEP.WELCOME;
  const step = steps[safeStepIndex] ?? steps[STEP.WELCOME];
  const isFirstStep = safeStepIndex === STEP.WELCOME;
  const isLastStep = safeStepIndex === steps.length - 1;

  const markSetupComplete = useSettingsStore((state) => state.markSetupComplete);

  // Derive canProceed based on current step - computed directly to avoid useEffect
  const canProceed = useMemo(() => {
    switch (safeStepIndex) {
      case STEP.WELCOME:
        return true;
      case STEP.RUNTIME:
        return runtimeChecksPassed;
      case STEP.INSTALLING:
        return false; // Cannot manually proceed, auto-proceeds when done
      case STEP.COMPLETE:
        return true;
      default:
        return true;
    }
  }, [safeStepIndex, runtimeChecksPassed]);

  const handleNext = async () => {
    if (isLastStep) {
      // Complete setup
      markSetupComplete();
      toast.success(t('complete.title'));
      navigate('/');
    } else {
      setCurrentStep((i) => i + 1);
    }
  };

  const handleBack = () => {
    setCurrentStep((i) => Math.max(i - 1, 0));
  };

  const handleSkip = () => {
    markSetupComplete();
    navigate('/');
  };

  // Auto-proceed when installation is complete
  const handleInstallationComplete = useCallback((skills: string[]) => {
    setInstalledSkills(skills);
    // Auto-proceed to next step after a short delay
    setTimeout(() => {
      setCurrentStep((i) => i + 1);
    }, 1000);
  }, []);


  return (
    <div data-testid="setup-page" className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <TitleBar />
      <div className="flex-1 overflow-auto">
        {/* Progress Indicator */}
        <div className="flex justify-center pt-8">
          <div className="flex items-center gap-2">
            {steps.map((s, i) => (
              <div key={s.id} className="flex items-center">
                <div
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors',
                    i < safeStepIndex
                      ? 'border-primary bg-primary text-primary-foreground'
                      : i === safeStepIndex
                        ? 'border-primary text-primary'
                        : 'border-slate-600 text-slate-600'
                  )}
                >
                  {i < safeStepIndex ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <span className="text-sm">{i + 1}</span>
                  )}
                </div>
                {i < steps.length - 1 && (
                  <div
                    className={cn(
                      'h-0.5 w-8 transition-colors',
                      i < safeStepIndex ? 'bg-primary' : 'bg-slate-600'
                    )}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Step Content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={step.id}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="mx-auto max-w-2xl p-8"
          >
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold mb-2">{t(`steps.${step.id}.title`)}</h1>
              <p className="text-slate-400">{t(`steps.${step.id}.description`)}</p>
            </div>

            {/* Step-specific content */}
            <div className="rounded-xl bg-card text-card-foreground border shadow-sm p-8 mb-8">
              {safeStepIndex === STEP.WELCOME && <WelcomeContent />}
              {safeStepIndex === STEP.RUNTIME && (
                <RuntimeContent
                  installChoice={installChoice}
                  onInstallChoiceChange={setInstallChoice}
                  onStatusChange={setRuntimeChecksPassed}
                />
              )}
              {safeStepIndex === STEP.INSTALLING && (
                <InstallingContent
                  installChoice={installChoice}
                  onComplete={handleInstallationComplete}
                  onSkip={() => setCurrentStep((i) => i + 1)}
                />
              )}
              {safeStepIndex === STEP.COMPLETE && (
                <CompleteContent
                  installedSkills={installedSkills}
                />
              )}
            </div>

            {/* Navigation - hidden during installation step */}
            {safeStepIndex !== STEP.INSTALLING && (
              <div className="flex justify-between">
                <div>
                  {!isFirstStep && (
                    <Button variant="ghost" onClick={handleBack}>
                      <ChevronLeft className="h-4 w-4 mr-2" />
                      {t('nav.back')}
                    </Button>
                  )}
                </div>
                <div className="flex gap-2">
                  {!isLastStep && safeStepIndex !== STEP.RUNTIME && (
                    <Button data-testid="setup-skip-button" variant="ghost" onClick={handleSkip}>
                      {t('nav.skipSetup')}
                    </Button>
                  )}
                  <Button data-testid="setup-next-button" onClick={handleNext} disabled={!canProceed}>
                    {isLastStep ? (
                      t('nav.getStarted')
                    ) : (
                      <>
                        {t('nav.next')}
                        <ChevronRight className="h-4 w-4 ml-2" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

// ==================== Step Content Components ====================

function WelcomeContent() {
  const { t } = useTranslation(['setup', 'settings']);
  const { language, setLanguage } = useSettingsStore();

  return (
    <div data-testid="setup-welcome-step" className="text-center space-y-4">
      <div className="mb-4 flex justify-center">
          <img src={hermesclawIcon} alt="HermesClaw" className="h-16 w-16" />
      </div>
      <h2 className="text-xl font-semibold">{t('welcome.title')}</h2>
      <p className="text-muted-foreground">
        {t('welcome.description')}
      </p>

      {/* Language Selector */}
      <div className="flex justify-center gap-2 py-2">
        {SUPPORTED_LANGUAGES.map((lang) => (
          <Button
            key={lang.code}
            variant={language === lang.code ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setLanguage(lang.code)}
            className="h-7 text-xs"
          >
            {lang.label}
          </Button>
        ))}
      </div>

      <ul className="text-left space-y-2 text-muted-foreground pt-2">
        <li className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-400" />
          {t('welcome.features.noCommand')}
        </li>
        <li className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-400" />
          {t('welcome.features.modernUI')}
        </li>
        <li className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-400" />
          {t('welcome.features.bundles')}
        </li>
        <li className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-400" />
          {t('welcome.features.crossPlatform')}
        </li>
      </ul>
    </div>
  );
}

interface RuntimeContentProps {
  installChoice: SetupInstallChoice;
  onInstallChoiceChange: (installChoice: SetupInstallChoice) => void;
  onStatusChange: (canProceed: boolean) => void;
}

function RuntimeContent({ installChoice, onInstallChoiceChange, onStatusChange }: RuntimeContentProps) {
  const { t } = useTranslation('setup');
  const gatewayStatus = useGatewayStore((state) => state.status);
  const startGateway = useGatewayStore((state) => state.start);
  const runtimeSettings = useSettingsStore((state) => state.runtime);
  const windowsHermesWslDistro = runtimeSettings.windowsHermesWslDistro;

  const [checks, setChecks] = useState({
    nodejs: { status: 'checking' as 'checking' | 'success' | 'error', message: '' },
    openclaw: { status: 'checking' as 'checking' | 'success' | 'error', message: '' },
    gateway: { status: 'checking' as 'checking' | 'success' | 'error', message: '' },
  });
  const [showLogs, setShowLogs] = useState(false);
  const [logContent, setLogContent] = useState('');
  const [openclawDir, setOpenclawDir] = useState('');
  const [resolvedWindowsWslDistro, setResolvedWindowsWslDistro] = useState<string | undefined>(windowsHermesWslDistro);
  const [platform, setPlatform] = useState<'win32' | 'darwin' | 'linux' | 'unknown'>(() => {
    const detected = window.electron?.platform;
    return detected === 'win32' || detected === 'darwin' || detected === 'linux' ? detected : 'unknown';
  });
  const gatewayTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const runChecks = useCallback(async () => {
    // Reset checks
    setChecks({
      nodejs: { status: 'checking', message: '' },
      openclaw: { status: 'checking', message: '' },
      gateway: { status: 'checking', message: '' },
    });

    // Check Node.js — always available in Electron
    setChecks((prev) => ({
      ...prev,
      nodejs: { status: 'success', message: t('runtime.status.success') },
    }));

    // Check OpenClaw package status
    try {
      const openclawStatus = await invokeIpc('openclaw:status') as {
        packageExists: boolean;
        isBuilt: boolean;
        dir: string;
        version?: string;
      };

      setOpenclawDir(openclawStatus.dir);

      if (!openclawStatus.packageExists) {
        setChecks((prev) => ({
          ...prev,
          openclaw: {
            status: 'error',
            message: `OpenClaw package not found at: ${openclawStatus.dir}`
          },
        }));
      } else if (!openclawStatus.isBuilt) {
        setChecks((prev) => ({
          ...prev,
          openclaw: {
            status: 'error',
            message: 'OpenClaw package found but dist is missing'
          },
        }));
      } else {
        const versionLabel = openclawStatus.version ? ` v${openclawStatus.version}` : '';
        setChecks((prev) => ({
          ...prev,
          openclaw: {
            status: 'success',
            message: `OpenClaw package ready${versionLabel}`
          },
        }));
      }
    } catch (error) {
      setChecks((prev) => ({
        ...prev,
        openclaw: { status: 'error', message: `Check failed: ${error}` },
      }));
    }

    // Check Gateway — read directly from store to avoid stale closure
    // Don't immediately report error; gateway may still be initializing
    const currentGateway = useGatewayStore.getState().status;
    if (currentGateway.state === 'running') {
      setChecks((prev) => ({
        ...prev,
        gateway: { status: 'success', message: `Running on port ${currentGateway.port}` },
      }));
    } else if (currentGateway.state === 'error') {
      setChecks((prev) => ({
        ...prev,
        gateway: { status: 'error', message: currentGateway.error || t('runtime.status.error') },
      }));
    } else {
      // Gateway is 'stopped', 'starting', or 'reconnecting'
      // Keep as 'checking' — the dedicated useEffect will update when status changes
      setChecks((prev) => ({
        ...prev,
        gateway: {
          status: 'checking',
          message: currentGateway.state === 'starting' ? t('runtime.status.checking') : 'Waiting for gateway...'
        },
      }));
    }
  }, [t]);

  useEffect(() => {
    runChecks();
  }, [runChecks]);

  useEffect(() => {
    let cancelled = false;

    void invokeIpc<'win32' | 'darwin' | 'linux' | 'unknown'>('app:platform')
      .then((value) => {
        if (!cancelled && (value === 'win32' || value === 'darwin' || value === 'linux')) {
          setPlatform(value);
        }
      })
      .catch(() => {
        // ignore platform reconciliation failures
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setResolvedWindowsWslDistro(windowsHermesWslDistro);
  }, [windowsHermesWslDistro]);

  useEffect(() => {
    if (platform !== 'win32' || resolvedWindowsWslDistro) {
      return;
    }

    let cancelled = false;

    void invokeIpc<string[]>('wsl:list')
      .then(async (distros) => {
        if (cancelled) return;

        const discoveredDistro = distros.find((distro) => typeof distro === 'string' && distro.trim().length > 0)?.trim();
        if (!discoveredDistro) {
          return;
        }

        setResolvedWindowsWslDistro(discoveredDistro);

        await hostApiFetch('/api/settings/runtime', {
          method: 'PUT',
          body: JSON.stringify({
            value: {
              ...runtimeSettings,
              windowsHermesWslDistro: discoveredDistro,
            },
          }),
        }).catch(() => {
          // local runtime gating still uses the discovered distro for this setup session
        });
      })
      .catch(() => {
        // ignore WSL discovery failures and keep Windows Hermes blocked
      });

    return () => {
      cancelled = true;
    };
  }, [platform, resolvedWindowsWslDistro, runtimeSettings]);

  const windowsRequiresWsl = platform === 'win32';
  const windowsNativeReady = Boolean(runtimeSettings.windowsHermesNativePath?.trim());
  const windowsWslReady = Boolean(resolvedWindowsWslDistro);
  const windowsHermesReady = windowsNativeReady || windowsWslReady;
  const blockedByWindowsWsl = windowsRequiresWsl && !windowsHermesReady && installChoice !== 'openclaw';
  const requiresOpenClawPrimary = installChoice !== 'hermes';

  // Update canProceed when gateway status changes
  useEffect(() => {
    const allPassed = checks.nodejs.status === 'success'
      && (!requiresOpenClawPrimary || checks.openclaw.status === 'success')
      && (!requiresOpenClawPrimary || checks.gateway.status === 'success' || gatewayStatus.state === 'running');
    onStatusChange(allPassed && !blockedByWindowsWsl);
  }, [blockedByWindowsWsl, checks, gatewayStatus, onStatusChange, requiresOpenClawPrimary]);

  // Update gateway check when gateway status changes
  useEffect(() => {
    if (gatewayStatus.state === 'running') {
      setChecks((prev) => ({
        ...prev,
        gateway: { status: 'success', message: t('runtime.status.gatewayRunning', { port: gatewayStatus.port }) },
      }));
    } else if (gatewayStatus.state === 'error') {
      setChecks((prev) => ({
        ...prev,
        gateway: { status: 'error', message: gatewayStatus.error || 'Failed to start' },
      }));
    } else if (gatewayStatus.state === 'starting' || gatewayStatus.state === 'reconnecting') {
      setChecks((prev) => ({
        ...prev,
        gateway: { status: 'checking', message: 'Starting...' },
      }));
    }
    // 'stopped' state: keep current check status (likely 'checking') to allow startup time
  }, [gatewayStatus, t]);

  // Gateway startup timeout — show error only after giving enough time to initialize
  useEffect(() => {
    if (gatewayTimeoutRef.current) {
      clearTimeout(gatewayTimeoutRef.current);
      gatewayTimeoutRef.current = null;
    }

    // If gateway is already in a terminal state, no timeout needed
    if (gatewayStatus.state === 'running' || gatewayStatus.state === 'error') {
      return;
    }

    // Set timeout for non-terminal states (stopped, starting, reconnecting)
    gatewayTimeoutRef.current = setTimeout(() => {
      setChecks((prev) => {
        if (prev.gateway.status === 'checking') {
          return {
            ...prev,
            gateway: { status: 'error', message: 'Gateway startup timed out' },
          };
        }
        return prev;
      });
    }, 600 * 1000); // 600 seconds — enough for gateway to fully initialize

    return () => {
      if (gatewayTimeoutRef.current) {
        clearTimeout(gatewayTimeoutRef.current);
        gatewayTimeoutRef.current = null;
      }
    };
  }, [gatewayStatus.state]);

  const handleStartGateway = async () => {
    setChecks((prev) => ({
      ...prev,
      gateway: { status: 'checking', message: 'Starting...' },
    }));
    await startGateway();
  };

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

  const ERROR_TRUNCATE_LEN = 30;

  const installChoiceOptions: Array<{
    value: SetupInstallChoice;
    title: string;
    description: string;
  }> = [
    {
      value: 'both',
      title: t('runtime.installChoice.both.title'),
      description: t('runtime.installChoice.both.description'),
    },
  ];

  const handleInstallChoiceSelect = async (nextChoice: SetupInstallChoice) => {
    onInstallChoiceChange(nextChoice);
    try {
      await setRuntimeInstallChoice(nextChoice);
    } catch {
      // local state remains source of truth for the setup flow
    }
  };

  const renderStatus = (status: 'checking' | 'success' | 'error', message: string) => {
    if (status === 'checking') {
      return (
        <span className="flex items-center gap-2 text-yellow-400 whitespace-nowrap">
          <Loader2 className="h-5 w-5 flex-shrink-0 animate-spin" />
          {message || 'Checking...'}
        </span>
      );
    }
    if (status === 'success') {
      return (
        <span className="flex items-center gap-2 text-green-400 whitespace-nowrap">
          <CheckCircle2 className="h-5 w-5 flex-shrink-0" />
          {message}
        </span>
      );
    }

    const isLong = message.length > ERROR_TRUNCATE_LEN;
    const displayMsg = isLong ? message.slice(0, ERROR_TRUNCATE_LEN) : message;

    return (
      <span className="flex items-center gap-2 text-red-400 whitespace-nowrap">
        <XCircle className="h-5 w-5 flex-shrink-0" />
        <span>{displayMsg}</span>
        {isLong && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="cursor-pointer text-red-300 hover:text-red-200 font-medium">...</span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-sm whitespace-normal break-words text-xs">
              {message}
            </TooltipContent>
          </Tooltip>
        )}
      </span>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">{t('runtime.title')}</h2>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={handleShowLogs}>
            {t('runtime.viewLogs')}
          </Button>
          <Button variant="ghost" size="sm" onClick={runChecks}>
            <RefreshCw className="h-4 w-4 mr-2" />
            {t('runtime.recheck')}
          </Button>
        </div>
      </div>
      <div className="space-y-3">
        <div className="grid grid-cols-[1fr_auto] items-center gap-4 p-3 rounded-lg bg-muted/50">
          <span className="text-left">{t('runtime.nodejs')}</span>
          <div className="flex justify-end">
            {renderStatus(checks.nodejs.status, checks.nodejs.message)}
          </div>
        </div>
        <div className="grid grid-cols-[1fr_auto] items-center gap-4 p-3 rounded-lg bg-muted/50">
          <div className="text-left min-w-0">
            <span>{t('runtime.openclaw')}</span>
            {openclawDir && (
              <p className="text-xs text-muted-foreground mt-0.5 font-mono break-all">
                {openclawDir}
              </p>
            )}
          </div>
          <div className="flex justify-end self-start mt-0.5">
            {renderStatus(checks.openclaw.status, checks.openclaw.message)}
          </div>
        </div>
        <div className="grid grid-cols-[1fr_auto] items-center gap-4 p-3 rounded-lg bg-muted/50">
          <div className="flex items-center gap-2 text-left">
            <span>{t('runtime.gateway')}</span>
            {checks.gateway.status === 'error' && (
              <Button variant="outline" size="sm" onClick={handleStartGateway}>
                {t('runtime.startGateway')}
              </Button>
            )}
          </div>
          <div className="flex justify-end">
            {renderStatus(checks.gateway.status, checks.gateway.message)}
          </div>
        </div>
      </div>

      <div className="space-y-3 pt-2">
        <div>
          <p className="text-sm font-medium text-foreground">{t('runtime.installChoiceLabel')}</p>
          <p className="text-sm text-muted-foreground mt-1">{t('runtime.installChoiceHint')}</p>
        </div>
        <div className="grid gap-3">
          {installChoiceOptions.map((option) => {
            const selected = installChoice === option.value;
            const disabled = windowsRequiresWsl && !windowsHermesReady && option.value !== 'openclaw';

            return (
              <Button
                key={option.value}
                type="button"
                variant="outline"
                data-testid={`setup-install-choice-${option.value}`}
                aria-pressed={selected}
                disabled={disabled}
                className={cn(
                  'h-auto min-h-28 flex-col items-start justify-start gap-2 p-4 text-left',
                  selected && 'border-primary bg-primary/10 text-primary',
                )}
                onClick={() => void handleInstallChoiceSelect(option.value)}
              >
                <span className="text-sm font-semibold">{option.title}</span>
                <span className="text-xs leading-5 text-muted-foreground whitespace-normal">
                  {option.description}
                </span>
              </Button>
            );
          })}
        </div>
      </div>

      {windowsRequiresWsl && (
        <div
          data-testid="setup-runtime-wsl2-notice"
          className={cn(
            'mt-4 rounded-lg border p-4',
            windowsHermesReady ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-amber-500/30 bg-amber-500/10',
          )}
        >
          <p className="font-medium text-foreground">{t('runtime.windowsWsl.title')}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t('runtime.windowsWsl.description')}</p>
            <p className="mt-2 text-sm text-foreground">
              {windowsNativeReady
                ? (windowsWslReady
                    ? t('runtime.windowsWsl.nativeAndWslReady', { distro: resolvedWindowsWslDistro })
                    : t('runtime.windowsWsl.nativeReady'))
                : windowsWslReady
                  ? t('runtime.windowsWsl.ready', { distro: resolvedWindowsWslDistro })
                  : t('runtime.windowsWsl.missing')}
            </p>
          </div>
      )}

      {(checks.nodejs.status === 'error' || checks.openclaw.status === 'error') && (
        <div className="mt-4 p-4 rounded-lg bg-red-900/20 border border-red-500/20">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-5 w-5 text-red-400 mt-0.5" />
            <div>
              <p className="font-medium text-red-400">{t('runtime.issue.title')}</p>
              <p className="text-sm text-muted-foreground mt-1">
                {t('runtime.issue.desc')}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Log viewer panel */}
      {showLogs && (
        <div className="mt-4 p-4 rounded-lg bg-black/40 border border-border">
          <div className="flex items-center justify-between mb-2">
            <p className="font-medium text-foreground text-sm">{t('runtime.logs.title')}</p>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleOpenLogDir}>
                <ExternalLink className="h-3 w-3 mr-1" />
                {t('runtime.logs.openFolder')}
              </Button>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowLogs(false)}>
                {t('runtime.logs.close')}
              </Button>
            </div>
          </div>
          <pre className="text-xs text-slate-300 bg-black/50 p-3 rounded max-h-60 overflow-auto whitespace-pre-wrap font-mono">
            {logContent || t('runtime.logs.noLogs')}
          </pre>
        </div>
      )}
    </div>
  );
}

// NOTE: ProviderContent component removed - configure providers via Settings > AI Providers


// Installation status for each skill
type InstallStatus = RuntimeInstallResult['steps'][number]['status'];

interface StepInstallState {
  id: 'openclaw' | 'hermes' | 'bridge';
  label: string;
  status: InstallStatus;
}

interface InstallingContentProps {
  installChoice: SetupInstallChoice;
  onComplete: (installedSkills: string[]) => void;
  onSkip: () => void;
}

type InstallFailureSource = 'openclaw' | 'hermes' | 'bridge' | 'generic';

function inferFailureSourceFromSteps(
  steps: Array<{ id: StepInstallState['id']; status: InstallStatus }>,
): InstallFailureSource | null {
  const failedStep = steps.find((step) => step.status === 'failed');
  if (!failedStep) return null;
  return failedStep.id;
}

function getStepLabel(t: TFunction<'setup'>, stepId: StepInstallState['id']) {
  return t(`installing.steps.${stepId}`);
}

function buildInstallSteps(t: TFunction<'setup'>, installChoice: SetupInstallChoice): StepInstallState[] {
  const steps: StepInstallState[] = [];

  if (installChoice !== 'hermes') {
    steps.push({ id: 'openclaw', label: getStepLabel(t, 'openclaw'), status: 'pending' });
  }

  if (installChoice !== 'openclaw') {
    steps.push({ id: 'hermes', label: getStepLabel(t, 'hermes'), status: 'pending' });
  }

  if (installChoice === 'both') {
    steps.push({ id: 'bridge', label: getStepLabel(t, 'bridge'), status: 'pending' });
  }

  return steps;
}

function inferFailureSource(message: string, installChoice: SetupInstallChoice): InstallFailureSource {
  const normalized = message.toLowerCase();

  if (normalized.includes('bridge') || normalized.includes('agent')) return 'bridge';
  if (normalized.includes('hermes') || normalized.includes('wsl')) return 'hermes';
  if (normalized.includes('openclaw') || normalized.includes('gateway')) return 'openclaw';
  return installChoice === 'openclaw' ? 'openclaw' : 'generic';
}

function applyFailureToSteps(
  steps: StepInstallState[],
  source: InstallFailureSource,
): StepInstallState[] {
  if (steps.length === 0) return steps;

  const sourceIndex = source === 'generic'
    ? steps.findIndex((step) => step.status === 'installing')
    : steps.findIndex((step) => step.id === source);
  const failedIndex = sourceIndex >= 0 ? sourceIndex : 0;

  return steps.map((step, index) => {
    if (index < failedIndex) return { ...step, status: 'completed' };
    if (index === failedIndex) return { ...step, status: 'failed' };
    return { ...step, status: 'pending' };
  });
}

function applyBackendSteps(
  plannedSteps: StepInstallState[],
  backendSteps: Array<{ id: StepInstallState['id']; status: InstallStatus }>,
): StepInstallState[] {
  return plannedSteps.map((step) => {
    const backendStep = backendSteps.find((candidate) => candidate.id === step.id);
    return {
      ...step,
      status: backendStep?.status ?? 'pending',
    };
  });
}

function calculateProgress(steps: Array<{ status: InstallStatus }>): number {
  if (steps.length === 0) return 0;
  const completed = steps.filter((step) => step.status === 'completed').length;
  const installing = steps.some((step) => step.status === 'installing');
  const progress = (completed / steps.length) * 100 + (installing ? 100 / (steps.length * 2) : 0);
  return Math.min(95, Math.max(0, Math.round(progress)));
}

interface RuntimeInstallProgressPayload {
  installChoice: SetupInstallChoice;
  activeStepId: StepInstallState['id'];
  steps: Array<{
    id: StepInstallState['id'];
    status: InstallStatus;
  }>;
}

function InstallingContent({ installChoice, onComplete, onSkip }: InstallingContentProps) {
  const { t } = useTranslation('setup');
  const [stepStates, setStepStates] = useState<StepInstallState[]>([]);
  const [overallProgress, setOverallProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [failureSource, setFailureSource] = useState<InstallFailureSource | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const installStarted = useRef(false);

  // Real installation process
  useEffect(() => {
    if (installStarted.current) return;
    installStarted.current = true;

    const runRealInstall = async () => {
      try {
        const plannedSteps = buildInstallSteps(t, installChoice);
        const unsubscribeProgress = subscribeHostEvent<RuntimeInstallProgressPayload>('runtime:install:progress', (payload) => {
          if (payload.installChoice !== installChoice) return;
          const nextSteps = applyBackendSteps(plannedSteps, payload.steps);
          setStepStates(nextSteps);
          setOverallProgress(calculateProgress(nextSteps));
        });
        setFailureSource(null);
        setErrorMessage(null);
        setStepStates(
          plannedSteps.map((step, index) => ({
            ...step,
            status: index === 0 ? 'installing' : 'pending',
          })),
        );
        setOverallProgress(plannedSteps.length <= 1 ? 45 : 25);

        const result = await installRuntime(installChoice);
        unsubscribeProgress();

        if (!result.success) {
          const failureMessage = result.error || t('installing.error.generic');
          const source = inferFailureSourceFromSteps(result.steps) ?? inferFailureSource(failureMessage, installChoice);
          setFailureSource(source);
          setErrorMessage(failureMessage);
          setStepStates(applyBackendSteps(plannedSteps, result.steps));
          setOverallProgress(0);
          return;
        }

        setStepStates(applyBackendSteps(plannedSteps, result.steps));

        setOverallProgress(100);
        setTimeout(() => {
          onComplete([]);
        }, 1500);

      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        const source = inferFailureSource(message, installChoice);
        setFailureSource(source);
        setErrorMessage(message);
        setStepStates((prev) => applyFailureToSteps(prev.length ? prev : buildInstallSteps(t, installChoice), source));
        setOverallProgress(0);
      }
    };

    runRealInstall();
  }, [installChoice, onComplete, retryNonce, t]);


  const getStatusIcon = (status: InstallStatus) => {
    switch (status) {
      case 'pending':
        return <div className="h-5 w-5 rounded-full border-2 border-slate-500" />;
      case 'installing':
        return <Loader2 className="h-5 w-5 text-primary animate-spin" />;
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-green-400" />;
      case 'skipped':
        return <CheckCircle2 className="h-5 w-5 text-slate-500" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-400" />;
    }
  };

  const getStatusText = (status: InstallStatus) => {
    switch (status) {
      case 'pending':
        return <span className="text-muted-foreground">{t('installing.status.pending')}</span>;
      case 'installing':
        return <span className="text-primary">{t('installing.status.installing')}</span>;
      case 'completed':
        return <span className="text-green-400">{t('installing.status.installed')}</span>;
      case 'failed':
        return <span className="text-red-400">{t('installing.status.failed')}</span>;
    }
  };

  const activeStepCount = stepStates.length;

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="text-4xl mb-4">⚙️</div>
        <h2 className="text-xl font-semibold mb-2">{t('installing.title')}</h2>
        <p className="text-muted-foreground">
          {t('installing.subtitle')}
        </p>
        {activeStepCount > 0 && (
          <p className="mt-2 text-sm text-muted-foreground" data-testid="setup-install-summary">
            {t('installing.summary', { count: activeStepCount })}
          </p>
        )}
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">{t('installing.progress')}</span>
          <span className="text-primary">{overallProgress}%</span>
        </div>
        <div className="h-2 bg-secondary rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-primary"
            initial={{ width: 0 }}
            animate={{ width: `${overallProgress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {/* Step list */}
      <div className="space-y-2 max-h-48 overflow-y-auto">
        {stepStates.map((step) => (
          <motion.div
            key={step.id}
            data-testid={`setup-install-step-${step.id}`}
            data-status={step.status}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              'flex items-center justify-between p-3 rounded-lg',
              step.status === 'installing' ? 'bg-muted' : 'bg-muted/50'
            )}
          >
              <div className="flex items-center gap-3">
                {getStatusIcon(step.status)}
                <div>
                  <p className="font-medium">{step.label}</p>
                  <p className="text-xs text-muted-foreground">{t(`installing.stepHint.${step.id}`)}</p>
                </div>
              </div>
              <div data-testid={`setup-install-step-${step.id}-status`}>
                {getStatusText(step.status)}
              </div>
            </motion.div>
        ))}
      </div>

      {/* Error Message Display */}
      {errorMessage && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="p-4 rounded-lg bg-red-900/30 border border-red-500/50 text-red-200 text-sm"
        >
          <div className="flex items-start gap-2">
            <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">{t('installing.error')}</p>
              <p className="text-xs text-red-200" data-testid="setup-install-error-source">
                {t(`installing.failureSource.${failureSource ?? 'generic'}`)}
              </p>
              <pre className="text-xs bg-black/30 p-2 rounded overflow-x-auto whitespace-pre-wrap font-monospace">
                {errorMessage}
              </pre>
              <p className="text-xs text-red-100">{t(`installing.retryGuidance.${failureSource ?? 'generic'}`)}</p>
              <Button
                variant="link"
                className="text-red-400 p-0 h-auto text-xs underline"
                data-testid="setup-install-retry-button"
                onClick={() => {
                  installStarted.current = false;
                  setErrorMessage(null);
                  setFailureSource(null);
                  setOverallProgress(0);
                  setStepStates([]);
                  setRetryNonce((value) => value + 1);
                }}
              >
                {t('installing.retry')}
              </Button>
            </div>
          </div>
        </motion.div>
      )}

      {!errorMessage && (
        <p className="text-sm text-slate-400 text-center">
          {t('installing.wait')}
        </p>
      )}
      <div className="flex justify-end">
        <Button
          variant="ghost"
          className="text-muted-foreground"
          onClick={onSkip}
        >
          {t('installing.skip')}
        </Button>
      </div>
    </div>
  );
}

interface CompleteContentProps {
  installedSkills?: string[];
}

function CompleteContent(_props: CompleteContentProps) {
  const { t } = useTranslation(['setup', 'settings']);
  const gatewayStatus = useGatewayStore((state) => state.status);

  return (
    <div className="text-center space-y-6">
      <div className="text-6xl mb-4">🎉</div>
      <h2 className="text-xl font-semibold">{t('complete.title')}</h2>
      <p className="text-muted-foreground">
        {t('complete.subtitle')}
      </p>

      <div className="space-y-3 text-left max-w-md mx-auto">
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <span>{t('complete.gateway')}</span>
          <span className={gatewayStatus.state === 'running' ? 'text-green-400' : 'text-yellow-400'}>
            {gatewayStatus.state === 'running' ? `✓ ${t('complete.running')}` : gatewayStatus.state}
          </span>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        {t('complete.footer')}
      </p>
    </div>
  );
}

export default Setup;
