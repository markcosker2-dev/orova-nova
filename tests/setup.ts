/**
 * Vitest global setup.
 * Referenced by vitest.config.ts (setupFiles). Keep side effects minimal —
 * unit tests must not require a running Electron process.
 */
import '@testing-library/jest-dom';
