import { getPort } from './config';

const SETTINGS: Record<string, unknown> = {
  orovaBackendUrl: 'http://127.0.0.1:18790',
  orovaApiKey: 'nova_admin_2026',
};

export async function getSetting<K extends keyof typeof SETTINGS>(key: K): Promise<typeof SETTINGS[K]> {
  return SETTINGS[key];
}

export async function setSetting<K extends keyof typeof SETTINGS>(
  _key: K,
  _value: typeof SETTINGS[K]
): Promise<void> {
  // Stub for HermesClaw integration
}

export async function getAllSettings(): Promise<{ orovaBackendUrl: string; orovaApiKey: string }> {
  return SETTINGS as { orovaBackendUrl: string; orovaApiKey: string };
}