# renewalradar/config.py
"""Command registry and application configuration for WordWise."""

from renewalradar.registry import COMMANDS
# Import all command modules to trigger decorator registration
from renewalradar.commands import AddCommand, ViewCommand
# add future commands herea

AVAILABLE_COMMANDS = COMMANDS
