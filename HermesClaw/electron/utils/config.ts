/**
 * Application Configuration
 * Centralized configuration constants and helpers
 */

/**
 * Port configuration
 */
export const PORTS = {
  /** HermesClaw GUI development server port */
  HERMESCLAW_DEV: 5173,

  /** HermesClaw GUI production port (for reference) */
  HERMESCLAW_GUI: 23333,

  /** Local host API server port */
  HERMESCLAW_HOST_API: 13210,

  /** OpenClaw Gateway port */
  OPENCLAW_GATEWAY: 18789,

  /** OROVA backend port */
  OROVA_BACKEND: 18790,
} as const;

/**
 * Get port from environment or default
 */
export function getPort(key: keyof typeof PORTS): number {
  const envKey = `HERMESCLAW_PORT_${key}`;
  const envValue = process.env[envKey];
  return envValue ? parseInt(envValue, 10) : PORTS[key];
}