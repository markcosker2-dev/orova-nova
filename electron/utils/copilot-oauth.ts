/**
 * Self-contained GitHub Copilot Device Code OAuth flow.
 *
 * Implements RFC 8628 (Device Authorization Grant) for GitHub Copilot.
 * Uses the official Copilot client ID (Iv1.b507a08c87ecfe98).
 *
 * Protocol:
 *   1. POST https://github.com/login/device/code  → get user_code, device_code, verification_uri
 *   2. Open verification_uri in browser
 *   3. Poll POST https://github.com/login/oauth/access_token with device_code until approved
 *   4. Return { accessToken: 'gho_...' }
 */
import { proxyAwareFetch } from './proxy-fetch';

// ── Constants ────────────────────────────────────────────────

const GITHUB_COPILOT_CLIENT_ID = 'Iv1.b507a08c87ecfe98';
const GITHUB_DEVICE_CODE_URL = 'https://github.com/login/device/code';
const GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token';
const GITHUB_OAUTH_SCOPE = 'read:user';

// ── Types ────────────────────────────────────────────────────

export interface CopilotOAuthToken {
  accessToken: string; // gho_* OAuth token
}

interface DeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number; // seconds
  interval: number; // polling interval in seconds
}

type TokenResult =
  | { status: 'success'; accessToken: string }
  | { status: 'pending' }
  | { status: 'slow_down' }
  | { status: 'error'; message: string };

export interface CopilotOAuthOptions {
  openUrl: (url: string) => Promise<void>;
  note: (message: string, title?: string) => Promise<void>;
  progress: { update: (message: string) => void; stop: (message?: string) => void };
}

// ── OAuth flow steps ─────────────────────────────────────────

async function requestDeviceCode(): Promise<DeviceCodeResponse> {
  const response = await proxyAwareFetch(GITHUB_DEVICE_CODE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      client_id: GITHUB_COPILOT_CLIENT_ID,
      scope: GITHUB_OAUTH_SCOPE,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub device code request failed: ${text || response.statusText}`);
  }

  const payload = (await response.json()) as DeviceCodeResponse & {
    error?: string;
    error_description?: string;
  };
  if (payload.error) {
    throw new Error(
      `GitHub device code error: ${payload.error_description || payload.error}`,
    );
  }
  if (!payload.device_code || !payload.user_code || !payload.verification_uri) {
    throw new Error('GitHub device code response missing required fields.');
  }
  return payload;
}

async function pollAccessToken(deviceCode: string): Promise<TokenResult> {
  const response = await proxyAwareFetch(GITHUB_TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      client_id: GITHUB_COPILOT_CLIENT_ID,
      device_code: deviceCode,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    }),
  });

  const text = await response.text();
  let payload: Record<string, unknown> | undefined;
  if (text) {
    try {
      payload = JSON.parse(text) as Record<string, unknown>;
    } catch {
      payload = undefined;
    }
  }

  if (!payload) {
    return { status: 'error', message: 'GitHub OAuth failed to parse response.' };
  }

  const error = payload.error as string | undefined;
  if (error === 'authorization_pending') {
    return { status: 'pending' };
  }
  if (error === 'slow_down') {
    return { status: 'slow_down' };
  }
  if (error === 'expired_token') {
    return {
      status: 'error',
      message: 'Device code expired. Please restart the authorization flow.',
    };
  }
  if (error === 'access_denied') {
    return { status: 'error', message: 'Authorization was denied by the user.' };
  }
  if (error) {
    return { status: 'error', message: (payload.error_description as string) || error };
  }

  const accessToken = payload.access_token as string | undefined;
  if (!accessToken) {
    return { status: 'error', message: 'GitHub OAuth response missing access_token.' };
  }

  return { status: 'success', accessToken };
}

// ── Public API ───────────────────────────────────────────────

export async function loginGitHubCopilot(
  params: CopilotOAuthOptions,
): Promise<CopilotOAuthToken> {
  const deviceCode = await requestDeviceCode();

  const noteLines = [
    `Open ${deviceCode.verification_uri} to approve access.`,
    `If prompted, enter the code ${deviceCode.user_code}.`,
    `Expires in: ${deviceCode.expires_in} seconds`,
  ];
  await params.note(noteLines.join('\n'), 'GitHub Copilot OAuth');

  try {
    await params.openUrl(deviceCode.verification_uri);
  } catch {
    // Fall back to manual copy/paste if browser open fails.
  }

  let pollIntervalMs = (deviceCode.interval || 5) * 1000;
  const expiresAt = Date.now() + deviceCode.expires_in * 1000;

  while (Date.now() < expiresAt) {
    params.progress.update('Waiting for GitHub authorization…');
    const result = await pollAccessToken(deviceCode.device_code);

    if (result.status === 'success') {
      return { accessToken: result.accessToken };
    }

    if (result.status === 'error') {
      throw new Error(result.message);
    }

    if (result.status === 'slow_down') {
      pollIntervalMs += 5000;
    }

    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error('GitHub OAuth timed out before authorization completed.');
}
