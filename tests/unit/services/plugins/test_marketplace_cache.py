"""Tests for marketplace cache invalidation.

Reference: docs/skill-system.md — Marketplace cache invalidation
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pode_agent.services.plugins.marketplace import (
    add_marketplace,
    list_marketplaces,
    update_marketplace,
)


class TestMarketplaceCacheInvalidation:
    """Tests for marketplace cache invalidation."""

    def test_update_overwrites_cache(self, tmp_path: Path) -> None:
        """Verify that update_marketplace() overwrites existing cache."""
        # Setup: Create marketplace source with initial plugin
        marketplace_dir = tmp_path / "test-marketplace"
        marketplace_dir.mkdir()

        initial_manifest = {
            "name": "test-marketplace",
            "version": "1.0.0",
            "plugins": [
                {
                    "name": "plugin-v1",
                    "version": "1.0.0",
                    "source": "./plugin-v1",
                }
            ],
        }
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps(initial_manifest), encoding="utf-8"
        )

        # Add marketplace
        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            add_marketplace(f"file:{marketplace_dir}", name="test-mkt")

            # Initial update - cache should have plugin-v1
            entry = update_marketplace("test-mkt")
            assert entry["cache"] is not None
            assert len(entry["cache"]["plugins"]) == 1
            assert entry["cache"]["plugins"][0]["name"] == "plugin-v1"

            # Modify marketplace.json
            updated_manifest = {
                "name": "test-marketplace",
                "version": "1.0.0",
                "plugins": [
                    {
                        "name": "plugin-v2",  # Changed
                        "version": "2.0.0",
                        "source": "./plugin-v2",
                    }
                ],
            }
            (marketplace_dir / "marketplace.json").write_text(
                json.dumps(updated_manifest), encoding="utf-8"
            )

            # Update again - cache should be invalidated and refreshed
            entry = update_marketplace("test-mkt")
            assert entry["cache"] is not None
            assert len(entry["cache"]["plugins"]) == 1
            assert entry["cache"]["plugins"][0]["name"] == "plugin-v2"  # New plugin
            assert "updated_at" in entry["cache"]

    def test_update_timestamp_changes(self, tmp_path: Path) -> None:
        """Verify that updated_at timestamp changes on each update."""
        marketplace_dir = tmp_path / "test-mkt"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "test",
                    "version": "1.0.0",
                    "plugins": [],
                }
            ),
            encoding="utf-8",
        )

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            add_marketplace(f"file:{marketplace_dir}", name="test")

            # First update
            entry1 = update_marketplace("test")
            timestamp1 = entry1["cache"]["updated_at"]

            time.sleep(0.01)  # Ensure time difference

            # Second update
            entry2 = update_marketplace("test")
            timestamp2 = entry2["cache"]["updated_at"]

            assert timestamp1 != timestamp2, "Timestamp should change on update"

    def test_update_with_missing_manifest_keeps_cache_none(self, tmp_path: Path) -> None:
        """Verify that update fails gracefully when marketplace.json is missing."""
        marketplace_dir = tmp_path / "broken-mkt"
        marketplace_dir.mkdir()
        # No marketplace.json file

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            add_marketplace(f"file:{marketplace_dir}", name="broken")

            # Update should not crash, cache should remain None
            entry = update_marketplace("broken")
            assert entry["cache"] is None

    def test_update_with_invalid_json_logs_error(self, tmp_path: Path) -> None:
        """Verify that update handles invalid JSON gracefully."""
        marketplace_dir = tmp_path / "invalid-json-mkt"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text(
            "{ invalid json }",  # Broken JSON
            encoding="utf-8",
        )

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            add_marketplace(f"file:{marketplace_dir}", name="invalid")

            # Update should not crash
            entry = update_marketplace("invalid")
            assert entry["cache"] is None

    def test_update_with_schema_errors_logs_warning(self, tmp_path: Path) -> None:
        """Verify that update handles validation errors gracefully."""
        marketplace_dir = tmp_path / "schema-error-mkt"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    # Missing required 'name' field
                    "plugins": [
                        {"name": "plugin1", "source": "./p1"}
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            add_marketplace(f"file:{marketplace_dir}", name="schema-error")

            # Update should log warning but not crash
            entry = update_marketplace("schema-error")
            # Cache should remain None due to validation errors
            assert entry["cache"] is None

    def test_multiple_marketplaces_independent_cache(self, tmp_path: Path) -> None:
        """Verify that updating one marketplace doesn't affect others."""
        # Create two marketplaces
        mkt1_dir = tmp_path / "mkt1"
        mkt1_dir.mkdir()
        (mkt1_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "mkt1",
                    "version": "1.0.0",
                    "plugins": [
                        {"name": "plugin-a", "version": "1.0.0", "source": "./a"}
                    ],
                }
            ),
            encoding="utf-8",
        )

        mkt2_dir = tmp_path / "mkt2"
        mkt2_dir.mkdir()
        (mkt2_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "mkt2",
                    "version": "1.0.0",
                    "plugins": [
                        {"name": "plugin-b", "version": "1.0.0", "source": "./b"}
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            add_marketplace(f"file:{mkt1_dir}", name="marketplace-1")
            add_marketplace(f"file:{mkt2_dir}", name="marketplace-2")

            # Update only marketplace-1
            update_marketplace("marketplace-1")

            # Verify marketplace-2 cache is still None
            marketplaces = list_marketplaces()
            mkt1 = next(m for m in marketplaces if m["name"] == "marketplace-1")
            mkt2 = next(m for m in marketplaces if m["name"] == "marketplace-2")

            assert mkt1["cache"] is not None
            assert mkt2["cache"] is None

    def test_update_nonexistent_marketplace_raises(self, tmp_path: Path) -> None:
        """Verify that updating nonexistent marketplace raises KeyError."""
        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            with pytest.raises(KeyError, match="Marketplace not found"):
                update_marketplace("nonexistent")

    def test_update_directory_source_with_marketplace_in_subdir(
        self, tmp_path: Path
    ) -> None:
        """Verify update works when marketplace.json is in subdirectory."""
        # Source is a directory, marketplace.json is inside
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        mkt_dir = source_dir / "marketplace"
        mkt_dir.mkdir()
        (mkt_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "nested-mkt",
                    "version": "1.0.0",
                    "plugins": [
                        {"name": "nested-plugin", "version": "1.0.0", "source": "./p"}
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            # Add with directory type
            add_marketplace(f"dir:{mkt_dir}", name="nested")

            entry = update_marketplace("nested")
            assert entry["cache"] is not None
            assert len(entry["cache"]["plugins"]) == 1
            assert entry["cache"]["plugins"][0]["name"] == "nested-plugin"


class TestMarketplaceCacheWithPluginInstallation:
    """Integration tests: cache invalidation affects plugin installation."""

    def test_install_uses_updated_cache(self, tmp_path: Path) -> None:
        """Verify that install_plugin uses the updated cache."""
        from pode_agent.services.plugins.marketplace import install_plugin

        # Create marketplace with plugin
        marketplace_dir = tmp_path / "marketplace"
        marketplace_dir.mkdir()

        plugin_dir = marketplace_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"}),
            encoding="utf-8",
        )

        manifest = {
            "name": "test-marketplace",
            "version": "1.0.0",
            "plugins": [
                {
                    "name": "test-plugin",
                    "version": "1.0.0",
                    "source": "./test-plugin",
                }
            ],
        }
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        with patch(
            "pode_agent.services.plugins.marketplace._plugins_dir",
            return_value=tmp_path / "plugins",
        ):
            # Add and update marketplace
            add_marketplace(f"file:{marketplace_dir}", name="test-mkt")
            update_marketplace("test-mkt")

            # Install from marketplace
            installed = install_plugin(
                "marketplace:test-mkt/test-plugin", install_mode="plugin-pack"
            )
            assert installed.name == "test-plugin"
            assert installed.enabled
