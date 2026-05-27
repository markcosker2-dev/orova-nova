/**
 * Device OAuth Manager
 *
 * Manages Device Code OAuth flows for MiniMax providers.
 *
 * The OAuth protocol implementations are fully self-contained in:
 *   - ./minimax-oauth.ts  (MiniMax Device Code + PKCE)
 *
 * This approach:
 * - Hardcodes client_id and endpoints (same as openai-codex-oauth.ts)
 * - Implements OAuth flows locally with zero openclaw dependency
 * - Survives openclaw package upgrades without breakage
 * - Works identically on macOS, Windows, and Linux
 *
 * We provide our own callbacks (openUrl/note/progress) that hook into
 * the Electron IPC system to display UI in the HermesClaw frontend.
 */
import { EventEmitter } from 'events';
import { BrowserWindow, shell } from 'electron';
import { logger } from './logger';
import { saveProvider, getProvider, ProviderConfig } from './secure-storage';
import { listProviderAccounts } from '../services/providers/provider-store';
import { getProviderDefaultModel } from './provider-registry';
import { proxyAwareFetch } from './proxy-fetch';
import { saveOAuthTokenToOpenClaw, saveCopilotGitHubTokenToOpenClaw, setCopilotPluginConfigToOpenClaw, setOpenClawDefaultModelWithOverride } from './openclaw-auth';
import { loginMiniMaxPortalOAuth, type MiniMaxOAuthToken, type MiniMaxRegion } from './minimax-oauth';
import { loginGitHubCopilot, type CopilotOAuthToken } from './copilot-oauth';

export type OAuthProviderType = 'minimax-portal' | 'minimax-portal-cn' | 'copilot';

// Re-export types for consumers
export type { MiniMaxRegion, MiniMaxOAuthToken, CopilotOAuthToken };

// ─────────────────────────────────────────────────────────────
// DeviceOAuthManager
// ─────────────────────────────────────────────────────────────

class DeviceOAuthManager extends EventEmitter {
    private activeProvider: OAuthProviderType | null = null;
    private activeAccountId: string | null = null;
    private activeLabel: string | null = null;
    private active: boolean = false;
    private mainWindow: BrowserWindow | null = null;

    private async runWithProxyAwareFetch<T>(task: () => Promise<T>): Promise<T> {
        const originalFetch = globalThis.fetch;
        globalThis.fetch = ((input: string | URL, init?: RequestInit) =>
            proxyAwareFetch(input, init)) as typeof fetch;
        try {
            return await task();
        } finally {
            globalThis.fetch = originalFetch;
        }
    }

    setWindow(window: BrowserWindow) {
        this.mainWindow = window;
    }

    async startFlow(
        provider: OAuthProviderType,
        region: MiniMaxRegion = 'global',
        options?: { accountId?: string; label?: string },
    ): Promise<boolean> {
        if (this.active) {
            await this.stopFlow();
        }

        this.active = true;
        this.emit('oauth:start', { provider, accountId: options?.accountId || provider });
        this.activeProvider = provider;
        this.activeAccountId = options?.accountId || provider;
        this.activeLabel = options?.label || null;

        try {
            if (provider === 'minimax-portal' || provider === 'minimax-portal-cn') {
                const actualRegion = provider === 'minimax-portal-cn' ? 'cn' : (region || 'global');
                await this.runMiniMaxFlow(actualRegion, provider);
            } else if (provider === 'copilot') {
                await this.runCopilotFlow();
            } else {
                throw new Error(`Unsupported OAuth provider type: ${provider}`);
            }
            return true;
        } catch (error) {
            if (!this.active) {
                // Flow was cancelled — not an error
                return false;
            }
            logger.error(`[DeviceOAuth] Flow error for ${provider}:`, error);
            this.emitError(error instanceof Error ? error.message : String(error));
            this.active = false;
            this.activeProvider = null;
            this.activeAccountId = null;
            this.activeLabel = null;
            return false;
        }
    }

    async stopFlow(): Promise<void> {
        this.active = false;
        this.activeProvider = null;
        this.activeAccountId = null;
        this.activeLabel = null;
        logger.info('[DeviceOAuth] Flow explicitly stopped');
    }

    // ─────────────────────────────────────────────────────────
    // MiniMax flow
    // ─────────────────────────────────────────────────────────

    private async runMiniMaxFlow(region?: MiniMaxRegion, providerType: OAuthProviderType = 'minimax-portal'): Promise<void> {
        const provider = this.activeProvider!;

        const token: MiniMaxOAuthToken = await this.runWithProxyAwareFetch(() => loginMiniMaxPortalOAuth({
            region,
            openUrl: async (url: string) => {
                logger.info(`[DeviceOAuth] MiniMax opening browser: ${url}`);
                // Open the authorization URL in the system browser
                shell.openExternal(url).catch((err: unknown) =>
                    logger.warn(`[DeviceOAuth] Failed to open browser:`, err)
                );
            },
            note: async (message: string, _title?: string) => {
                if (!this.active) return;
                // The extension calls note() with a message containing
                // the user_code and verification_uri — parse them for the UI
                const { verificationUri, userCode } = this.parseNote(message);
                if (verificationUri && userCode) {
                    this.emitCode({ provider, verificationUri, userCode, expiresIn: 300 });
                } else {
                    logger.info(`[DeviceOAuth] MiniMax note: ${message}`);
                }
            },
            progress: {
                update: (msg: string) => logger.info(`[DeviceOAuth] MiniMax progress: ${msg}`),
                stop: (msg?: string) => logger.info(`[DeviceOAuth] MiniMax progress done: ${msg ?? ''}`),
            },
        }));

        if (!this.active) return;

        await this.onSuccess(providerType, {
            access: token.access,
            refresh: token.refresh,
            expires: token.expires,
            // MiniMax returns a per-account resourceUrl as the API base URL
            resourceUrl: token.resourceUrl,
            // Revert back to anthropic-messages
            api: 'anthropic-messages',
            region,
        });
    }


    // ─────────────────────────────────────────────────────────
    // GitHub Copilot flow
    // ─────────────────────────────────────────────────────────

    private async runCopilotFlow(): Promise<void> {
        const provider = this.activeProvider!;

        const token: CopilotOAuthToken = await this.runWithProxyAwareFetch(() => loginGitHubCopilot({
            openUrl: async (url: string) => {
                logger.info(`[DeviceOAuth] Copilot opening browser: ${url}`);
                shell.openExternal(url).catch((err: unknown) =>
                    logger.warn(`[DeviceOAuth] Failed to open browser:`, err)
                );
            },
            note: async (message: string, _title?: string) => {
                if (!this.active) return;
                const { verificationUri, userCode } = this.parseNote(message);
                if (verificationUri && userCode) {
                    this.emitCode({ provider, verificationUri, userCode, expiresIn: 900 });
                } else {
                    logger.info(`[DeviceOAuth] Copilot note: ${message}`);
                }
            },
            progress: {
                update: (msg: string) => logger.info(`[DeviceOAuth] Copilot progress: ${msg}`),
                stop: (msg?: string) => logger.info(`[DeviceOAuth] Copilot progress done: ${msg ?? ''}`),
            },
        }));

        if (!this.active) return;

        await this.onSuccess('copilot', {
            access: token.accessToken,
            refresh: '',
            expires: Date.now() + 8 * 60 * 60 * 1000, // ~8 hours
            api: 'openai-completions',
        });
    }



    // ─────────────────────────────────────────────────────────
    // Success handler
    // ─────────────────────────────────────────────────────────

    private async onSuccess(providerType: OAuthProviderType, token: {
        access: string;
        refresh: string;
        expires: number;
        resourceUrl?: string;
        api: 'anthropic-messages' | 'openai-completions';
        region?: MiniMaxRegion;
    }) {
        const accountId = this.activeAccountId || providerType;
        const accountLabel = this.activeLabel;
        this.active = false;
        this.activeProvider = null;
        this.activeAccountId = null;
        this.activeLabel = null;
        logger.info(`[DeviceOAuth] Successfully completed OAuth for ${providerType}`);

        // 1. Write OAuth token to OpenClaw's auth-profiles.json in native OAuth format.
        //    (matches what `openclaw models auth login` → upsertAuthProfile writes).
        //    We save both MiniMax providers to the generic "minimax-portal" profile
        //    so OpenClaw's gateway auto-refresher knows how to find it.
        try {
            if (providerType === 'copilot') {
                // The Copilot plugin reads type:'token' profiles with provider:'github-copilot'.
                // Write the raw gho_* token so the plugin can exchange it for a Copilot tid= token.
                await saveCopilotGitHubTokenToOpenClaw(token.access);
            } else {
                const tokenProviderId = providerType.startsWith('minimax-portal') ? 'minimax-portal' : providerType;
                await saveOAuthTokenToOpenClaw(tokenProviderId, {
                    access: token.access,
                    refresh: token.refresh,
                    expires: token.expires,
                });
            }
        } catch (err) {
            logger.warn(`[DeviceOAuth] Failed to save OAuth token to OpenClaw:`, err);
        }

        // 2. Write openclaw.json: set default model + provider config (baseUrl/api/models)
        //    This mirrors what the OpenClaw plugin's configPatch does after CLI login.
        //    The baseUrl comes from token.resourceUrl (per-account URL from the OAuth server)
        //    or falls back to the provider's default public endpoint.
        let baseUrl: string;
        if (providerType === 'copilot') {
            baseUrl = 'https://api.githubcopilot.com';
        } else {
            const defaultBaseUrl = providerType === 'minimax-portal'
                ? 'https://api.minimax.io/anthropic'
                : 'https://api.minimaxi.com/anthropic';

            baseUrl = token.resourceUrl || defaultBaseUrl;

            // Ensure baseUrl has a protocol prefix
            if (baseUrl && !baseUrl.startsWith('http://') && !baseUrl.startsWith('https://')) {
                baseUrl = 'https://' + baseUrl;
            }

            // Ensure the base URL ends with /anthropic
            if (providerType.startsWith('minimax-portal') && baseUrl) {
                baseUrl = baseUrl.replace(/\/v1$/, '').replace(/\/anthropic$/, '').replace(/\/$/, '') + '/anthropic';
            }
        }

        // 2. Write openclaw.json config
        try {
            if (providerType === 'copilot') {
                // For Copilot we use the plugin-based path: do NOT write models.providers.copilot
                // (that would bypass the plugin's prepareRuntimeAuth token-exchange logic).
                // Instead just set the default model with github-copilot/ prefix and ensure
                // the plugin is allowed. The plugin reads auth-profiles.json on its own.
                await setCopilotPluginConfigToOpenClaw('github-copilot/gpt-4o');
            } else {
                const tokenProviderId = providerType.startsWith('minimax-portal') ? 'minimax-portal' : providerType;
                const apiKeyEnv = 'minimax-oauth';
                await setOpenClawDefaultModelWithOverride(tokenProviderId, undefined, {
                    baseUrl,
                    api: token.api,
                    authHeader: providerType.startsWith('minimax-portal') ? true : undefined,
                    apiKeyEnv,
                });
            }
        } catch (err) {
            logger.warn(`[DeviceOAuth] Failed to configure openclaw models:`, err);
        }

        // 3. Save provider record in HermesClaw's own store so UI shows it as configured
        // For copilot (single-account OAuth), find any existing account with vendorId='copilot'
        // and reuse its id to avoid creating duplicates on every re-authorization.
        let resolvedAccountId = accountId;
        if (providerType === 'copilot') {
            try {
                const allAccounts = await listProviderAccounts();
                const existingCopilot = allAccounts.find(a => a.vendorId === 'copilot');
                if (existingCopilot) {
                    resolvedAccountId = existingCopilot.id;
                }
            } catch (err) {
                logger.warn('[DeviceOAuth] Failed to look up existing copilot accounts:', err);
            }
        }
        const existing = await getProvider(resolvedAccountId);
        const nameMap: Record<OAuthProviderType, string> = {
            'minimax-portal': 'MiniMax (Global)',
            'minimax-portal-cn': 'MiniMax (CN)',
            'copilot': 'GitHub Copilot',
        };
        const providerConfig: ProviderConfig = {
            id: resolvedAccountId,
            name: accountLabel || nameMap[providerType as OAuthProviderType] || providerType,
            type: providerType,
            enabled: existing?.enabled ?? true,
            baseUrl, // Save the dynamically resolved URL (Global vs CN)

            model: getProviderDefaultModel(providerType) || existing?.model,
            createdAt: existing?.createdAt || new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        };
        await saveProvider(providerConfig);

        // 4. Emit success internally so the main process can restart the Gateway
        this.emit('oauth:success', { provider: providerType, accountId: resolvedAccountId });

        // 5. Emit success to frontend
        if (this.mainWindow && !this.mainWindow.isDestroyed()) {
            this.mainWindow.webContents.send('oauth:success', { provider: providerType, accountId: resolvedAccountId, success: true });
        }
    }


    // ─────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────

    /**
     * Parse user_code and verification_uri from the note message sent by
     * the OpenClaw extension's loginXxxPortalOAuth function.
     *
     * Note format (minimax-portal-auth/oauth.ts):
     *   "Open https://platform.minimax.io/oauth-authorize?user_code=dyMj_wOhpK&client=... to approve access.\n"
     *   "If prompted, enter the code dyMj_wOhpK.\n"
     *   ...
     *
     * user_code format: mixed-case alphanumeric with underscore, e.g. "dyMj_wOhpK"
     */
    private parseNote(message: string): { verificationUri?: string; userCode?: string } {
        // Primary: extract URL (everything between "Open " and " to")
        const urlMatch = message.match(/Open\s+(https?:\/\/\S+?)\s+to/i);
        const verificationUri = urlMatch?.[1];

        let userCode: string | undefined;

        // Method 1: extract user_code from URL query param (most reliable)
        if (verificationUri) {
            try {
                const parsed = new URL(verificationUri);
                const qp = parsed.searchParams.get('user_code');
                if (qp) userCode = qp;
            } catch {
                // fall through to text-based extraction
            }
        }

        // Method 2: text-based extraction — matches mixed-case alnum + underscore/hyphen codes
        if (!userCode) {
            const codeMatch = message.match(/enter.*?code\s+([A-Za-z0-9][A-Za-z0-9_-]{3,})/i);
            if (codeMatch?.[1]) userCode = codeMatch[1].replace(/\.$/, ''); // strip trailing period
        }

        return { verificationUri, userCode };
    }

    private emitCode(data: {
        provider: string;
        verificationUri: string;
        userCode: string;
        expiresIn: number;
    }) {
        this.emit('oauth:code', data);
        if (this.mainWindow && !this.mainWindow.isDestroyed()) {
            this.mainWindow.webContents.send('oauth:code', data);
        }
    }

    private emitError(message: string) {
        this.emit('oauth:error', { message });
        if (this.mainWindow && !this.mainWindow.isDestroyed()) {
            this.mainWindow.webContents.send('oauth:error', { message });
        }
    }
}

export const deviceOAuthManager = new DeviceOAuthManager();
