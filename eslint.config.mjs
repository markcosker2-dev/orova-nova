// ESLint 10 flat config (required since ESLint v9 — no .eslintrc support).
// Scope: the HermesClaw TS/JS surface (electron/, src/, shared/, tests/,
// scripts/, root configs). The Python app, vault, and legacy/mirror
// directories are ignored.
import js from '@eslint/js';
import tseslint from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';

// react-hooks recommended rules, downgraded to warnings: the codebase
// predates this config, so hook findings surface without failing CI.
const reactHooksWarnRules = Object.fromEntries(
  Object.keys(reactHooks.configs['recommended-latest'].rules).map((rule) => [
    rule,
    'warn',
  ]),
);

export default [
  {
    ignores: [
      // Dependencies and build outputs
      'node_modules/**',
      'dist/**',
      'dist-electron/**',
      'build/**',
      'out/**',
      'release/**',
      'coverage/**',
      'artifacts/**',
      'playwright-report/**',
      'test-results/**',
      '.venv/**',
      '**/*.min.js',
      // Non-TS parts of the repo: Python backend, Obsidian vault,
      // reference mirrors, legacy dashboard assets
      'app/**',
      'vault/**',
      'HermesClaw/**',
      'mission-control/**',
      'openclaw_instance/**',
      'js/**',
      'css/**',
      'test_auth.js',
      // Generated files (scripts/generate-ext-bridge.mjs)
      'electron/extensions/_ext-bridge.generated.ts',
      'src/extensions/_ext-bridge.generated.ts',
    ],
  },
  {
    linterOptions: {
      // Existing sources carry directives for rules this config keeps at
      // warn level; don't strip them via --fix.
      reportUnusedDisableDirectives: 'off',
    },
  },

  // Core recommended rules for every linted file (the typescript-eslint
  // preset below disables the ones its own rules replace).
  js.configs.recommended,

  // Plain JS (root configs, build scripts) runs under Node
  {
    files: ['**/*.{js,mjs,cjs}'],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.node },
    },
  },
  // zx scripts run with injected globals ($, fs, path, argv, ...)
  {
    files: ['scripts/**/*.mjs'],
    rules: {
      'no-undef': 'off',
    },
  },
  // Pre-existing dead assignments in build scripts; not auto-fixable
  {
    rules: {
      'no-useless-assignment': 'warn',
    },
  },

  // TypeScript (electron main/preload, React renderer, shared, tests)
  ...tseslint.configs['flat/recommended'].map((cfg) => ({
    ...cfg,
    files: ['**/*.{ts,tsx}'],
  })),
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      ...reactHooksWarnRules,
      'react-refresh/only-export-components': 'warn',
      // Pragmatic downgrades — surface as warnings, don't fail CI.
      // Tighten these once the codebase is cleaned up.
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      // Electron main-process code uses require() for CJS interop
      '@typescript-eslint/no-require-imports': 'warn',
    },
  },
];
