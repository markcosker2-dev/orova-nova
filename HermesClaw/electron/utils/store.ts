import { getPort } from './config';

interface StoreEntry {
  key: string;
  value: unknown;
  updatedAt: string;
}

const STORE_FILE = 'hermesclaw-settings.json';
const SETTINGS: Record<string, unknown> = {
  orovaBackendUrl: 'http://127.0.0.1:18790',
  orovaApiKey: '',  // Must be configured by user — no hardcoded default
};

function getStorePath(): string {
  const { app } = require('electron');
  const path = require('path');
  return path.join(app.getPath('userData'), STORE_FILE);
}

function loadPersistedSettings(): void {
  try {
    const fs = require('fs');
    const storePath = getStorePath();
    if (fs.existsSync(storePath)) {
      const raw = fs.readFileSync(storePath, 'utf-8');
      const entries: StoreEntry[] = JSON.parse(raw);
      for (const entry of entries) {
        if (entry.key in SETTINGS) {
          SETTINGS[entry.key as keyof typeof SETTINGS] = entry.value;
        }
      }
    }
  } catch (e) {
    // Silently fail — use defaults
  }
}

function persistSettings(): void {
  try {
    const fs = require('fs');
    const storePath = getStorePath();
    const entries: StoreEntry[] = Object.entries(SETTINGS).map(([key, value]) => ({
      key,
      value,
      updatedAt: new Date().toISOString(),
    }));
    fs.writeFileSync(storePath, JSON.stringify(entries, null, 2), 'utf-8');
  } catch (e) {
    // Silently fail — in-memory state still works
  }
}

// Load on module init
loadPersistedSettings();

export async function getSetting<K extends keyof typeof SETTINGS>(key: K): Promise<typeof SETTINGS[K]> {
  return SETTINGS[key];
}

export async function setSetting<K extends keyof typeof SETTINGS>(
  key: K,
  value: typeof SETTINGS[K]
): Promise<void> {
  SETTINGS[key] = value;
  persistSettings();
}

export async function getAllSettings(): Promise<{ orovaBackendUrl: string; orovaApiKey: string }> {
  return SETTINGS as { orovaBackendUrl: string; orovaApiKey: string };
}
