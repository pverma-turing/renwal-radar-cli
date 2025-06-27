from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from renewalradar.registry import register_command
from renewalradar.utils.status_utils import print_status_help, VALID_STATUSES, get_status_error_message
from renewalradar.utils.validators import ValidationRegistry


@register_command
class UpdateStatusCommand(Command):
    """Command for updating a subscription's status."""

    name = "update-status"
    description = "Update the status of an existing subscription"

    def __init__(self):
        """Initialize update-status command."""
        super().__init__()

    @classmethod
    def register_arguments(self, parser):
        """Set up argument parser for update-status command."""

        parser.add_argument(
            "subscription_id",
            type=int,
            help="ID of the subscription to update"
        )

        parser.add_argument(
            "--status",
            choices=Subscription.VALID_STATUSES,
            help="New status for the subscription"
        )

        parser.add_argument(
            "--payment-method",
            help="Update the payment method"
        )

        parser.add_argument(
            "--add-tag",
            action="append",
            dest="add_tags",
            help="Add a tag to the subscription. Can be used multiple times."
        )

        # Update options
        parser.add_argument(
            "--set-status",
            choices=Subscription.VALID_STATUSES,
            help="Set new status for the subscription"
        )

        parser.add_argument(
            "--set-payment-method",
            help="Set new payment method for the subscription"
        )

        parser.add_argument(
            "--set-tags",
            nargs="+",
            help="Set completely new tags for the subscription (replaces all existing tags)"
        )

        parser.add_argument(
            "--remove-tag",
            action="append",
            dest="remove_tags",
            help="Remove a tag from the subscription. Can be used multiple times."
        )

        # Help flags for valid values
        parser.add_argument(
            "--help-tags",
            action="store_true",
            help="Show list of valid tags"
        )

        parser.add_argument(
            "--help-payment-methods",
            action="store_true",
            help="Show list of valid payment methods"
        )

        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        """Execute update-status command."""
        try:
            # Check if help-status flag is set
            # Check if help flags were used
            if args.help_tags:
                ValidationRegistry.print_valid_tags()
                return 0

            if args.help_payment_methods:
                ValidationRegistry.print_valid_payment_methods()
                return 0

            # Check if any update was specified
            if not (args.status or args.payment_method or args.add_tags or args.remove_tags
                    or args.set_status or args.set_payment_method or args.set_tags):
                raise ValueError(
                    "No update specified. Please provide at least one of: --status, --payment-method, --add-tag, "
                    "--remove-tag", "--set-status", "--set-payment-method", "--set-tags")

            # Get the subscription to update
            subscription = self._get_subscription(args.subscription_id)
            if not subscription:
                raise ValueError(f"Subscription with ID {args.subscription_id} not found.")
            # Track changes for user feedback
            changes = []

            # Update status if specified
            if args.status:
                old_status = subscription.status
                subscription.status = args.status
                changes.append(f"Status: {old_status} -> {args.status}")

            # Update payment method if specified
            if args.payment_method:
                try:
                    ValidationRegistry.validate_payment_method(args.payment_method)
                    old_method = subscription.payment_method or "None"
                    subscription.payment_method = args.payment_method
                    changes.append(f"Payment Method: {old_method} -> {args.payment_method}")
                except ValueError as e:
                    raise ValueError(str(e))

            # Update tags if specified
            if args.add_tags:
                try:
                    # Validate new tags
                    for tag in args.add_tags:
                        ValidationRegistry.validate_tag(tag)

                    # Add new tags (avoid duplicates)
                    old_tags = set(subscription.tags)
                    for tag in args.add_tags:
                        if tag not in old_tags:
                            subscription.tags.append(tag)

                    if set(subscription.tags) != old_tags:
                        changes.append(f"Added tags: {', '.join(set(subscription.tags) - old_tags)}")
                except ValueError as e:
                    raise ValueError(str(e))

            # Update status if specified
            if args.set_status:
                old_status = subscription.status
                subscription.status = args.set_status
                changes.append(f"Status: {old_status} → {args.set_status}")

            # Update payment method if specified
            if args.set_payment_method:
                try:
                    ValidationRegistry.validate_payment_method(args.set_payment_method)
                    old_method = subscription.payment_method or "None"
                    subscription.payment_method = args.set_payment_method
                    changes.append(f"Payment Method: {old_method} → {args.set_payment_method}")
                except ValueError as e:
                    raise ValueError(str(e))

            # Update tags if specified
            if args.set_tags:
                try:
                    # Validate new tags
                    for tag in args.set_tags:
                        ValidationRegistry.validate_tag(tag)

                    old_tags_str = ", ".join(subscription.tags) if subscription.tags else "None"
                    new_tags_str = ", ".join(args.set_tags)

                    # Replace all existing tags with new ones
                    subscription.tags = args.set_tags
                    changes.append(f"Tags: [{old_tags_str}] → [{new_tags_str}]")
                except ValueError as e:
                    raise ValueError(str(e))

            if args.remove_tags:
                old_tags = set(subscription.tags)
                subscription.tags = [tag for tag in subscription.tags if tag not in args.remove_tags]
                if set(subscription.tags) != old_tags:
                    changes.append(f"Removed tags: {', '.join(old_tags - set(subscription.tags))}")

            # Update the subscription in the database
            if changes:
                self._update_subscription(subscription)
                print(f"Successfully updated subscription: {subscription.name} (ID: {subscription.id})")
                for change in changes:
                    print(f"- {change}")
            else:
                print("No changes were made to the subscription.")

            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return 1

    def _get_subscription(self, subscription_id):
        """Get a subscription by ID."""
        # This is a stub - in a real implementation, this would query the database
        db_manager = DatabaseManager()
        subscriptions = db_manager.get_all_subscriptions()
        for sub in subscriptions:
            if sub.id == subscription_id:
                return sub
        return None

    def _update_subscription(self, subscription):
        """Update a subscription in the database."""
        # This is a stub - in a real implementation, this would update the database
        # For now, we'll assume the manager has an update_subscription method
        db_manager = DatabaseManager()
        db_manager.update_subscription(subscription)