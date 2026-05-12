# -*- coding: utf-8 -*-
"""
File System Skill for MarkBot
Read, write, and list files/directories
"""

import os
from pathlib import Path

# Base directory for safety (only allow access within OROVA folder)
BASE_DIR = Path(os.environ.get("OROVA_DIR", "/home/node/app")).resolve()


def _safe_path(path: str) -> Path:
    """Ensure path is within allowed directory"""
    requested = Path(path).resolve()
    
    # Allow absolute paths within BASE_DIR or relative paths
    if str(requested).startswith(str(BASE_DIR)):
        return requested
    
    # Treat as relative to BASE_DIR
    relative = BASE_DIR / path
    return relative.resolve()


def read_file(path: str, max_lines: int = 100):
    """Read contents of a file
    
    Args:
        path: File path (relative to app dir or absolute within OROVA)
        max_lines: Maximum lines to return to avoid overwhelming output
    """
    try:
        file_path = _safe_path(path)
        
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {path}"}
        
        if not file_path.is_file():
            return {"success": False, "error": f"Not a file: {path}"}
        
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        content = "".join(lines[:max_lines])
        
        return {
            "success": True,
            "path": str(file_path),
            "total_lines": total_lines,
            "showing_lines": min(max_lines, total_lines),
            "content": content
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, append: bool = False):
    """Write content to a file
    
    Args:
        path: File path
        content: Content to write
        append: If True, append to file instead of overwriting
    """
    try:
        file_path = _safe_path(path)
        
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = 'a' if append else 'w'
        with open(file_path, mode, encoding='utf-8') as f:
            f.write(content)
        
        return {
            "success": True,
            "path": str(file_path),
            "action": "appended" if append else "written",
            "bytes": len(content)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_directory(path: str = "."):
    """List contents of a directory
    
    Args:
        path: Directory path (defaults to current app directory)
    """
    try:
        dir_path = _safe_path(path)
        
        if not dir_path.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        
        if not dir_path.is_dir():
            return {"success": False, "error": f"Not a directory: {path}"}
        
        items = []
        for item in sorted(dir_path.iterdir()):
            info = {
                "name": item.name,
                "type": "dir" if item.is_dir() else "file"
            }
            if item.is_file():
                info["size"] = item.stat().st_size
            items.append(info)
        
        return {
            "success": True,
            "path": str(dir_path),
            "count": len(items),
            "items": items[:50]  # Limit to 50 items
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def register_filesystem_skills(TOOLS, tool_decorator):
    """Register File System tools"""
    
    @tool_decorator("read_file", "Read contents of a file")
    def _read_file(**kwargs):
        path = kwargs.get('path') or kwargs.get('file') or kwargs.get('filename')
        max_lines = kwargs.get('max_lines') or kwargs.get('lines') or 100
        
        if not path:
            return {"success": False, "error": "Missing 'path' parameter"}
        
        try:
            max_lines = int(max_lines)
        except:
            max_lines = 100
            
        return read_file(path, max_lines)
    
    @tool_decorator("write_file", "Write content to a file")
    def _write_file(**kwargs):
        path = kwargs.get('path') or kwargs.get('file') or kwargs.get('filename')
        content = kwargs.get('content') or kwargs.get('text') or kwargs.get('data') or ""
        append = kwargs.get('append', False)
        
        if not path:
            return {"success": False, "error": "Missing 'path' parameter"}
        
        return write_file(path, content, append)
    
    @tool_decorator("list_dir", "List contents of a directory")
    def _list_dir(**kwargs):
        path = kwargs.get('path') or kwargs.get('directory') or kwargs.get('dir') or "."
        return list_directory(path)
    
    TOOLS["read_file"] = {"func": _read_file, "description": "Read file contents"}
    TOOLS["write_file"] = {"func": _write_file, "description": "Write to a file"}
    TOOLS["list_dir"] = {"func": _list_dir, "description": "List directory contents"}
    
    return TOOLS
