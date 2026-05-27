import type { InstallChoice, RuntimeKind, RuntimeMode } from './types';

export const HERMESCLAW_BOTH_MODE = 'hermesclaw-both' satisfies RuntimeMode;
export const LEGACY_HERMES_BOTH_MODE = 'openclaw-with-hermes-agent' satisfies RuntimeMode;

export function isHermesClawBothMode(mode: RuntimeMode): boolean {
  return mode === HERMESCLAW_BOTH_MODE || mode === LEGACY_HERMES_BOTH_MODE;
}

export function hostRuntimeKindFromMode(mode: RuntimeMode): RuntimeKind {
  return mode === 'hermes' ? 'hermes' : 'openclaw';
}

export function runtimeModeFromInstallChoice(choice: InstallChoice): RuntimeMode {
  switch (choice) {
    case 'hermes':
      return 'hermes';
    case 'both':
      return HERMESCLAW_BOTH_MODE;
    case 'openclaw':
    default:
      return 'openclaw';
  }
}

export function installedKindsFromChoice(choice: InstallChoice): RuntimeKind[] {
  switch (choice) {
    case 'hermes':
      return ['hermes'];
    case 'both':
      return ['openclaw', 'hermes'];
    case 'openclaw':
    default:
      return ['openclaw'];
  }
}

export function normalizeInstalledKinds(kinds: RuntimeKind[] | undefined, mode: RuntimeMode): RuntimeKind[] {
  if (Array.isArray(kinds) && kinds.length > 0) {
    return Array.from(new Set(kinds));
  }

  if (mode === 'hermes') {
    return ['hermes'];
  }

  if (isHermesClawBothMode(mode)) {
    return ['openclaw', 'hermes'];
  }

  return ['openclaw'];
}

export function installChoiceFromMode(mode: RuntimeMode): InstallChoice {
  switch (mode) {
    case 'hermes':
      return 'hermes';
    case HERMESCLAW_BOTH_MODE:
    case LEGACY_HERMES_BOTH_MODE:
      return 'both';
    case 'openclaw':
    default:
      return 'openclaw';
  }
}
