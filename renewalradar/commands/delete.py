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
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--name",
            type=str,
            help="Name of the subscription to delete",
        )
        group.add_argument(
            "--id",
            type=int,
            help="ID of the subscription to delete",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm deletion of the subscription",
        )

    def execute(self, args: argparse.Namespace) -> int:
        """Execute the delete command with the given arguments."""
        db_manager = DatabaseManager()

        # Determine which identifier to use
        if args.name is not None and args.id is not None:
            print(f"```\nPlease provide either --name or --id, not both.\n```")
            return 1
        elif args.name is None and args.id is None:
            print(f"```\nYou must provide either --name or --id to delete a subscription.\n```")
            return 1

        # Get subscription by name or ID
        if args.name is not None:
            subscriptions = db_manager.get_subscriptions(name=args.name)
            identifier = args.name
            id_type = "name"
        else:  # args.id is not None
            subscriptions = db_manager.get_subscriptions(subscription_id=args.id)
            identifier = args.id
            id_type = "ID"

        # Check if subscription exists
        if not subscriptions:
            print(f"```\nNo subscription found with {id_type}: {identifier}\n```")
            return 1

        # Store subscription details before deletion for summary
        subscription = subscriptions[0]

        # Check if deletion is confirmed
        if not args.confirm:
            print(f"```\nDeletion not confirmed. Use --confirm to permanently delete the subscription.\n```")
            return 1

        # Delete the subscription
        try:
            if args.name is not None:
                success = db_manager.delete_subscription_by_name(args.name)
            else:  # args.id is not None
                success = db_manager.delete_subscription_by_id(args.id)

            if success:
                # Show success message with subscription details
                print("```")
                print(f"Subscription deleted:")
                print(f"Name: {subscription['name']}")
                print(f"Cost: {subscription['cost']} {subscription['currency']}")
                print(f"Billing Cycle: {subscription['billing_cycle']}")

                # Include tags if available
                if 'tags' in subscription and subscription['tags']:
                    print(f"Tags: {subscription['tags']}")

                # Include any other relevant fields
                if 'start_date' in subscription:
                    print(f"Start Date: {subscription['start_date']}")
                if 'renewal_date' in subscription:
                    print(f"Renewal Date: {subscription['renewal_date']}")
                if 'payment_method' in subscription:
                    print(f"Payment Method: {subscription['payment_method']}")
                print("```")

                return 0
            else:
                print(f"```\nFailed to delete subscription with {id_type}: {identifier}\n```")
                return 1
        except Exception as e:
            print(f"```\nError deleting subscription: {e}\n```")
            return 1
