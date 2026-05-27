import { app } from 'electron';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
 
 // Lazy-load electron-store (ESM module) from the main process only.
 // eslint-disable-next-line @typescript-eslint/no-explicit-any
 let providerStore: any = null;
 
 /** Strip UTF-8 BOM from hermesclaw-providers.json if present (can be introduced by manual edits on Windows). */
 function sanitizeProviderStoreFile() {
   try {
     const filePath = join((app?.getPath?.('userData') ?? process.cwd()), 'hermesclaw-providers.json');
    if (!existsSync(filePath)) return;
    const raw = readFileSync(filePath);
    // UTF-8 BOM: EF BB BF
    if (raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf) {
      writeFileSync(filePath, raw.slice(3));
    }
  } catch {
    // Non-fatal — let electron-store handle any subsequent parse errors.
  }
}

export async function getHermesClawProviderStore() {
  if (!providerStore) {
    sanitizeProviderStoreFile();
    const Store = (await import('electron-store')).default;
    providerStore = new Store({
      name: 'hermesclaw-providers',
      defaults: {
        schemaVersion: 0,
        providers: {} as Record<string, unknown>,
        providerAccounts: {} as Record<string, unknown>,
        apiKeys: {} as Record<string, string>,
        providerSecrets: {} as Record<string, unknown>,
        defaultProvider: null as string | null,
        defaultProviderAccountId: null as string | null,
      },
    });
  }

  return providerStore;
}
