"""Lightsheet microscope controller package."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = PACKAGE_ROOT / "config.ini"
RIG_SPECIFIC_PATH = PACKAGE_ROOT / "config.rig-specific.ini"
HARDWARE_INVENTORY_PATH = PACKAGE_ROOT / "hardware_inventory.yaml"
