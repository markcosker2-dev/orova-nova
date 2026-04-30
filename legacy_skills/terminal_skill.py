# -*- coding: utf-8 -*-
"""
Terminal Skill for MarkBot
Execute shell commands
"""

import os
import subprocess
from pathlib import Path

# Working directory for commands
WORK_DIR = Path(os.environ.get("OROVA_DIR", "/home/node/app"))

# Dangerous commands that are blocked
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){",  # fork bomb
    "chmod -R 777 /",
]


def run_command(command: str, timeout: int = 30):
    """Execute a shell command
    
    Args:
        command: The command to execute
        timeout: Maximum seconds to wait (default 30)
    
    Returns:
        Command output and status
    """
    # Safety check
    command_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in command_lower:
            return {
                "success": False,
                "error": f"Command blocked for safety: contains '{blocked}'"
            }
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(WORK_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        
        stdout = result.stdout[:3000] if result.stdout else ""
        stderr = result.stderr[:1000] if result.stderr else ""
        
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "command": command,
            "stdout": stdout,
            "stderr": stderr if result.returncode != 0 else ""
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Command timed out after {timeout} seconds",
            "command": command
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": command
        }


def run_python(code: str, timeout: int = 30):
    """Execute Python code
    
    Args:
        code: Python code to execute
        timeout: Maximum seconds to wait
    """
    try:
        # Write code to temp file and execute
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        result = subprocess.run(
            ["python", temp_path],
            cwd=str(WORK_DIR),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Cleanup
        os.unlink(temp_path)
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:3000] if result.stdout else "",
            "error": result.stderr[:1000] if result.returncode != 0 else ""
        }
        
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Execution timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def register_terminal_skills(TOOLS, tool_decorator):
    """Register Terminal tools"""
    
    @tool_decorator("run_command", "Execute a shell command")
    def _run_command(**kwargs):
        command = kwargs.get('command') or kwargs.get('cmd') or kwargs.get('shell')
        timeout = kwargs.get('timeout') or 30
        
        if not command:
            return {"success": False, "error": "Missing 'command' parameter"}
        
        try:
            timeout = int(timeout)
        except:
            timeout = 30
        
        # Limit timeout
        timeout = min(timeout, 120)
        
        return run_command(command, timeout)
    
    @tool_decorator("run_python", "Execute Python code")
    def _run_python(**kwargs):
        code = kwargs.get('code') or kwargs.get('python') or kwargs.get('script')
        timeout = kwargs.get('timeout') or 30
        
        if not code:
            return {"success": False, "error": "Missing 'code' parameter"}
        
        try:
            timeout = int(timeout)
        except:
            timeout = 30
        
        return run_python(code, timeout)
    
    TOOLS["run_command"] = {"func": _run_command, "description": "Execute shell command"}
    TOOLS["run_python"] = {"func": _run_python, "description": "Execute Python code"}
    
    return TOOLS
