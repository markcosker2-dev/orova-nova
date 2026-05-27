import { existsSync, readFileSync, readdirSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';

import { getOpenClawConfigDir } from '../utils/paths';
import { logger } from '../utils/logger';

const PI_AI_PACKAGE_JSON = join('node_modules', '@mariozechner', 'pi-ai', 'package.json');
const PI_AI_OAUTH_EXPORT = './oauth';

type JsonObject = Record<string, unknown>;

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function patchPiAiPackageJson(pkgJsonPath: string): boolean {
  if (!existsSync(pkgJsonPath)) return false;

  const raw = readFileSync(pkgJsonPath, 'utf-8');
  const pkg = JSON.parse(raw) as unknown;
  if (!isJsonObject(pkg)) return false;

  const exportsField = pkg.exports;
  if (!isJsonObject(exportsField)) return false;

  const oauthExport = exportsField[PI_AI_OAUTH_EXPORT];
  if (!isJsonObject(oauthExport)) return false;

  const importTarget = oauthExport.import;
  if (typeof importTarget !== 'string' || importTarget.length === 0) return false;

  const oauthFile = join(dirname(pkgJsonPath), importTarget);
  if (!existsSync(oauthFile)) {
    logger.warn(`[runtime-deps] Skipped pi-ai oauth export repair; target missing: ${oauthFile}`);
    return false;
  }

  if (oauthExport.require === importTarget && oauthExport.default === importTarget) {
    return false;
  }

  const nextPkg: JsonObject = {
    ...pkg,
    exports: {
      ...exportsField,
      [PI_AI_OAUTH_EXPORT]: {
        ...oauthExport,
        require: importTarget,
        default: importTarget,
      },
    },
  };

  writeFileSync(pkgJsonPath, `${JSON.stringify(nextPkg, null, 2)}\n`, 'utf-8');
  return true;
}

function collectPiAiPackageJsonCandidates(openclawDir: string): string[] {
  const candidates = new Set<string>();
  candidates.add(join(openclawDir, PI_AI_PACKAGE_JSON));

  const runtimeDepsDir = join(getOpenClawConfigDir(), 'plugin-runtime-deps');
  if (!existsSync(runtimeDepsDir)) return [...candidates];

  try {
    for (const entry of readdirSync(runtimeDepsDir, { withFileTypes: true })) {
      if (!entry.isDirectory() || !entry.name.startsWith('openclaw-')) continue;
      candidates.add(join(runtimeDepsDir, entry.name, PI_AI_PACKAGE_JSON));
    }
  } catch (err) {
    logger.warn('[runtime-deps] Failed to scan OpenClaw runtime deps cache:', err);
  }

  return [...candidates];
}

export function repairPiAiOauthExportForGateway(openclawDir: string): void {
  let patchedCount = 0;

  for (const pkgJsonPath of collectPiAiPackageJsonCandidates(openclawDir)) {
    try {
      if (patchPiAiPackageJson(pkgJsonPath)) {
        patchedCount++;
        logger.info(`[runtime-deps] Repaired pi-ai oauth export: ${pkgJsonPath}`);
      }
    } catch (err) {
      logger.warn(`[runtime-deps] Failed to repair pi-ai oauth export at ${pkgJsonPath}:`, err);
    }
  }

  if (patchedCount > 0) {
    logger.info(`[runtime-deps] Repaired ${patchedCount} pi-ai oauth export package.json file(s)`);
  }
}
