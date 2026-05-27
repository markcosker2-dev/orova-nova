/**
 * Electron Main Process Entry
 * Manages window creation, system tray, and IPC handlers
 */
import { BrowserWindow, nativeImage, session, shell } from 'electron';
import type { Server } from 'node:http';
import { join } from 'path';
import { GatewayManager } from '../gateway/manager';
import { registerIpcHandlers } from './ipc-handlers';
import { createTray } from './tray';
import { createMenu } from './menu';

import { getAppUpdater, registerUpdateHandlers } from './updater';
import { logger } from '../utils/logger';
import { warmupNetworkOptimization } from '../utils/uv-env';
import { initTelemetry } from '../utils/telemetry';

import { ClawHubService } from '../gateway/clawhub';
import { extensionRegistry } from '../extensions/registry';
import { loadExtensionsFromManifest } from '../extensions/loader';
import { registerAllBuiltinExtensions } from '../extensions/builtin';
import { loadExternalMainExtensions } from '../extensions/_ext-bridge.generated';
import { ensureHermesClawContext, repairHermesClawOnlyBootstrapFiles } from '../utils/openclaw-workspace';
import { autoInstallCliIfNeeded, generateCompletionCache, installCompletionToProfile } from '../utils/openclaw-cli';
import { isQuitting, setQuitting } from './app-state';
import { applyProxySettings } from './proxy';
import { syncLaunchAtStartupSettingFromStore } from './launch-at-startup';
import {
  clearPendingSecondInstanceFocus,
  consumeMainWindowReady,
  createMainWindowFocusState,
  requestSecondInstanceFocus,
} from './main-window-focus';
import {
  createQuitLifecycleState,
  markQuitCleanupCompleted,
  requestQuitLifecycleAction,
} from './quit-lifecycle';
import { createSignalQuitHandler } from './signal-quit';
import { acquireProcessInstanceFileLock } from './process-instance-lock';
import { getSetting } from '../utils/store';
import { ensureBuiltinSkillsInstalled, ensurePreinstalledSkillsInstalled } from '../utils/skill-config';
import { ensureAllBundledPluginsInstalled } from '../utils/plugin-install';
import { startHostApiServer } from '../api/server';
import { HostEventBus } from '../api/event-bus';
import { deviceOAuthManager } from '../utils/device-oauth';
import { browserOAuthManager } from '../utils/browser-oauth';
import { whatsAppLoginManager } from '../utils/whatsapp-login';
import { syncAllProviderAuthToRuntime } from '../services/providers/provider-runtime-sync';
import { scheduleRuntimeStartupSync } from './runtime-startup-sync';

const WINDOWS_APP_USER_MODEL_ID = 'app.hermesclaw.desktop';
const isE2EMode = process.env.HERMESCLAW_E2E === '1';
const requestedUserDataDir = process.env.HERMESCLAW_USER_DATA_DIR?.trim();
const MAIN_WINDOW_SHOW_FALLBACK_MS = 4000;

// Check if Electron app is ready (handles vite-plugin-electron early evaluation)
 
function isAppReady(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronApp = require('electron').app;
  return electronApp && typeof electronApp.isPackaged === 'boolean';
}

// Defer app.setPath until app is ready
if (isE2EMode && requestedUserDataDir && isAppReady()) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronApp = require('electron').app;
  if (electronApp && typeof electronApp.setPath === 'function') {
    electronApp.setPath('userData', requestedUserDataDir);
  }
}

// Disable GPU hardware acceleration globally for maximum stability across
// all GPU configurations (no GPU, integrated, discrete).
//
// Rationale (following VS Code's philosophy):
// - Page/file loading is async data fetching — zero GPU dependency.
// - The original per-platform GPU branching was added to avoid CPU rendering
//   competing with sync I/O on Windows, but all file I/O is now async
//   (fs/promises), so that concern no longer applies.
// - Software rendering is deterministic across all hardware; GPU compositing
//   behaviour varies between vendors (Intel, AMD, NVIDIA, Apple Silicon) and
//   driver versions, making it the #1 source of rendering bugs in Electron.
//
// Users who want GPU acceleration can pass `--enable-gpu` on the CLI or
// set `"disable-hardware-acceleration": false` in the app config (future).
if (isAppReady() && !isE2EMode) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronApp = require('electron').app;
  if (electronApp && typeof electronApp.disableHardwareAcceleration === 'function') {
    electronApp.disableHardwareAcceleration();
  }
}

// On Linux, set CHROME_DESKTOP so Chromium can find the correct .desktop file.
// On Wayland this maps the running window to hermesclaw.desktop (→ icon + app grouping);
// on X11 it supplements the StartupWMClass matching.
// Must be called before app.whenReady() / before any window is created.
if (process.platform === 'linux' && isAppReady() && !isE2EMode) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronApp = require('electron').app;
  if (electronApp && typeof electronApp.setDesktopName === 'function') {
    electronApp.setDesktopName('hermesclaw.desktop');
  }
}

// Prevent multiple instances of the app from running simultaneously.
// Without this, two instances each spawn their own gateway process on the
// same port, then each treats the other's gateway as "orphaned" and kills
// it — creating an infinite kill/restart loop on Windows.
// The losing process must exit immediately so it never reaches Gateway startup.
let gotElectronLock: boolean | 'pending' | undefined = undefined;

let releaseProcessInstanceFileLock: () => void = () => {};

function acquireSingleInstanceLock(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronApp = require('electron').app;
  if (electronApp && typeof electronApp.requestSingleInstanceLock === 'function') {
    return electronApp.requestSingleInstanceLock() ?? false;
  }
  return false;
}

// In E2E mode or when app is ready, get the lock immediately
if (isE2EMode) {
  gotElectronLock = true;
} else if (isAppReady()) {
  gotElectronLock = acquireSingleInstanceLock();
}
// If app isn't ready yet, we'll acquire the lock during app.whenReady()
// Use 'pending' to indicate we need to acquire the lock later
if (gotElectronLock === undefined && !isE2EMode) {
  gotElectronLock = 'pending';
}

// Global references
let mainWindow: BrowserWindow | null = null;
let gatewayManager!: GatewayManager;
let clawHubService!: ClawHubService;
let hostEventBus!: HostEventBus;
let hostApiServer: Server | null = null;
const mainWindowFocusState = createMainWindowFocusState();
const quitLifecycleState = createQuitLifecycleState();

// Determine if we have the lock - for 'pending', we'll acquire it inside the block
const gotTheLock = isE2EMode || gotElectronLock === true || gotElectronLock === 'pending';

/**
 * Resolve the icons directory path (works in both dev and packaged mode)
 */
function getIconsDir(): string {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronApp = require('electron').app;
  const isPackaged = electronApp?.isPackaged ?? false;
  if (isPackaged) {
    // Packaged: icons are in extraResources → process.resourcesPath/resources/icons
    return join(process.resourcesPath, 'resources', 'icons');
  }
  // Development: relative to dist-electron/main/
  return join(__dirname, '../../resources/icons');
}

/**
 * Get the app icon for the current platform
 */
function getAppIcon(): Electron.NativeImage | undefined {
  if (process.platform === 'darwin') return undefined; // macOS uses the app bundle icon

  const iconsDir = getIconsDir();
  const iconPath =
    process.platform === 'win32'
      ? join(iconsDir, 'icon.ico')
      : join(iconsDir, 'icon.png');
  const icon = nativeImage.createFromPath(iconPath);
  return icon.isEmpty() ? undefined : icon;
}

/**
 * Create the main application window
 */
function createWindow(): BrowserWindow {
  const isMac = process.platform === 'darwin';
  const isWindows = process.platform === 'win32';
  const useCustomTitleBar = isWindows;
  const shouldSkipSetupForE2E = process.env.HERMESCLAW_E2E_SKIP_SETUP === '1';

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    icon: getAppIcon(),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      webviewTag: true, // Enable <webview> for embedding OpenClaw Control UI
    },
    titleBarStyle: isMac ? 'hiddenInset' : useCustomTitleBar ? 'hidden' : 'default',
    trafficLightPosition: isMac ? { x: 16, y: 16 } : undefined,
    frame: isMac || !useCustomTitleBar,
    show: false,
  });

  // Handle external links — only allow safe protocols to prevent arbitrary
  // command execution via shell.openExternal() (e.g. file://, ms-msdt:, etc.)
  win.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
        shell.openExternal(url);
      } else {
        logger.warn(`Blocked openExternal for disallowed protocol: ${parsed.protocol}`);
      }
    } catch {
      logger.warn(`Blocked openExternal for malformed URL: ${url}`);
    }
    return { action: 'deny' };
  });

  // Load the app
  if (process.env.VITE_DEV_SERVER_URL) {
    const rendererUrl = new URL(process.env.VITE_DEV_SERVER_URL);
    if (shouldSkipSetupForE2E) {
      rendererUrl.searchParams.set('e2eSkipSetup', '1');
    }
    win.loadURL(rendererUrl.toString());
    if (!isE2EMode) {
      win.webContents.openDevTools();
    }
  } else {
    win.loadFile(join(__dirname, '../../dist/index.html'), {
      query: shouldSkipSetupForE2E
        ? { e2eSkipSetup: '1' }
        : undefined,
    });
  }

  return win;
}

function focusWindow(win: BrowserWindow): void {
  if (win.isDestroyed()) {
    return;
  }

  if (win.isMinimized()) {
    win.restore();
  }

  win.show();
  win.focus();
}

function focusMainWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  clearPendingSecondInstanceFocus(mainWindowFocusState);
  focusWindow(mainWindow);
}

function createMainWindow(): BrowserWindow {
  const win = createWindow();
  let windowRevealed = false;

  const revealMainWindow = (reason: 'ready-to-show' | 'did-finish-load' | 'did-fail-load' | 'fallback-timeout') => {
    if (windowRevealed || mainWindow !== win || win.isDestroyed()) {
      return;
    }

    windowRevealed = true;
    clearTimeout(revealFallbackTimer);

    const action = consumeMainWindowReady(mainWindowFocusState);
    if (action === 'focus') {
      logger.info(`Revealing main window via ${reason} with deferred focus`);
      focusWindow(win);
      return;
    }

    logger.info(`Revealing main window via ${reason}`);
    win.show();
  };

  const revealFallbackTimer = setTimeout(() => {
    logger.warn(
      `Main window did not emit ready-to-show within ${MAIN_WINDOW_SHOW_FALLBACK_MS}ms; forcing it visible to avoid hidden startup`,
    );
    revealMainWindow('fallback-timeout');
  }, MAIN_WINDOW_SHOW_FALLBACK_MS);

  win.once('ready-to-show', () => {
    revealMainWindow('ready-to-show');
  });

  win.webContents.once('did-finish-load', () => {
    logger.debug('Main window renderer finished loading');
    revealMainWindow('did-finish-load');
  });

  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    logger.error(
      `Main window failed to load${isMainFrame ? ' main frame' : ''} (${errorCode}): ${errorDescription}`,
      validatedURL,
    );
    if (isMainFrame) {
      revealMainWindow('did-fail-load');
    }
  });

  win.webContents.on('render-process-gone', (_event, details) => {
    logger.error('Main window renderer process exited unexpectedly:', details);
  });

  win.on('show', () => {
    windowRevealed = true;
    clearTimeout(revealFallbackTimer);
  });

  win.on('close', (event) => {
    if (!isQuitting() && !isE2EMode) {
      event.preventDefault();
      win.hide();
    }
  });

  win.on('closed', () => {
    clearTimeout(revealFallbackTimer);
    if (mainWindow === win) {
      mainWindow = null;
    }
  });

  mainWindow = win;
  return win;
}

/**
 * Initialize the application
 */
async function initialize(): Promise<void> {
   // Initialize logger first
   logger.init();
   logger.info('=== HermesClaw Application Starting ===');
   logger.debug(
     // eslint-disable-next-line @typescript-eslint/no-require-imports
     `Runtime: platform=${process.platform}/${process.arch}, electron=${process.versions.electron}, node=${process.versions.node}, packaged=${require('electron').app?.isPackaged ?? false}, pid=${process.pid}, ppid=${process.ppid}`
   );

  if (!isE2EMode) {
    // Warm up network optimization (non-blocking)
    void warmupNetworkOptimization();

    // Initialize Telemetry early
    await initTelemetry();

    // Apply persisted proxy settings before creating windows or network requests.
    await applyProxySettings();
    await syncLaunchAtStartupSettingFromStore();
  } else {
    logger.info('Running in E2E mode: startup side effects minimized');
  }

  // Set application menu
  createMenu();

  // Create the main window
  const window = createMainWindow();

  // Create system tray
  if (!isE2EMode) {
    createTray(window);
  }

  // Override security headers ONLY for the OpenClaw Gateway Control UI.
  // The URL filter ensures this callback only fires for gateway requests,
  // avoiding unnecessary overhead on every other HTTP response.
  session.defaultSession.webRequest.onHeadersReceived(
    { urls: ['http://127.0.0.1:18789/*', 'http://localhost:18789/*'] },
    (details, callback) => {
      const headers = { ...details.responseHeaders };
      delete headers['X-Frame-Options'];
      delete headers['x-frame-options'];
      if (headers['Content-Security-Policy']) {
        headers['Content-Security-Policy'] = headers['Content-Security-Policy'].map(
          (csp) => csp.replace(/frame-ancestors\s+'none'/g, "frame-ancestors 'self' *")
        );
      }
      if (headers['content-security-policy']) {
        headers['content-security-policy'] = headers['content-security-policy'].map(
          (csp) => csp.replace(/frame-ancestors\s+'none'/g, "frame-ancestors 'self' *")
        );
      }
      callback({ responseHeaders: headers });
    },
  );

  // Register IPC handlers
  registerIpcHandlers(gatewayManager, clawHubService, window);

  hostApiServer = startHostApiServer({
    gatewayManager,
    clawHubService,
    eventBus: hostEventBus,
    mainWindow: window,
  });

  // Initialize extension system
  await extensionRegistry.initialize({
    gatewayManager,
    eventBus: hostEventBus,
    getMainWindow: () => mainWindow,
  });

  // Wire marketplace provider to ClawHubService if an extension provides one
  const marketplaceProvider = extensionRegistry.getMarketplaceProvider();
  if (marketplaceProvider) {
    clawHubService.setMarketplaceProvider(marketplaceProvider);
  }

// Register update handlers
   const updater = getAppUpdater();
   if (updater) {
     registerUpdateHandlers(updater, window);
   }

  // Note: Auto-check for updates is driven by the renderer (update store init)
  // so it respects the user's "Auto-check for updates" setting.

  // Repair any bootstrap files that only contain HermesClaw markers (no OpenClaw
  // template content). This fixes a race condition where ensureHermesClawContext()
  // previously created the file before the gateway could seed the full template.
  if (!isE2EMode) {
    void repairHermesClawOnlyBootstrapFiles().catch((error) => {
      logger.warn('Failed to repair bootstrap files:', error);
    });
  }

  // Pre-deploy built-in skills (feishu-doc, feishu-drive, feishu-perm, feishu-wiki)
  // to ~/.openclaw/skills/ so they are immediately available without manual install.
  if (!isE2EMode) {
    void ensureBuiltinSkillsInstalled().catch((error) => {
      logger.warn('Failed to install built-in skills:', error);
    });
  }

  // Pre-deploy bundled third-party skills from resources/preinstalled-skills.
  // This installs full skill directories (not only SKILL.md) in an idempotent,
  // non-destructive way and never blocks startup.
  if (!isE2EMode) {
    void ensurePreinstalledSkillsInstalled().catch((error) => {
      logger.warn('Failed to install preinstalled skills:', error);
    });
  }

  // Pre-deploy/upgrade bundled OpenClaw plugins (dingtalk, wecom, feishu, wechat)
  // to ~/.openclaw/extensions/ so they are always up-to-date after an app update.
  // Note: qqbot was moved to a built-in channel in OpenClaw 3.31.
  if (!isE2EMode) {
    void ensureAllBundledPluginsInstalled().catch((error) => {
      logger.warn('Failed to install/upgrade bundled plugins:', error);
    });
  }

  // Bridge gateway and host-side events before any auto-start logic runs, so
  // renderer subscribers observe the full startup lifecycle.
  gatewayManager.on('status', (status: { state: string }) => {
    hostEventBus.emit('gateway:status', status);
    if (status.state === 'running' && !isE2EMode) {
      void ensureHermesClawContext().catch((error) => {
        logger.warn('Failed to re-merge HermesClaw context after gateway reconnect:', error);
      });
      scheduleRuntimeStartupSync(
        gatewayManager,
        'Failed to sync runtime startup after gateway reconnect:',
      );
    }
  });

  gatewayManager.on('error', (error) => {
    hostEventBus.emit('gateway:error', { message: error.message });
  });

  gatewayManager.on('notification', (notification) => {
    hostEventBus.emit('gateway:notification', notification);
  });

  gatewayManager.on('chat:message', (data) => {
    hostEventBus.emit('gateway:chat-message', data);
  });

  gatewayManager.on('channel:status', (data) => {
    hostEventBus.emit('gateway:channel-status', data);
  });

  gatewayManager.on('exit', (code) => {
    hostEventBus.emit('gateway:exit', { code });
  });

  deviceOAuthManager.on('oauth:code', (payload) => {
    hostEventBus.emit('oauth:code', payload);
  });

  deviceOAuthManager.on('oauth:start', (payload) => {
    hostEventBus.emit('oauth:start', payload);
  });

  deviceOAuthManager.on('oauth:success', (payload) => {
    hostEventBus.emit('oauth:success', { ...payload, success: true });
  });

  deviceOAuthManager.on('oauth:error', (error) => {
    hostEventBus.emit('oauth:error', error);
  });

  browserOAuthManager.on('oauth:start', (payload) => {
    hostEventBus.emit('oauth:start', payload);
  });

  browserOAuthManager.on('oauth:code', (payload) => {
    hostEventBus.emit('oauth:code', payload);
  });

  browserOAuthManager.on('oauth:success', (payload) => {
    hostEventBus.emit('oauth:success', { ...payload, success: true });
  });

  browserOAuthManager.on('oauth:error', (error) => {
    hostEventBus.emit('oauth:error', error);
  });

  whatsAppLoginManager.on('qr', (data) => {
    hostEventBus.emit('channel:whatsapp-qr', data);
  });

  whatsAppLoginManager.on('success', (data) => {
    hostEventBus.emit('channel:whatsapp-success', data);
  });

  whatsAppLoginManager.on('error', (error) => {
    hostEventBus.emit('channel:whatsapp-error', error);
  });

  // Start Gateway automatically (this seeds missing bootstrap files with full templates)
  const gatewayAutoStart = await getSetting('gatewayAutoStart');
  if (!isE2EMode && gatewayAutoStart) {
    try {
      await syncAllProviderAuthToRuntime();
      logger.debug('Auto-starting Gateway...');
      await gatewayManager.start();
      logger.info('Gateway auto-start succeeded');
    } catch (error) {
      logger.error('Gateway auto-start failed:', error);
      mainWindow?.webContents.send('gateway:error', String(error));
    }
  } else if (isE2EMode) {
    logger.info('Gateway auto-start skipped in E2E mode');
  } else {
    logger.info('Gateway auto-start disabled in settings');
  }

  if (!isE2EMode) {
    scheduleRuntimeStartupSync(
      gatewayManager,
      'Failed to sync runtime startup during initialization:',
    );
  }

  // Merge HermesClaw context snippets into the workspace bootstrap files.
  // The gateway seeds workspace files asynchronously after its HTTP server
  // is ready, so ensureHermesClawContext will retry until the target files appear.
  if (!isE2EMode) {
    void ensureHermesClawContext().catch((error) => {
      logger.warn('Failed to merge HermesClaw context into workspace:', error);
    });
  }

  // Auto-install openclaw CLI and shell completions (non-blocking).
  if (!isE2EMode) {
    void autoInstallCliIfNeeded((installedPath) => {
      mainWindow?.webContents.send('openclaw:cli-installed', installedPath);
    }).then(() => {
      generateCompletionCache();
      installCompletionToProfile();
    }).catch((error) => {
      logger.warn('CLI auto-install failed:', error);
    });
  }
}

if (gotTheLock) {
   // If we didn't have the lock at module load time, acquire it now
   if (gotElectronLock !== true && !isE2EMode) {
     // In development mode with vite-plugin-electron, the lock may not be available yet.
     // Check if we're in a dev environment (VITE_DEV_SERVER_URL is set by vite-plugin-electron)
     const inViteDev = process.env.VITE_DEV_SERVER_URL !== undefined;
     if (inViteDev) {
       // In vite dev, skip the lock check - just proceed
       // eslint-disable-next-line no-useless-assignment
       gotElectronLock = true;
     } else {
       gotElectronLock = acquireSingleInstanceLock();
       if (!gotElectronLock) {
         console.info('[HermesClaw] Another instance already holds the single-instance lock; exiting duplicate process');
         process.exit(0);
       }
     }
   }

   // Get file lock (only if app is now ready)
   if (!isE2EMode) {
     try {
       // eslint-disable-next-line @typescript-eslint/no-require-imports
       const electronApp = require('electron').app;
       if (electronApp && typeof electronApp.getPath === 'function') {
        const fileLock = acquireProcessInstanceFileLock({
          userDataDir: electronApp.getPath('userData'),
          lockName: 'hermesclaw',
          force: true,
        });
        releaseProcessInstanceFileLock = fileLock.release;
        if (!fileLock.acquired) {
          const ownerDescriptor = fileLock.ownerPid
            ? `${fileLock.ownerFormat ?? 'legacy'} pid=${fileLock.ownerPid}`
            : fileLock.ownerFormat === 'unknown'
              ? 'unknown lock format/content'
              : 'unknown owner';
          console.info(
            `[HermesClaw] Another instance already holds process lock (${fileLock.lockPath}, ${ownerDescriptor}); exiting duplicate process`,
          );
          process.exit(0);
        }
      }
    } catch (error) {
      console.warn('[HermesClaw] Failed to acquire process instance file lock; continuing with Electron single-instance lock only', error);
    }
  }

  const requestQuitOnSignal = createSignalQuitHandler({
    logInfo: (message) => logger.info(message),
    requestQuit: () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const electronApp = require('electron').app;
      if (electronApp && typeof electronApp.quit === 'function') {
        electronApp.quit();
      } else {
        process.exit(0);
      }
    },
  });

  process.on('exit', () => {
    releaseProcessInstanceFileLock();
  });

  process.once('SIGINT', () => requestQuitOnSignal('SIGINT'));
  process.once('SIGTERM', () => requestQuitOnSignal('SIGTERM'));

  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronAppForHandlers = require('electron').app;
  if (electronAppForHandlers && typeof electronAppForHandlers.on === 'function') {
    electronAppForHandlers.on('will-quit', () => {
      releaseProcessInstanceFileLock();
    });
  }

  if (process.platform === 'win32' && electronAppForHandlers && typeof electronAppForHandlers.setAppUserModelId === 'function') {
    electronAppForHandlers.setAppUserModelId(WINDOWS_APP_USER_MODEL_ID);
  }

  gatewayManager = new GatewayManager();
  clawHubService = new ClawHubService();
  hostEventBus = new HostEventBus();

  // Register builtin extensions and load manifest
  registerAllBuiltinExtensions();
  loadExternalMainExtensions();
  void loadExtensionsFromManifest().catch((err) => {
    logger.warn('Failed to load extensions from manifest:', err);
  });

  // When a second instance is launched, focus the existing window instead.
  if (electronAppForHandlers && typeof electronAppForHandlers.on === 'function') {
    electronAppForHandlers.on('second-instance', () => {
      logger.info('Second HermesClaw instance detected; redirecting to the existing window');

      const focusRequest = requestSecondInstanceFocus(
        mainWindowFocusState,
        Boolean(mainWindow && !mainWindow.isDestroyed()),
      );

      if (focusRequest === 'focus-now') {
        focusMainWindow();
        return;
      }

      logger.debug('Main window is not ready yet; deferring second-instance focus until ready-to-show');
    });
  }

  // Application lifecycle
  if (electronAppForHandlers && typeof electronAppForHandlers.whenReady === 'function') {
    electronAppForHandlers.whenReady().then(() => {
      void initialize().catch((error) => {
        logger.error('Application initialization failed:', error);
      });

      // Register activate handler AFTER app is ready to prevent
      // "Cannot create BrowserWindow before app is ready" on macOS.
      if (typeof electronAppForHandlers.on === 'function') {
        electronAppForHandlers.on('activate', () => {
          if (BrowserWindow.getAllWindows().length === 0) {
            createMainWindow();
          } else {
            focusMainWindow();
          }
        });
      }
    });
  }

  if (electronAppForHandlers && typeof electronAppForHandlers.on === 'function') {
    electronAppForHandlers.on('window-all-closed', () => {
      if (process.platform !== 'darwin' || isE2EMode) {
        if (typeof electronAppForHandlers.quit === 'function') {
          electronAppForHandlers.quit();
        }
      }
    });

    electronAppForHandlers.on('before-quit', (event) => {
      setQuitting();
      const action = requestQuitLifecycleAction(quitLifecycleState);

      if (action === 'allow-quit') {
        return;
      }

      event.preventDefault();

      if (action === 'cleanup-in-progress') {
        logger.debug('Quit requested while cleanup already in progress; waiting for shutdown task to finish');
        return;
      }

      hostEventBus.closeAll();
      hostApiServer?.close();
      void extensionRegistry.teardownAll();

      const stopPromise = gatewayManager.stop().catch((err) => {
        logger.warn('gatewayManager.stop() error during quit:', err);
      });
      const timeoutPromise = new Promise<'timeout'>((resolve) => {
        setTimeout(() => resolve('timeout'), 5000);
      });

      void Promise.race([stopPromise.then(() => 'stopped' as const), timeoutPromise]).then((result) => {
        if (result === 'timeout') {
          logger.warn('Gateway shutdown timed out during app quit; proceeding with forced quit');
          void gatewayManager.forceTerminateOwnedProcessForQuit().then((terminated) => {
            if (terminated) {
              logger.warn('Forced gateway process termination completed after quit timeout');
            }
          }).catch((err) => {
            logger.warn('Forced gateway termination failed after quit timeout:', err);
          });
        }
        markQuitCleanupCompleted(quitLifecycleState);
        if (typeof electronAppForHandlers.quit === 'function') {
          electronAppForHandlers.quit();
        }
      });
    });
  }

  // Best-effort Gateway cleanup on unexpected crashes.
  // These handlers attempt to terminate the Gateway child process within a
  // short timeout before force-exiting, preventing orphaned processes.
  const emergencyGatewayCleanup = (reason: string, error: unknown): void => {
    logger.error(`${reason}:`, error);
    try {
      void gatewayManager?.stop().catch(() => { /* ignore */ });
    } catch {
      // ignore — stop() may not be callable if state is corrupted
    }
    // Give Gateway stop a brief window, then force-exit.
    setTimeout(() => {
      process.exit(1);
    }, 3000).unref();
  };

  process.on('uncaughtException', (error) => {
    emergencyGatewayCleanup('Uncaught exception in main process', error);
  });

  process.on('unhandledRejection', (reason) => {
    emergencyGatewayCleanup('Unhandled promise rejection in main process', reason);
  });
}

// Export for testing
export { mainWindow, gatewayManager };
