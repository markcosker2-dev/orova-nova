/**
 * Config File Watcher
 * Monitors ~/.openclaw/openclaw.json for changes and emits events
 */
import { EventEmitter } from 'events';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { logger } from '../utils/logger';

export interface ConfigFileWatcherEvents {
  'config-changed': (filePath: string) => void;
  'watch-error': (error: Error) => void;
}

/**
 * Watches the OpenClaw config file for changes
 * Uses fs.watch with debouncing to handle multiple rapid events
 */
export class ConfigFileWatcher extends EventEmitter {
  private configPath: string;
  private watcher: fs.FSWatcher | null = null;
  private debounceTimer: NodeJS.Timeout | null = null;
  private readonly debounceMs = 500; // Debounce rapid file change events
  private lastChangeTime = 0;
  private readonly minChangeIntervalMs = 1000; // Minimum interval between emitted events

  constructor() {
    super();
    this.configPath = path.join(os.homedir(), '.openclaw', 'openclaw.json');
  }

  /**
   * Start watching the config file
   */
  start(): void {
    if (this.watcher) {
      logger.debug('Config file watcher already started');
      return;
    }

    try {
      // Verify config file exists before watching
      if (!fs.existsSync(this.configPath)) {
        logger.warn(`Config file not found at ${this.configPath}, watcher will not start`);
        return;
      }

      this.watcher = fs.watch(this.configPath, (eventType) => {
        if (eventType === 'change') {
          this.handleConfigChange();
        }
      });

      this.watcher.on('error', (error) => {
        logger.error('Config file watcher error:', error);
        this.emit('watch-error', error);
      });

      logger.info(`Config file watcher started for ${this.configPath}`);
    } catch (error) {
      logger.error('Failed to start config file watcher:', error);
      this.emit('watch-error', error instanceof Error ? error : new Error(String(error)));
    }
  }

  /**
   * Stop watching the config file
   */
  stop(): void {
    if (this.watcher) {
      this.watcher.close();
      this.watcher = null;
      logger.debug('Config file watcher stopped');
    }

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }
  }

  /**
   * Handle config file change with debouncing
   */
  private handleConfigChange(): void {
    // Clear existing debounce timer
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    // Debounce rapid changes
    this.debounceTimer = setTimeout(() => {
      const now = Date.now();
      const timeSinceLastChange = now - this.lastChangeTime;

      // Only emit if minimum interval has passed
      if (timeSinceLastChange >= this.minChangeIntervalMs) {
        this.lastChangeTime = now;
        logger.debug(`Config file changed: ${this.configPath}`);
        this.emit('config-changed', this.configPath);
      }

      this.debounceTimer = null;
    }, this.debounceMs);
  }

  /**
   * Get the config file path being watched
   */
  getConfigPath(): string {
    return this.configPath;
  }

  /**
   * Check if watcher is active
   */
  isActive(): boolean {
    return this.watcher !== null;
  }
}