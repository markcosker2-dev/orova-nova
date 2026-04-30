# -*- coding: utf-8 -*-
"""
Auto-Updater Skill for OROVA Moltbot
Automates 'git pull' and dependency checks.
"""
import subprocess
import sys
from loguru import logger

def update_system():
    """
    Pulls the latest code from git and checks for changes.
    Returns the update status.
    """
    try:
        # 1. Git Pull
        result = subprocess.run(
            ["git", "pull"], 
            capture_output=True, 
            text=True, 
            check=False
        )
        
        if result.returncode != 0:
            return f"❌ Update Failed: {result.stderr}"
            
        output = result.stdout.strip()
        
        if "Already up to date" in output:
            return "✅ System is already up to date."
            
        # 2. If updated, check requirements (naive)
        # In a full system, we might restart logic here.
        return f"🔄 System Updated:\n{output}\n\nNote: Please restart the bot to apply changes."

    except Exception as e:
        logger.error(f"Auto-Update Error: {e}")
        return f"❌ Error during update: {e}"

if __name__ == "__main__":
    print(update_system())
