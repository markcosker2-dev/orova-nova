"""
Tenant Cloning System - Automatically create new niches by cloning successful templates
Enables rapid expansion into new luxury verticals.
"""

import os
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TenantCloner:
    """
    Clones successful tenant configurations for new niches.
    Automatically adapts scraping parameters and business logic.
    """

    def __init__(self, tenants_dir: str = "tenants"):
        self.tenants_dir = Path(tenants_dir)
        self.tenants_dir.mkdir(exist_ok=True)

    def clone_tenant(self, source_tenant: str, new_tenant_id: str, new_niche_config: Dict[str, Any]) -> str:
        """
        Clone an existing tenant configuration for a new niche.

        Args:
            source_tenant: ID of tenant to clone (e.g., "car_dealer")
            new_tenant_id: New tenant ID (e.g., "luxury_real_estate")
            new_niche_config: Configuration specific to new niche

        Returns:
            Success/error message
        """
        source_file = self.tenants_dir / f"{source_tenant}.json"
        target_file = self.tenants_dir / f"{new_tenant_id}.json"

        if not source_file.exists():
            return f"❌ Source tenant '{source_tenant}' not found"

        if target_file.exists():
            return f"❌ Target tenant '{new_tenant_id}' already exists"

        try:
            # Load source configuration
            with open(source_file, 'r') as f:
                source_config = json.load(f)

            # Create new configuration
            new_config = self._adapt_config_for_niche(source_config, new_tenant_id, new_niche_config)

            # Save new configuration
            with open(target_file, 'w') as f:
                json.dump(new_config, f, indent=2)

            logger.info(f"Cloned tenant {source_tenant} to {new_tenant_id}")
            return f"✅ Successfully cloned tenant '{source_tenant}' to '{new_tenant_id}'"

        except Exception as e:
            logger.error(f"Failed to clone tenant: {e}")
            return f"❌ Failed to clone tenant: {str(e)}"

    def _adapt_config_for_niche(self, source_config: Dict[str, Any], new_tenant_id: str, niche_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adapt the source configuration for the new niche.
        """
        # Deep copy the source config
        new_config = json.loads(json.dumps(source_config))

        # Update tenant-specific fields
        new_config["tenant_id"] = new_tenant_id
        new_config["name"] = niche_config.get("name", f"Luxury {new_tenant_id.replace('_', ' ').title()}")
        new_config["niche"] = niche_config.get("niche", new_tenant_id.replace('_', ' '))

        # Update scraping parameters
        if "scraping_params" in niche_config:
            new_config["scraping_params"].update(niche_config["scraping_params"])

        # Update Meta Ads config if provided
        if "meta_ads_config" in niche_config:
            new_config["meta_ads_config"].update(niche_config["meta_ads_config"])

        # Update Google Sheets tabs if provided
        if "google_sheets" in niche_config:
            new_config["google_sheets"].update(niche_config["google_sheets"])

        # Generate new sheet ID for Google Sheets (in practice, you'd create a new sheet)
        # For now, we'll use a placeholder
        new_config["google_sheets"]["master_sheet_id"] = f"new_sheet_for_{new_tenant_id}"

        return new_config

    def list_available_tenants(self) -> Dict[str, Any]:
        """List all available tenant configurations."""
        tenants = {}
        for config_file in self.tenants_dir.glob("*.json"):
            tenant_id = config_file.stem
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    tenants[tenant_id] = {
                        "name": config.get("name", tenant_id),
                        "niche": config.get("niche", "Unknown"),
                        "status": "active"
                    }
            except Exception as e:
                tenants[tenant_id] = {
                    "name": tenant_id,
                    "niche": "Error loading config",
                    "status": f"error: {str(e)}"
                }

        return tenants

    def get_tenant_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific tenant."""
        config_file = self.tenants_dir / f"{tenant_id}.json"
        if not config_file.exists():
            return None

        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load tenant config {tenant_id}: {e}")
            return None

    def quick_clone_presets(self) -> Dict[str, Dict[str, Any]]:
        """
        Return preset configurations for common luxury niches.
        These can be used with clone_tenant() to quickly spin up new verticals.
        """
        return {
            "luxury_real_estate": {
                "name": "Luxury Real Estate",
                "niche": "high-end property sales",
                "scraping_params": {
                    "keywords": ["luxury homes", "million dollar listings", "luxury real estate"],
                    "locations": ["Beverly Hills", "Miami Beach", "Aspen", "New York City"],
                    "luxury_alignment_threshold": 90
                },
                "meta_ads_config": {
                    "target_audience": "High-net-worth home buyers",
                    "budget_daily": 200,
                    "roas_threshold": 3.0
                }
            },
            "luxury_watches": {
                "name": "Luxury Timepieces",
                "niche": "high-end watches and jewelry",
                "scraping_params": {
                    "keywords": ["luxury watches", "rolex dealer", "cartier boutique"],
                    "locations": ["New York", "London", "Dubai", "Hong Kong"],
                    "luxury_alignment_threshold": 95
                },
                "meta_ads_config": {
                    "target_audience": "Ultra-high-net-worth watch collectors",
                    "budget_daily": 150,
                    "roas_threshold": 2.5
                }
            },
            "luxury_yachts": {
                "name": "Luxury Yacht Sales",
                "niche": "superyacht and luxury boat sales",
                "scraping_params": {
                    "keywords": ["luxury yachts", "superyacht dealer", "yacht brokerage"],
                    "locations": ["Monaco", "Fort Lauderdale", "Miami", "Ibiza"],
                    "luxury_alignment_threshold": 92
                },
                "meta_ads_config": {
                    "target_audience": "Ultra-high-net-worth yacht owners",
                    "budget_daily": 300,
                    "roas_threshold": 2.8
                }
            },
            "luxury_art": {
                "name": "Fine Art Dealerships",
                "niche": "contemporary and classic fine art",
                "scraping_params": {
                    "keywords": ["fine art gallery", "contemporary art", "luxury art dealer"],
                    "locations": ["New York", "London", "Paris", "Los Angeles"],
                    "luxury_alignment_threshold": 88
                },
                "meta_ads_config": {
                    "target_audience": "Art collectors and institutions",
                    "budget_daily": 100,
                    "roas_threshold": 2.2
                }
            }
        }