"""
Delete command for removing subscriptions by name.
"""

import argparse
import datetime
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

        # Create a mutually exclusive group for --dry-run and --force
        mode_group = parser.add_mutually_exclusive_group()
        mode_group.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the subscription that would be deleted without making changes",
        )
        mode_group.add_argument(
            "--force",
            action="store_true",
            help="Delete the subscription without confirmation or warnings",
        )

        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm deletion of the subscription",
        )

    def _get_subscription_by_name_case_insensitive(self, db_manager: DatabaseManager, name: str) -> List[
        Dict[str, Any]]:
        """
        Get subscriptions with case-insensitive name matching.

        Args:
            db_manager: Database manager instance
            name: Name to search for (case-insensitive)

        Returns:
            List of matching subscription dictionaries
        """
        # Get all subscriptions
        all_subscriptions = db_manager.get_subscriptions()

        # Filter subscriptions with case-insensitive matching
        return [sub for sub in all_subscriptions if sub['name'].lower() == name.lower()]

    def _get_child_subscriptions(self, db_manager: DatabaseManager, parent_id: str) -> List[Dict[str, Any]]:
        """
        Get all child subscriptions that have the given parent_name.

        Args:
            db_manager: Database manager instance
            parent_name: Name of the parent subscription

        Returns:
            List of child subscription dictionaries
        """
        # Get all subscriptions
        all_subscriptions = db_manager.get_subscriptions()

        # Filter subscriptions that have the given parent_name
        return [
            sub for sub in all_subscriptions
            if 'parent_subscription_id' in sub and sub['parent_subscription_id'] == parent_id
        ]

    def _check_budget_contribution(self, subscription: Dict[str, Any]) -> bool:
        """
        Check if the subscription contributes to current or recent month's budget.

        Args:
            subscription: The subscription data

        Returns:
            True if the subscription contributes to current month's budget, False otherwise.
        """
        # Get the current month and year
        current_date = datetime.datetime.now()
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

        # Validate that --dry-run and --force are not used together
        if args.dry_run and args.force:
            print(f"```\nCannot use --dry-run and --force together.\n```")
            return 1

        # Get subscription by name (case-insensitive) or ID
        if args.name is not None:
            subscriptions = self._get_subscription_by_name_case_insensitive(db_manager, args.name)
            identifier = args.name
            id_type = "name"

            # Check for multiple matches with the same case-insensitive name
            if len(subscriptions) > 1:
                print(
                    f"```\nMultiple subscriptions found with name '{args.name}' (case-insensitive).\nUse --id to delete the exact subscription.\n```")
                return 1

            # Improved error message when no subscription is found by name
            if not subscriptions:
                print(
                    f"```\nNo subscription found with name '{args.name}'.\nTip: Use the 'view' command to list all subscriptions.\n```")
                return 1

        else:  # args.id is not None
            subscriptions = db_manager.get_subscriptions(subscription_id=args.id)
            identifier = args.id
            id_type = "ID"

            # Improved error message when no subscription is found by ID
            if not subscriptions:
                print(
                    f"```\nNo subscription found with ID {args.id}.\nTip: Use the 'view' command to list all subscriptions with their IDs.\n```")
                return 1

        # Store subscription details
        subscription = subscriptions[0]

        # Check for child subscriptions linked to this parent, regardless of flags
        child_subscriptions = self._get_child_subscriptions(db_manager, subscription['id'])
        if child_subscriptions:
            child_names = [child['name'] for child in child_subscriptions]
            child_list = "\n- " + "\n- ".join(child_names)
            print(
                f"```\nCannot delete '{subscription['name']}' because it has linked child subscriptions:{child_list}\nPlease delete or reassign these child subscriptions first.\n```")
            return 1

        # Handle dry run mode
        if args.dry_run:
            self._display_subscription_summary(subscription, is_dry_run=True)

            # Check if subscription contributes to current month's budget
            if self._check_budget_contribution(subscription):
                current_month = datetime.datetime.now().strftime("%B %Y")
                print(f"```\nNote: This subscription contributes to your budget utilization for {current_month}.\n```")

            return 0

        # Check if deletion is confirmed for actual deletion (skip if --force is used)
        if not args.confirm and not args.force:
            print(f"```\nDeletion not confirmed. Use --confirm to permanently delete the subscription.\n```")
            return 1

        # Delete the subscription
        try:
            # Use ID for deletion to ensure we delete the exact subscription
            # (since we already have the subscription object, we can get its ID)
            success = db_manager.delete_subscription_by_id(subscription['id'])

            if success:
                # For force mode, just show a simple message
                if args.force:
                    print(f"```\nSubscription '{subscription['name']}' has been permanently deleted.\n```")
                    return 0

                # Otherwise, show normal success message with details
                self._display_subscription_summary(subscription)

                # Display budget warning if applicable (only in non-force mode)
                if self._check_budget_contribution(subscription):
                    current_month = datetime.datetime.now().strftime("%B %Y")
                    print(
                        f"```\nWarning: This subscription contributed to your budget utilization for {current_month}.\nYou may want to review your budget breakdown.\n```")

                return 0
            else:
                print(f"```\nFailed to delete subscription with {id_type}: {identifier}\n```")
                return 1
        except Exception as e:
            print(f"```\nError deleting subscription: {e}\n```")
            return 1