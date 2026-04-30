"""
Core_Engine/config.py
Loads industry-specific configurations from Niche_Verticals/.
"""

import os
import json
import logging

logger = logging.getLogger("nova.config")

class ConfigLoader:
    """Loads vertical-specific configuration from Niche_Verticals/."""
    
    def __init__(self, root_dir: str = "Niche_Verticals"):
        # Get absolute path relative to this file's directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.root_dir = os.path.join(base_dir, root_dir)

    def get_vertical_config(self, vertical: str) -> dict:
        """
        Load all config files for a given vertical.
        Returns dict with keys: queries, scoring_rules, email_templates
        """
        path = os.path.join(self.root_dir, vertical)
        config = {}
        
        if not os.path.isdir(path):
            logger.warning(f"[CONFIG] Vertical directory not found: {path}")
            return {}

        for filename in ['email_templates.json', 'queries.json', 'scoring_rules.json']:
            file_path = os.path.join(path, filename)
            key = filename.split('.')[0]
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        config[key] = json.load(f)
                except Exception as e:
                    logger.error(f"[CONFIG] Failed to load {filename} for {vertical}: {e}")
                    config[key] = {}
            else:
                config[key] = {}
                
        return config

    def list_verticals(self) -> list:
        """List all available verticals in the Niche_Verticals directory."""
        if not os.path.isdir(self.root_dir):
            return []
        return [
            d for d in os.listdir(self.root_dir)
            if os.path.isdir(os.path.join(self.root_dir, d))
        ]
