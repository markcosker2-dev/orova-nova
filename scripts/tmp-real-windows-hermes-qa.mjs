import electronBinaryPath from 'electron';
import { _electron as electron, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, rm, readFile, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const repoRoot = resolve(process.cwd());
const electronEntry = join(repoRoot, 'dist-electron/main/index.js');

async function removeTempDir(dir) {
  const cleanup = rm(dir, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 200,
  });

  if (process.platform !== 'win32') {
    await cleanup;
    return;
  }

  await Promise.race([
    cleanup.catch(() => undefined),
    new Promise((resolvePromise) => setTimeout(resolvePromise, 5_000)),
  ]);
}

async function allocatePort() {
  return await new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('Failed to allocate port')));
        return;
      }
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolvePort(address.port);
      });
    });
  });
}

async function getStableWindow(app) {
  const deadline = Date.now() + 30_000;
  let page = await app.firstWindow();

  while (Date.now() < deadline) {
    const openWindows = app.windows().filter((candidate) => !candidate.isClosed());
    const currentWindow = openWindows.at(-1) ?? page;

    if (currentWindow && !currentWindow.isClosed()) {
      try {
        await currentWindow.waitForLoadState('domcontentloaded', { timeout: 5_000 });
        return currentWindow;
      } catch (error) {
        const message = String(error);
        if (!message.includes('has been closed') && !message.includes('Timeout')) {
          throw error;
        }
      }
    }

    try {
      page = await app.waitForEvent('window', { timeout: 2_000 });
    } catch {
      // keep polling
    }
  }

  throw new Error('No stable Electron window became available');
}

async function closeElectronApp(app, timeoutMs = 5_000) {
  let closed = false;

  await Promise.race([
    (async () => {
      const [closeResult] = await Promise.allSettled([
        app.waitForEvent('close', { timeout: timeoutMs }),
        app.evaluate(({ app: electronApp }) => {
          electronApp.quit();
        }),
      ]);

      if (closeResult.status === 'fulfilled') {
        closed = true;
      }
    })(),
    new Promise((resolvePromise) => setTimeout(resolvePromise, timeoutMs)),
  ]);

  if (closed) {
    return;
  }

  try {
    await app.close();
  } catch {
    try {
      app.process().kill('SIGKILL');
    } catch {
      // ignore
    }
  }
}

async function launchHermesClawElectron(homeDir, userDataDir, options = {}) {
  const hostApiPort = await allocatePort();
  const electronEnv = process.platform === 'linux' ? { ELECTRON_DISABLE_SANDBOX: '1' } : {};

  return await electron.launch({
    executablePath: electronBinaryPath,
    args: [electronEntry],
    env: {
      ...process.env,
      ...electronEnv,
      HOME: homeDir,
      USERPROFILE: homeDir,
      APPDATA: join(homeDir, 'AppData', 'Roaming'),
      LOCALAPPDATA: join(homeDir, 'AppData', 'Local'),
      XDG_CONFIG_HOME: join(homeDir, '.config'),
      HERMESCLAW_E2E: '1',
      HERMESCLAW_USER_DATA_DIR: userDataDir,
      ...(options.skipSetup ? { HERMESCLAW_E2E_SKIP_SETUP: '1' } : {}),
      HERMESCLAW_PORT_HERMESCLAW_HOST_API: String(hostApiPort),
    },
    timeout: 90_000,
  });
}

async function findFileRecursively(rootDir, fileName) {
  const entries = await readdir(rootDir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(rootDir, entry.name);
    if (entry.isFile() && entry.name === fileName) {
      return fullPath;
    }
    if (entry.isDirectory()) {
      const nested = await findFileRecursively(fullPath, fileName).catch(() => undefined);
      if (nested) {
        return nested;
      }
    }
  }
  return undefined;
}

function parseWslDistroOutput(output) {
  return output
    .replaceAll('\0', '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^Windows Subsystem for Linux Distributions:/i.test(line));
}

function getHostWslDistros() {
  if (process.platform !== 'win32') {
    return [];
  }

  try {
    const output = execFileSync('wsl.exe', ['-l', '-q'], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });

    const utf16 = parseWslDistroOutput(output.toString('utf16le'));
    if (utf16.length > 0) {
      return utf16;
    }

    return parseWslDistroOutput(output.toString('utf8'));
  } catch {
    return [];
  }
}

async function run() {
  const homeDir = await mkdtemp(join(tmpdir(), 'hermesclaw-real-qa-home-'));
  const userDataDir = await mkdtemp(join(tmpdir(), 'hermesclaw-real-qa-user-data-'));
  const hostWslDistros = getHostWslDistros();
  const hostHasWsl = hostWslDistros.length > 0;

  console.log('QA_HOME_DIR=' + homeDir);
  console.log('QA_USER_DATA_DIR=' + userDataDir);
  console.log('QA_HOST_WSL_DISTROS=' + JSON.stringify(hostWslDistros));

  await mkdir(join(homeDir, '.config'), { recursive: true });
  await mkdir(join(homeDir, 'AppData', 'Local'), { recursive: true });
  await mkdir(join(homeDir, 'AppData', 'Roaming'), { recursive: true });

  let app;
  try {
    // Step 1: real setup gating on Windows defaults
    app = await launchHermesClawElectron(homeDir, userDataDir);
    let page = await getStableWindow(app);

    await expect(page.getByTestId('setup-page')).toBeVisible({ timeout: 30_000 });
    await page.getByTestId('setup-next-button').click();
    await expect(page.getByTestId('setup-install-choice-openclaw')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('setup-runtime-wsl2-notice')).toBeVisible();

    const hermesChoice = page.getByTestId('setup-install-choice-hermes');
    const bothChoice = page.getByTestId('setup-install-choice-both');

    if (hostHasWsl) {
      await expect(hermesChoice).toBeEnabled();
      await expect(bothChoice).toBeEnabled();
      console.log('QA_SETUP_GATING=PASS_WITH_WSL');
    } else {
      await expect(hermesChoice).toBeDisabled();
      await expect(bothChoice).toBeDisabled();
      console.log('QA_SETUP_GATING=PASS_NO_WSL');
    }

    await closeElectronApp(app);
    app = undefined;

    // Step 2: real settings save flow, no IPC mocks
    app = await launchHermesClawElectron(homeDir, userDataDir, { skipSetup: true });
    page = await getStableWindow(app);
    await expect(page.getByTestId('main-layout')).toBeVisible({ timeout: 30_000 });
    await page.getByTestId('sidebar-nav-settings').click();
    await expect(page.getByTestId('settings-page')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('settings-runtime-panel')).toBeVisible();
    await expect(page.getByTestId('settings-runtime-config-panel')).toBeVisible();

    await page.getByTestId('settings-runtime-mode-native').click();
    await page.getByTestId('settings-runtime-native-path').fill('C:\\Hermes\\.hermes');
    await page.getByTestId('settings-runtime-wsl-distro').fill('Ubuntu-24.04');
    await page.getByTestId('settings-runtime-save-button').click();

    await expect(page.getByTestId('settings-runtime-save-button')).toBeDisabled({ timeout: 15_000 });
    await expect(page.getByTestId('settings-runtime-native-path')).toHaveValue('C:\\Hermes\\.hermes');
    await expect(page.getByTestId('settings-runtime-wsl-distro')).toHaveValue('Ubuntu-24.04');
    console.log('QA_SETTINGS_SAVE_UI=PASS');

    const recheckButton = page.getByTestId('settings-runtime-bridge-recheck-button');
    if (await recheckButton.isVisible().catch(() => false)) {
      await recheckButton.click();
      await page.waitForTimeout(1_500);
      const bridgeError = page.getByTestId('settings-runtime-bridge-error');
      const bridgeErrorVisible = await bridgeError.isVisible().catch(() => false);
      const bridgeErrorText = bridgeErrorVisible ? ((await bridgeError.textContent()) ?? '').trim() : '';
      console.log('QA_BRIDGE_RECHECK_VISIBLE=' + String(true));
      console.log('QA_BRIDGE_RECHECK_ERROR=' + bridgeErrorText);
    }

    await closeElectronApp(app);
    app = undefined;

    // Step 3: inspect persisted electron-store payload
    const settingsFile = await findFileRecursively(userDataDir, 'settings.json');
    if (!settingsFile) {
      throw new Error(`Could not find persisted settings.json under ${userDataDir}`);
    }

    const persistedJson = JSON.parse(await readFile(settingsFile, 'utf8'));
    console.log('QA_SETTINGS_FILE=' + settingsFile);
    console.log('QA_PERSISTED_RUNTIME=' + JSON.stringify(persistedJson.runtime));

    if (persistedJson.runtime?.windowsHermesPreferredMode !== 'native') {
      throw new Error('Persisted runtime preferred mode was not native');
    }
    if (persistedJson.runtime?.windowsHermesNativePath !== 'C:\\Hermes\\.hermes') {
      throw new Error('Persisted runtime native path mismatch');
    }
    if (persistedJson.runtime?.windowsHermesWslDistro !== 'Ubuntu-24.04') {
      throw new Error('Persisted runtime WSL distro mismatch');
    }
    console.log('QA_PERSISTENCE_FILE=PASS');

    // Step 4: relaunch and verify values hydrate back into the real app
    app = await launchHermesClawElectron(homeDir, userDataDir, { skipSetup: true });
    page = await getStableWindow(app);
    await expect(page.getByTestId('main-layout')).toBeVisible({ timeout: 30_000 });
    await page.getByTestId('sidebar-nav-settings').click();
    await expect(page.getByTestId('settings-page')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('settings-runtime-config-panel')).toBeVisible();
    await expect(page.getByTestId('settings-runtime-native-path')).toHaveValue('C:\\Hermes\\.hermes');
    await expect(page.getByTestId('settings-runtime-wsl-distro')).toHaveValue('Ubuntu-24.04');
    await expect(page.getByTestId('settings-runtime-save-button')).toBeDisabled();
    console.log('QA_RELAUNCH_HYDRATION=PASS');

    await closeElectronApp(app);
    app = undefined;

    console.log('QA_RESULT=PASS');
  } finally {
    if (app) {
      await closeElectronApp(app).catch(() => undefined);
    }
    await removeTempDir(homeDir);
    await removeTempDir(userDataDir);
  }
}

run().catch((error) => {
  console.error('QA_RESULT=FAIL');
  console.error(error);
  process.exitCode = 1;
});
