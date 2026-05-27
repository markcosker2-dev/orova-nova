#!/usr/bin/env zx

/**
 * bundle-hermes-agent.mjs
 *
 * Builds a pinned HermesAgent Python runtime into build/hermes-agent/ for
 * electron-builder to ship as an app-owned extra resource. HermesAgent is a
 * Python package, so it deliberately stays out of npm dependencies.
 */

import 'zx/globals';
import { spawn } from 'node:child_process';

const ROOT = path.resolve(__dirname, '..');
const MANIFEST_PATH = path.join(ROOT, 'resources', 'hermes-agent', 'manifest.json');
const OUTPUT = path.join(ROOT, 'build', 'hermes-agent');

function loadManifest() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    throw new Error(`Missing HermesAgent manifest: ${MANIFEST_PATH}`);
  }

  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
  const requiredStringFields = [
    'packageName',
    'version',
    'releaseTag',
    'source',
    'installSpec',
    'pythonVersion',
  ];

  for (const field of requiredStringFields) {
    if (typeof manifest[field] !== 'string' || manifest[field].trim() === '') {
      throw new Error(`Invalid HermesAgent manifest: missing ${field}`);
    }
  }

  if (!Array.isArray(manifest.entrypoints) || manifest.entrypoints.length === 0) {
    throw new Error('Invalid HermesAgent manifest: entrypoints must be a non-empty array');
  }

  if (manifest.packageName !== 'hermes-agent') {
    throw new Error(`Unexpected HermesAgent package name: ${manifest.packageName}`);
  }

  return manifest;
}

function resolveManifestOverrides(manifest) {
  const releaseTag = process.env.HERMES_AGENT_RELEASE_TAG?.trim() || manifest.releaseTag;
  const installSpec = process.env.HERMES_AGENT_INSTALL_SPEC?.trim()
    || (releaseTag !== manifest.releaseTag
      ? `hermes-agent @ https://github.com/NousResearch/hermes-agent/archive/refs/tags/${releaseTag}.tar.gz`
      : manifest.installSpec);

  return {
    ...manifest,
    version: process.env.HERMES_AGENT_VERSION?.trim() || manifest.version,
    releaseTag,
    source: process.env.HERMES_AGENT_SOURCE?.trim() || manifest.source,
    installSpec,
    pythonVersion: process.env.HERMES_AGENT_PYTHON_VERSION?.trim() || manifest.pythonVersion,
  };
}

function getTargetId() {
  return `${os.platform()}-${os.arch()}`;
}

function getUvBinary() {
  if (process.env.UV_BINARY) return process.env.UV_BINARY;

  const binaryName = os.platform() === 'win32' ? 'uv.exe' : 'uv';
  const bundledUv = path.join(ROOT, 'resources', 'bin', getTargetId(), binaryName);
  if (fs.existsSync(bundledUv)) return bundledUv;

  return 'uv';
}

function getVenvPython(venvDir) {
  if (os.platform() === 'win32') {
    return path.join(venvDir, 'Scripts', 'python.exe');
  }
  return path.join(venvDir, 'bin', 'python');
}

function runCommand(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', shell: false });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${command} ${args.join(' ')} failed with exit code ${code}`));
      }
    });
  });
}

function parseExtraArgs(value) {
  if (!value?.trim()) return [];

  const matches = value.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || [];
  return matches.map((arg) => arg.replace(/^(["'])(.*)\1$/, '$2'));
}

async function runCommandWithRetries(command, args, options = {}) {
  const attempts = options.attempts || 3;
  const delayMs = options.delayMs || 5000;
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await runCommand(command, args);
      return;
    } catch (error) {
      lastError = error;
      if (attempt >= attempts) break;

      echo`⚠️  Command failed, retrying ${attempt + 1}/${attempts} after ${delayMs}ms...`;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }

  throw lastError;
}

function wrapperContent(entrypoint, venvDir) {
  if (os.platform() === 'win32') {
    const scriptPath = path.join(venvDir, 'Scripts', `${entrypoint}.exe`);
    return `@echo off\r\n"%~dp0..\\.venv\\Scripts\\${path.basename(scriptPath)}" %*\r\n`;
  }

  return `#!/usr/bin/env sh\nSCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexec "$SCRIPT_DIR/../.venv/bin/${entrypoint}" "$@"\n`;
}

async function writeWrappers(manifest, venvDir) {
  const binDir = path.join(OUTPUT, 'bin');
  await fs.ensureDir(binDir);

  for (const entrypoint of manifest.entrypoints) {
    const suffix = os.platform() === 'win32' ? '.cmd' : '';
    const wrapperPath = path.join(binDir, `${entrypoint}${suffix}`);
    await fs.writeFile(wrapperPath, wrapperContent(entrypoint, venvDir), 'utf8');
    if (os.platform() !== 'win32') {
      await fs.chmod(wrapperPath, 0o755);
    }
  }
}

async function removePythonCaches(rootDir) {
  const cacheDirs = await glob('**/__pycache__', { cwd: rootDir, absolute: true, onlyDirectories: true });
  for (const dir of cacheDirs) {
    await fs.remove(dir);
  }

  const cacheFiles = await glob('**/*.{pyc,pyo}', { cwd: rootDir, absolute: true });
  for (const file of cacheFiles) {
    await fs.remove(file);
  }
}

async function smokeTest(manifest, pythonPath) {
  const script = `import importlib.metadata as m; assert m.version('${manifest.packageName}') == '${manifest.version}'`;
  await runCommand(pythonPath, ['-c', script]);
}

async function bundleHermesAgent() {
  const manifest = resolveManifestOverrides(loadManifest());
  const uvBinary = getUvBinary();
  const venvDir = path.join(OUTPUT, '.venv');
  const pythonPath = getVenvPython(venvDir);
  const packageSpec = manifest.installSpec;
  const pipArgs = parseExtraArgs(process.env.HERMES_AGENT_PIP_ARGS);

  echo`📦 Bundling HermesAgent ${manifest.version} (${manifest.releaseTag})...`;
  echo`   uv: ${uvBinary}`;
  echo`   Python: ${manifest.pythonVersion}`;

  await fs.remove(OUTPUT);
  await fs.ensureDir(OUTPUT);

  await runCommand(uvBinary, ['venv', '--python', manifest.pythonVersion, venvDir]);
  await runCommandWithRetries(
    uvBinary,
    ['pip', 'install', '--python', pythonPath, ...pipArgs, packageSpec],
    { attempts: 4, delayMs: 5000 },
  );

  await fs.writeFile(path.join(OUTPUT, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  await writeWrappers(manifest, venvDir);
  await smokeTest(manifest, pythonPath);
  await removePythonCaches(OUTPUT);

  echo`✅ HermesAgent bundled: ${OUTPUT}`;
}

function checkConfiguration() {
  const manifest = resolveManifestOverrides(loadManifest());
  echo`✅ HermesAgent manifest OK: ${manifest.packageName} ${manifest.version} (${manifest.releaseTag})`;
  echo`   source: ${manifest.source}`;
  echo`   python: ${manifest.pythonVersion}`;
  echo`   output: ${OUTPUT}`;
}

if (argv.check) {
  checkConfiguration();
} else {
  await bundleHermesAgent();
}
