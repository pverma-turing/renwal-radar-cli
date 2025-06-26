from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from renewalradar.registry import register_command
from renewalradar.utils.status_utils import print_status_help, VALID_STATUSES, get_status_error_message


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
            "--name",
            required=False,
            help="Name of the subscription to update"
        )

        parser.add_argument(
            "--to",
            required=False,
            choices=Subscription.VALID_STATUSES,
            dest="new_status",
            help="New status to set (active, trial, expiring, canceled)"
        )

        parser.add_argument(
            "--help-status",
            action="store_true",
            help="Show information about valid subscription statuses"
        )

        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        """Execute update-status command."""
        try:
            # Check if help-status flag is set
            if args.help_status:
                print_status_help()
                return 0

            db_manager = DatabaseManager()
            # Validate status
            if args.new_status not in VALID_STATUSES:
                print(get_status_error_message(args.new_status))
                return 1
            # Check if subscription exists
            subscription = db_manager.get_subscription_by_name(args.name)
            if not subscription:
                print(f"Error: Subscription '{args.name}' not found")
                return 1

            # Check if status is already set to the requested value
            if subscription.status == args.new_status:
                print(f"Notice: Status for '{args.name}' is already set to '{args.new_status}'")
                return 0
            # Update the subscription status
            db_manager.update_subscription_status(subscription.id, args.new_status)

            print(f"Status for '{args.name}' updated to '{args.new_status}'")
            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return 1