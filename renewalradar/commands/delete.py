"""
Delete command for removing subscriptions by name.
"""

import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.registry import register_command
from renewalradar.utils.date_utils import parse_date


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
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the subscription that would be deleted without making changes",
        )

    def _check_budget_contribution(self, subscription: Dict[str, Any]) -> bool:
        """
        Check if the subscription contributes to current or recent month's budget.

        Args:
            subscription: The subscription data

        Returns:
            True if the subscription contributes to current month's budget, False otherwise.
        """
        # Get the current month and year
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year

        # Check if the subscription has renewal date in the current month
        if 'renewal_date' in subscription and subscription['renewal_date']:
            try:
                renewal_date = parse_date(subscription['renewal_date'])
                if renewal_date.month == current_month and renewal_date.year == current_year:
                    return True
            except ValueError:
                pass  # Invalid date format, continue checking

        # Check if the subscription has start date in the current month
        if 'start_date' in subscription and subscription['start_date']:
            try:
                start_date = parse_date(subscription['start_date'])
                if start_date.month == current_month and start_date.year == current_year:
                    return True
            except ValueError:
                pass  # Invalid date format, continue checking

        return False

    def _display_subscription_summary(self, subscription: Dict[str, Any], is_dry_run: bool = False) -> None:
        """
        Display a summary of the subscription.

        Args:
            subscription: The subscription data to display
            is_dry_run: Whether this is a dry run or actual deletion
        """
        print("```")
        if is_dry_run:
            print(f"Dry Run: The following subscription would be deleted:")
        else:
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

        # Store subscription details
        subscription = subscriptions[0]

        # Handle dry run mode
        if args.dry_run:
            self._display_subscription_summary(subscription, is_dry_run=True)

            # Check if subscription contributes to current month's budget
            if self._check_budget_contribution(subscription):
                current_month = datetime.now().strftime("%B %Y")
                print(f"```\nNote: This subscription contributes to your budget utilization for {current_month}.\n```")

            return 0

        # Check if deletion is confirmed for actual deletion
        if not args.confirm:
            print(f"```\nDeletion not confirmed. Use --confirm to permanently delete the subscription.\n```")
            return 1

        # Check if subscription contributes to current month's budget
        contributes_to_budget = self._check_budget_contribution(subscription)

        # Delete the subscription
        try:
            if args.name is not None:
                success = db_manager.delete_subscription_by_name(args.name)
            else:  # args.id is not None
                success = db_manager.delete_subscription_by_id(args.id)

            if success:
                # Show success message with subscription details
                self._display_subscription_summary(subscription)

                # Display budget warning if applicable
                if contributes_to_budget:
                    current_month = datetime.now().strftime("%B %Y")
                    print(
                        f"```\nWarning: This subscription contributed to your budget utilization for {current_month}.\nYou may want to review your budget breakdown.\n```")

                return 0
            else:
                print(f"```\nFailed to delete subscription with {id_type}: {identifier}\n```")
                return 1
        except Exception as e:
            print(f"```\nError deleting subscription: {e}\n```")
            return 1