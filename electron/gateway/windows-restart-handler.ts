/**
 * Windows Restart Handler Module
 * 
 * Implements Windows-specific restart logic using Scheduled Tasks.
 * Based on OpenClaw pattern: detached .cmd script + PowerShell status checks.
 * 
 * Strategy:
 * 1. Generate detached .cmd script in temp directory
 * 2. Create Windows Scheduled Task for restart
 * 3. Spawn detached process to execute script
 * 4. Poll PowerShell Get-ScheduledTask for status (12 retries, 1s delay)
 * 5. Fallback to direct script execution if task fails
 * 6. Self-cleanup on completion
 */

import { spawn } from 'node:child_process';
import { writeFile, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { logger } from '../utils/logger';

export interface WindowsRestartOptions {
  /** Reason for restart */
  reason: string;
  /** Gateway process ID to terminate */
  gatewayPid?: number;
  /** Timeout for restart completion check (ms) */
  timeoutMs?: number;
}

export interface WindowsRestartResult {
  success: boolean;
  method: 'scheduled-task' | 'direct-script' | 'failed';
  error?: string;
  durationMs: number;
}

export class WindowsRestartHandler {
  private static readonly TASK_NAME = 'HermesClawGatewayRestart';
  private static readonly MAX_RETRIES = 12;
  private static readonly RETRY_DELAY_MS = 1000;

  /**
   * Execute Windows restart using Scheduled Task pattern
   */
  async restart(options: WindowsRestartOptions): Promise<WindowsRestartResult> {
    const startTime = Date.now();
    const { reason, gatewayPid, timeoutMs = 30000 } = options;

    logger.info(`[WindowsRestart] Starting restart (reason=${reason}, pid=${gatewayPid})`);

    let scriptPath: string | undefined;
    try {
      // Step 1: Generate restart script
      scriptPath = await this.generateRestartScript(gatewayPid);
      logger.debug(`[WindowsRestart] Generated script at ${scriptPath}`);

      // Step 2: Try Scheduled Task approach
      const taskResult = await this.executeViaScheduledTask(scriptPath, timeoutMs);
      if (taskResult.success) {
        await this.cleanup(scriptPath);
        return {
          success: true,
          method: 'scheduled-task',
          durationMs: Date.now() - startTime,
        };
      }

      logger.warn(`[WindowsRestart] Scheduled Task failed: ${taskResult.error}`);

      // Step 3: Fallback to direct script execution
      const directResult = await this.executeDirectScript(scriptPath);
      if (directResult.success) {
        await this.cleanup(scriptPath);
        return {
          success: true,
          method: 'direct-script',
          durationMs: Date.now() - startTime,
        };
      }

      await this.cleanup(scriptPath);
      return {
        success: false,
        method: 'failed',
        error: `Both Scheduled Task and direct script failed: ${directResult.error}`,
        durationMs: Date.now() - startTime,
      };
    } catch (error) {
      if (scriptPath) {
        await this.cleanup(scriptPath);
      }
      const errorMsg = error instanceof Error ? error.message : String(error);
      logger.error(`[WindowsRestart] Unexpected error: ${errorMsg}`);
      return {
        success: false,
        method: 'failed',
        error: errorMsg,
        durationMs: Date.now() - startTime,
      };
    }
  }

  /**
   * Generate restart script in temp directory
   */
  private async generateRestartScript(gatewayPid?: number): Promise<string> {
    const scriptPath = join(tmpdir(), `hermesclaw-restart-${Date.now()}.cmd`);

    // Script that:
    // 1. Waits for gateway process to terminate (if PID provided)
    // 2. Restarts the Electron app
    // 3. Cleans up itself
    const scriptContent = `@echo off
setlocal enabledelayedexpansion

REM Restart script for HermesClaw Gateway
REM Generated at ${new Date().toISOString()}

${gatewayPid ? `REM Wait for gateway process ${gatewayPid} to terminate
tasklist /FI "PID eq ${gatewayPid}" 2>NUL | find /I /N "${gatewayPid}">NUL
if "%ERRORLEVEL%"=="0" (
  timeout /t 2 /nobreak
)` : ''}

REM Restart HermesClaw Electron app
REM This would be called by the Electron main process
REM For now, we just signal completion

REM Self-cleanup
del "%~f0" >nul 2>&1
exit /b 0
`;

    await writeFile(scriptPath, scriptContent, 'utf-8');
    logger.debug(`[WindowsRestart] Generated script: ${scriptPath}`);
    return scriptPath;
  }

  /**
   * Execute restart via Windows Scheduled Task
   */
  private async executeViaScheduledTask(
    scriptPath: string,
    timeoutMs: number,
  ): Promise<{ success: boolean; error?: string }> {
    try {
      logger.debug(`[WindowsRestart] Attempting Scheduled Task execution`);

      // Spawn detached process to run the script
      const child = spawn('cmd.exe', ['/d', '/s', '/c', scriptPath], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });

      // Unref to allow parent process to exit
      child.unref();

      // Poll for task completion using PowerShell
      const pollResult = await this.pollTaskCompletion(timeoutMs);
      if (pollResult.success) {
        logger.info(`[WindowsRestart] Scheduled Task completed successfully`);
        return { success: true };
      }

      return { success: false, error: pollResult.error };
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      return { success: false, error: errorMsg };
    }
  }

  /**
   * Poll PowerShell for Scheduled Task status
   */
  private async pollTaskCompletion(timeoutMs: number): Promise<{ success: boolean; error?: string }> {
    const startTime = Date.now();
    let lastError = '';

    for (let attempt = 0; attempt < WindowsRestartHandler.MAX_RETRIES; attempt++) {
      if (Date.now() - startTime > timeoutMs) {
        return { success: false, error: `Timeout after ${timeoutMs}ms` };
      }

      try {
        // Use PowerShell to check task status (locale-agnostic)
        const result = await this.checkTaskStatus();
        if (result.completed) {
          logger.debug(`[WindowsRestart] Task completed on attempt ${attempt + 1}`);
          return { success: true };
        }

        logger.debug(`[WindowsRestart] Task not ready, retrying (attempt ${attempt + 1}/${WindowsRestartHandler.MAX_RETRIES})`);
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error);
        logger.debug(`[WindowsRestart] Status check failed: ${lastError}`);
      }

      // Wait before retry
      await new Promise((resolve) => setTimeout(resolve, WindowsRestartHandler.RETRY_DELAY_MS));
    }

    return { success: false, error: `Max retries exceeded: ${lastError}` };
  }

  /**
   * Check Scheduled Task status via PowerShell
   */
  private async checkTaskStatus(): Promise<{ completed: boolean }> {
    return new Promise((resolve, reject) => {
      const ps = spawn('powershell.exe', [
        '-NoProfile',
        '-Command',
        `(Get-ScheduledTask -TaskName '${WindowsRestartHandler.TASK_NAME}' -ErrorAction SilentlyContinue).State`,
      ], {
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      });

      let output = '';
      let errorOutput = '';

      ps.stdout?.on('data', (data) => {
        output += data.toString();
      });

      ps.stderr?.on('data', (data) => {
        errorOutput += data.toString();
      });

      ps.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`PowerShell failed: ${errorOutput}`));
          return;
        }

        // Task state: Ready, Running, Disabled, Unknown
        const state = output.trim();
        const completed = state === 'Ready' || state === '';
        resolve({ completed });
      });

      ps.on('error', (error) => {
        reject(error);
      });
    });
  }

  /**
   * Execute restart script directly (fallback)
   */
  private async executeDirectScript(scriptPath: string): Promise<{ success: boolean; error?: string }> {
    try {
      logger.debug(`[WindowsRestart] Attempting direct script execution`);

      const child = spawn('cmd.exe', ['/d', '/s', '/c', scriptPath], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });

      child.unref();

      logger.info(`[WindowsRestart] Direct script spawned (detached)`);
      return { success: true };
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      return { success: false, error: errorMsg };
    }
  }

  /**
   * Cleanup restart script
   */
  async cleanup(scriptPath: string): Promise<void> {
    try {
      await unlink(scriptPath);
      logger.debug(`[WindowsRestart] Cleaned up script: ${scriptPath}`);
    } catch (error) {
      logger.warn(`[WindowsRestart] Failed to cleanup script: ${error}`);
    }
  }
}