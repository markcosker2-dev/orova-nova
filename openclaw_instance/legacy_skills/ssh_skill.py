# -*- coding: utf-8 -*-
"""
SSH Skill for MarkBot
Execute commands on remote servers via SSH
"""

import os
import subprocess
from pathlib import Path

# SSH config file for saved connections
SSH_CONFIG_FILE = Path(__file__).parent.parent / "ssh_hosts.json"


def ssh_execute(host: str, command: str, user: str = None, port: int = 22, timeout: int = 30):
    """Execute a command on a remote server via SSH
    
    Args:
        host: Hostname or IP address
        command: Command to execute
        user: SSH username (optional, uses default if not provided)
        port: SSH port (default 22)
        timeout: Command timeout in seconds
    """
    try:
        # Build SSH command
        ssh_target = f"{user}@{host}" if user else host
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", str(port),
            ssh_target,
            command
        ]
        
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "success": result.returncode == 0,
            "host": host,
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout[:3000] if result.stdout else "",
            "stderr": result.stderr[:1000] if result.returncode != 0 else ""
        }
        
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"SSH command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"success": False, "error": "SSH client not installed or not in PATH"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ssh_copy(host: str, local_path: str, remote_path: str, user: str = None, upload: bool = True):
    """Copy files to/from remote server via SCP
    
    Args:
        host: Hostname or IP
        local_path: Local file path
        remote_path: Remote file path
        user: SSH username
        upload: True to upload, False to download
    """
    try:
        ssh_target = f"{user}@{host}" if user else host
        
        if upload:
            scp_cmd = ["scp", local_path, f"{ssh_target}:{remote_path}"]
        else:
            scp_cmd = ["scp", f"{ssh_target}:{remote_path}", local_path]
        
        result = subprocess.run(
            scp_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        return {
            "success": result.returncode == 0,
            "action": "uploaded" if upload else "downloaded",
            "local": local_path,
            "remote": f"{host}:{remote_path}",
            "error": result.stderr if result.returncode != 0 else None
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def register_ssh_skills(TOOLS, tool_decorator):
    """Register SSH tools"""
    
    @tool_decorator("ssh", "Execute command on remote server via SSH")
    def _ssh(**kwargs):
        host = kwargs.get('host') or kwargs.get('server') or kwargs.get('ip')
        command = kwargs.get('command') or kwargs.get('cmd')
        user = kwargs.get('user') or kwargs.get('username')
        port = kwargs.get('port') or 22
        timeout = kwargs.get('timeout') or 30
        
        if not host:
            return {"success": False, "error": "Missing 'host' parameter"}
        if not command:
            return {"success": False, "error": "Missing 'command' parameter"}
        
        try:
            port = int(port)
            timeout = int(timeout)
        except:
            port = 22
            timeout = 30
        
        return ssh_execute(host, command, user, port, timeout)
    
    @tool_decorator("scp_upload", "Upload file to remote server")
    def _scp_upload(**kwargs):
        host = kwargs.get('host') or kwargs.get('server')
        local = kwargs.get('local_path') or kwargs.get('local') or kwargs.get('file')
        remote = kwargs.get('remote_path') or kwargs.get('remote')
        user = kwargs.get('user')
        
        if not all([host, local, remote]):
            return {"success": False, "error": "Need host, local_path, and remote_path"}
        
        return ssh_copy(host, local, remote, user, upload=True)
    
    @tool_decorator("scp_download", "Download file from remote server")
    def _scp_download(**kwargs):
        host = kwargs.get('host') or kwargs.get('server')
        local = kwargs.get('local_path') or kwargs.get('local')
        remote = kwargs.get('remote_path') or kwargs.get('remote') or kwargs.get('file')
        user = kwargs.get('user')
        
        if not all([host, local, remote]):
            return {"success": False, "error": "Need host, local_path, and remote_path"}
        
        return ssh_copy(host, local, remote, user, upload=False)
    
    TOOLS["ssh"] = {"func": _ssh, "description": "Execute SSH command on remote server"}
    TOOLS["scp_upload"] = {"func": _scp_upload, "description": "Upload file via SCP"}
    TOOLS["scp_download"] = {"func": _scp_download, "description": "Download file via SCP"}
    
    return TOOLS
