#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function findBundledRuntimeRootFile(openclawRoot) {
  const distDir = path.join(openclawRoot, 'dist');
  if (!fs.existsSync(distDir)) return null;
  return fs
    .readdirSync(distDir)
    .filter((name) => /^bundled-runtime-root-.*\.js$/.test(name))
    .map((name) => path.join(distDir, name))
    .sort((left, right) => left.localeCompare(right))[0] ?? null;
}

function replaceRequired(contents, search, replace, label) {
  if (contents.includes(replace)) return contents;
  if (!contents.includes(search)) {
    throw new Error(`Unable to patch OpenClaw runtime: expected ${label} snippet not found`);
  }
  return contents.replace(search, replace);
}

function replaceOneOfRequired(contents, searches, replace, label) {
  const search = searches.find((candidate) => contents.includes(candidate));
  if (!search) {
    if (contents.includes(replace)) return contents;
    throw new Error(`Unable to patch OpenClaw runtime: expected ${label} snippet not found`);
  }
  return contents.replace(search, replace);
}

export function patchOpenClawRuntimeRoot(openclawRoot) {
  const runtimeRootFile = findBundledRuntimeRootFile(openclawRoot);
  if (!runtimeRootFile) return false;

  let contents = fs.readFileSync(runtimeRootFile, 'utf8');

  contents = replaceOneOfRequired(
    contents,
    [
      'const MIRRORED_CORE_RUNTIME_DEP_NAMES = ["semver", "tslog"];',
      'const MIRRORED_CORE_RUNTIME_DEP_NAMES = ["json5", "semver", "tslog"];',
      'const MIRRORED_CORE_RUNTIME_DEP_NAMES = ["@agentclientprotocol/sdk", "croner", "dotenv", "jiti", "json5", "jszip", "markdown-it", "semver", "tar", "tslog", "web-push", "yaml"];',
      'const MIRRORED_CORE_RUNTIME_DEP_NAMES = ["@agentclientprotocol/sdk", "@mariozechner/pi-ai", "@mariozechner/pi-coding-agent", "croner", "dotenv", "global-agent", "jiti", "json5", "jszip", "markdown-it", "openai", "semver", "tar", "tslog", "web-push", "yaml"];',
      'const MIRRORED_CORE_RUNTIME_DEP_NAMES = ["@agentclientprotocol/sdk", "@mariozechner/pi-ai", "@mariozechner/pi-coding-agent", "croner", "dotenv", "global-agent", "jiti", "json5", "jszip", "markdown-it", "openai", "osc-progress", "semver", "tar", "tslog", "web-push", "yaml"];',
    ],
    'const MIRRORED_CORE_RUNTIME_DEP_NAMES = ["@agentclientprotocol/sdk", "@mariozechner/pi-ai", "@mariozechner/pi-coding-agent", "chokidar", "croner", "dotenv", "global-agent", "jiti", "json5", "jszip", "markdown-it", "openai", "osc-progress", "semver", "tar", "tslog", "web-push", "yaml"];',
    'root mirrored runtime dependencies',
  );

  const originalDependencyOwners = `function collectBundledRuntimeDependencyOwners(packageRoot) {
\tconst extensionsDir = path.join(packageRoot, "dist", "extensions");
\tif (!fs.existsSync(extensionsDir)) return /* @__PURE__ */ new Map();
\tconst owners = /* @__PURE__ */ new Map();
\tfor (const entry of fs.readdirSync(extensionsDir, { withFileTypes: true })) {
\t\tif (!entry.isDirectory()) continue;
\t\tconst pluginId = entry.name;
\t\tconst packageJson = readJsonObject(path.join(extensionsDir, pluginId, "package.json"));
\t\tif (!packageJson) continue;
\t\tfor (const [name, rawVersion] of Object.entries(collectRuntimeDeps(packageJson))) {
\t\t\tconst dep = parseInstallableRuntimeDep(name, rawVersion);
\t\t\tif (!dep) continue;
\t\t\tconst existing = owners.get(dep.name);
\t\t\tif (existing) {
\t\t\t\texisting.pluginIds = [...new Set([...existing.pluginIds, pluginId])].toSorted((left, right) => left.localeCompare(right));
\t\t\t\tcontinue;
\t\t\t}
\t\t\towners.set(dep.name, {
\t\t\t\t...dep,
\t\t\t\tpluginIds: [pluginId]
\t\t\t});
\t\t}
\t}
\treturn owners;
}`;

  const newDependencyOwners = `function mergeRuntimeDependencyOwner(owners, dep, pluginId) {
\tconst existing = owners.get(dep.name);
\tif (existing) {
\t\texisting.pluginIds = [...new Set([...existing.pluginIds, pluginId])].toSorted((left, right) => left.localeCompare(right));
\t\treturn;
\t}
\towners.set(dep.name, {
\t\t...dep,
\t\tpluginIds: [pluginId]
\t});
}
function collectBundledRuntimeDependencyOwners(packageRoot) {
\tconst owners = /* @__PURE__ */ new Map();
\tconst extensionsDir = path.join(packageRoot, "dist", "extensions");
\tif (fs.existsSync(extensionsDir)) for (const entry of fs.readdirSync(extensionsDir, { withFileTypes: true })) {
\t\tif (!entry.isDirectory()) continue;
\t\tconst pluginId = entry.name;
\t\tconst packageJson = readJsonObject(path.join(extensionsDir, pluginId, "package.json"));
\t\tif (!packageJson) continue;
\t\tfor (const [name, rawVersion] of Object.entries(collectRuntimeDeps(packageJson))) {
\t\t\tconst dep = parseInstallableRuntimeDep(name, rawVersion);
\t\t\tif (!dep) continue;
\t\t\tmergeRuntimeDependencyOwner(owners, dep, pluginId);
\t\t}
\t}
\tconst packageJson = readJsonObject(path.join(packageRoot, "package.json"));
\tif (packageJson) for (const [name, rawVersion] of Object.entries(collectRuntimeDeps(packageJson))) {
\t\tconst dep = parseInstallableRuntimeDep(name, rawVersion);
\t\tif (!dep) continue;
\t\tmergeRuntimeDependencyOwner(owners, dep, MIRRORED_PACKAGE_RUNTIME_DEP_PLUGIN_ID);
\t}
\treturn owners;
}`;

  contents = replaceOneOfRequired(
    contents,
    [originalDependencyOwners],
    newDependencyOwners,
    'root package runtime dependency owner discovery',
  );

  const originalRootDistOwnerCheck = `\t\t\tconst owner = dependencyOwners.get(dependencyName);
\t\t\tif (!owner) continue;
\t\t\tif (isPluginOwnedDistImporter({
\t\t\t\trelativePath,
\t\t\t\tsource,
\t\t\t\tpluginIds: owner.pluginIds
\t\t\t})) continue;
\t\t\tconst dep = parseInstallableRuntimeDep(dependencyName, params.runtimeDeps[dependencyName]);
\t\t\tif (dep) mirrored.set(dep.name, {
\t\t\t\t...dep,
\t\t\t\tpluginIds: owner.pluginIds
\t\t\t});`;

  const newRootDistOwnerCheck = `\t\t\tconst owner = dependencyOwners.get(dependencyName);
\t\t\tconst effectiveOwner = owner ?? (typeof params.runtimeDeps[dependencyName] === "string" ? {
\t\t\t\tname: dependencyName,
\t\t\t\tversion: params.runtimeDeps[dependencyName],
\t\t\t\tpluginIds: [MIRRORED_PACKAGE_RUNTIME_DEP_PLUGIN_ID]
\t\t\t} : undefined);
\t\t\tif (!effectiveOwner) continue;
\t\t\tif (isPluginOwnedDistImporter({
\t\t\t\trelativePath,
\t\t\t\tsource,
\t\t\t\tpluginIds: effectiveOwner.pluginIds
\t\t\t})) continue;
\t\t\tconst dep = parseInstallableRuntimeDep(dependencyName, params.runtimeDeps[dependencyName]);
\t\t\tif (dep) mirrored.set(dep.name, {
\t\t\t\t...dep,
\t\t\t\tpluginIds: effectiveOwner.pluginIds
\t\t\t});`;

  contents = replaceOneOfRequired(
    contents,
    [originalRootDistOwnerCheck],
    newRootDistOwnerCheck,
    'root dist runtime dependency owner fallback',
  );

  const originalHelperTarget = `function isNpmCliPath(candidate) {
\tconst normalized = candidate.replaceAll("\\\\", "/").toLowerCase();
\treturn normalized.endsWith("/npm-cli.js") || normalized.endsWith("/npm/bin/npm-cli.js");
}
function resolveBundledRuntimeDepsNpmRunner(params) {`;

  const oldHelperTarget = `function isNpmCliPath(candidate) {
\tconst normalized = candidate.replaceAll("\\\\", "/").toLowerCase();
\treturn normalized.endsWith("/npm-cli.js") || normalized.endsWith("/npm/bin/npm-cli.js");
}
const WINDOWS_UNSAFE_CMD_CHARS_RE = /[&|<>%\\r\\n]/;
function escapeForCmdExe(arg) {
\tif (WINDOWS_UNSAFE_CMD_CHARS_RE.test(arg)) throw new Error(\`Refusing to pass unsafe cmd.exe argument: \${arg}\`);
\tconst escaped = arg.replace(/\\^/g, "^^");
\tif (!escaped.includes(" ") && !escaped.includes('"')) return escaped;
\treturn \`"\${escaped.replace(/"/g, '""')}"\`;
}
function buildCmdExeCommandLine(command, args) {
\treturn [escapeForCmdExe(command), ...args.map(escapeForCmdExe)].join(" ");
}
function resolveBundledRuntimeDepsNpmRunner(params) {`;

  const newHelperTarget = `function isNpmCliPath(candidate) {
\tconst normalized = candidate.replaceAll("\\\\", "/").toLowerCase();
\treturn normalized.endsWith("/npm-cli.js") || normalized.endsWith("/npm/bin/npm-cli.js");
}
const WINDOWS_UNSAFE_CMD_CHARS_RE = /[&|<>%\\r\\n]/;
function escapeForCmdExe(arg) {
\tif (WINDOWS_UNSAFE_CMD_CHARS_RE.test(arg)) throw new Error(\`Refusing to pass unsafe cmd.exe argument: \${arg}\`);
\tconst escaped = arg.replace(/\\^/g, "^^");
\tif (!escaped.includes(" ") && !escaped.includes('"')) return escaped;
\treturn \`"\${escaped.replace(/"/g, '""')}"\`;
}
function buildCmdExeCommandLine(command, args) {
\treturn [escapeForCmdExe(command), ...args.map(escapeForCmdExe)].join(" ");
}
function resolveWindowsNpmExecutableFromPath(env, pathImpl, existsSync) {
\tconst pathKey = resolvePathEnvKey(env, "win32");
\tconst rawPath = typeof env[pathKey] === "string" ? env[pathKey] : "";
\tfor (const dir of rawPath.split(";")) {
\t\tif (!dir) continue;
\t\tfor (const name of [
\t\t\t"npm.cmd",
\t\t\t"npm.exe"
\t\t]) {
\t\t\tconst candidate = pathImpl.resolve(dir, name);
\t\t\tif (!pathImpl.isAbsolute(candidate) || WINDOWS_UNSAFE_CMD_CHARS_RE.test(candidate)) continue;
\t\t\tif (existsSync(candidate)) return candidate;
\t\t}
\t}
\treturn undefined;
}
function resolveBundledRuntimeDepsNpmRunner(params) {`;

  contents = replaceOneOfRequired(
    contents,
    [originalHelperTarget, oldHelperTarget],
    newHelperTarget,
    'Windows npm PATH resolver helper',
  );

  const originalNpmFallback = `\t\tif (existsSync(npmExePath)) return {
\t\t\tcommand: npmExePath,
\t\t\targs: params.npmArgs
\t\t};
\t\tthrow new Error("Unable to resolve a safe npm executable on Windows");`;

  const oldNpmFallback = `\t\tif (existsSync(npmExePath)) return {
\t\t\tcommand: npmExePath,
\t\t\targs: params.npmArgs
\t\t};
\t\tconst npmCmdPath = pathImpl.resolve(nodeDir, "npm.cmd");
\t\tif (existsSync(npmCmdPath)) return {
\t\t\tcommand: env.ComSpec ?? "cmd.exe",
\t\t\targs: [
\t\t\t\t"/d",
\t\t\t\t"/s",
\t\t\t\t"/c",
\t\t\t\tbuildCmdExeCommandLine(npmCmdPath, params.npmArgs)
\t\t\t],
\t\t\twindowsVerbatimArguments: true
\t\t};
\t\tthrow new Error("Unable to resolve a safe npm executable on Windows");`;

  const newNpmFallback = `\t\tif (existsSync(npmExePath)) return {
\t\t\tcommand: npmExePath,
\t\t\targs: params.npmArgs
\t\t};
\t\tconst npmCmdPath = pathImpl.resolve(nodeDir, "npm.cmd");
\t\tif (existsSync(npmCmdPath)) return {
\t\t\tcommand: env.ComSpec ?? "cmd.exe",
\t\t\targs: [
\t\t\t\t"/d",
\t\t\t\t"/s",
\t\t\t\t"/c",
\t\t\t\tbuildCmdExeCommandLine(npmCmdPath, params.npmArgs)
\t\t\t],
\t\t\twindowsVerbatimArguments: true
\t\t};
\t\tconst pathNpmExecutable = resolveWindowsNpmExecutableFromPath(env, pathImpl, existsSync);
\t\tif (pathNpmExecutable?.toLowerCase().endsWith(".cmd")) return {
\t\t\tcommand: env.ComSpec ?? "cmd.exe",
\t\t\targs: [
\t\t\t\t"/d",
\t\t\t\t"/s",
\t\t\t\t"/c",
\t\t\t\tbuildCmdExeCommandLine(pathNpmExecutable, params.npmArgs)
\t\t\t],
\t\t\twindowsVerbatimArguments: true
\t\t};
\t\tif (pathNpmExecutable) return {
\t\t\tcommand: pathNpmExecutable,
\t\t\targs: params.npmArgs
\t\t};
\t\tthrow new Error("Unable to resolve a safe npm executable on Windows");`;

  contents = replaceOneOfRequired(
    contents,
    [originalNpmFallback, oldNpmFallback],
    newNpmFallback,
    'Windows npm PATH fallback',
  );

  contents = replaceRequired(
    contents,
    `\t\t\t],
\t\t\twindowsHide: true
\t\t});`,
    `\t\t\t],
\t\t\twindowsVerbatimArguments: params.windowsVerbatimArguments === true,
\t\t\twindowsHide: true
\t\t});`,
    'async npm spawn windowsVerbatimArguments option',
  );

  contents = replaceRequired(
    contents,
    `\t\t\tstdio: "pipe",
\t\t\twindowsHide: true
\t\t});`,
    `\t\t\tstdio: "pipe",
\t\t\twindowsVerbatimArguments: npmRunner.windowsVerbatimArguments === true,
\t\t\twindowsHide: true
\t\t});`,
    'sync npm spawn windowsVerbatimArguments option',
  );

  contents = replaceRequired(
    contents,
    `\t\t\tcwd: installExecutionRoot,
\t\t\tenv: npmRunner.env ?? installEnv,
\t\t\tonProgress: params.onProgress
\t\t});`,
    `\t\t\tcwd: installExecutionRoot,
\t\t\tenv: npmRunner.env ?? installEnv,
\t\t\twindowsVerbatimArguments: npmRunner.windowsVerbatimArguments === true,
\t\t\tonProgress: params.onProgress
\t\t});`,
    'async npm runner windowsVerbatimArguments forwarding',
  );

  fs.writeFileSync(runtimeRootFile, contents, 'utf8');
  return true;
}

function patchDefaultRoots() {
  const roots = [
    path.join(ROOT, 'node_modules', 'openclaw'),
    path.join(ROOT, 'build', 'openclaw'),
  ];

  let patchedCount = 0;
  for (const openclawRoot of roots) {
    if (!fs.existsSync(openclawRoot)) continue;
    if (patchOpenClawRuntimeRoot(openclawRoot)) {
      patchedCount += 1;
      console.log(`Patched OpenClaw runtime npm resolver: ${openclawRoot}`);
    }
  }

  if (patchedCount === 0) {
    console.warn('OpenClaw runtime patch skipped: no OpenClaw runtime roots found');
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  patchDefaultRoots();
}
