"""
Delete command for removing subscriptions by name.
"""

import argparse
from typing import Dict, Any, List, Optional

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.registry import register_command


@register_command
class DeleteCommand(Command):
    """Command to delete a subscription by its name."""

    name = "delete"
    description = "Delete a subscription by name"

    @classmethod
    def register_arguments(cls, parser):
        """Configure argument parser for the delete command."""
        parser.add_argument(
            "--name",
            type=str,
            required=True,
            help="Name of the subscription to delete",
        )

        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm deletion (required to actually delete the subscription)",
        )

    def execute(self, args: argparse.Namespace) -> int:
        """Execute the delete command with the given arguments."""
        # Check if the confirmation flag is provided
        if not args.confirm:
            print("```\nDeletion not confirmed. Use --confirm to permanently delete the subscription.\n```")
            return 1

        db_manager = DatabaseManager()

        # Check if subscription exists
        subscriptions = db_manager.get_subscription_by_name(name=args.name)

        if not subscriptions:
            print(f"No subscription found with name: {args.name}")
            return 1

        # Delete the subscription
        try:
            db_manager.delete_subscription(subscriptions.id)
            print(f"Subscription '{args.name}' has been deleted.")
            return 0
        except Exception as e:
            print(f"Error deleting subscription: {e}")
            return 1
