from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from renewalradar.registry import register_command
from renewalradar.utils.validators import ValidationRegistry


@register_command
class ListUsageCommand(Command):
    """Command for listing tag and payment method usage."""

    name = "list-usage"
    description = "List tags and payment methods in use"

    @classmethod
    def register_arguments(self, parser):
        # Flags for what to list
        parser.add_argument(
            "--list-tags",
            action="store_true",
            help="List all distinct tags currently in use"
        )

        parser.add_argument(
            "--list-payment-methods",
            action="store_true",
            help="List all distinct payment methods currently in use"
        )

        # Filtering options
        parser.add_argument(
            "--status",
            nargs="*",
            choices=Subscription.VALID_STATUSES,
            help="Filter by subscription status (multiple values allowed)"
        )

        parser.add_argument(
            "--currency",
            help="Filter by subscription currency"
        )

        parser.add_argument(
            "--tag",
            action="append",
            dest="tags",
            help="Filter by specific tag(s). Can be used multiple times."
        )

        parser.add_argument(
            "--payment-method",
            action="append",
            dest="payment_methods",
            help="Filter by specific payment method(s). Can be used multiple times."
        )

        parser.add_argument(
            "--unused-tags",
            action="store_true",
            help="List tags from the global registry that are not currently in use"
        )

        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        """Execute list-usage command."""
        try:
            # Initialize database if it doesn't exist

            # If neither flag is specified, show both
            if not args.list_tags and not args.list_payment_methods:
                args.list_tags = True
                args.list_payment_methods = True

            # Build filters based on provided arguments
            filters = {}

            if args.status:
                filters["status"] = args.status

            if args.payment_methods:
                filters["payment_methods"] = args.payment_methods

            if args.tags:
                filters["tag"] = args.tags

            if args.currency:
                filters["currency"] = args.currency

            # Show tag usage if requested
            if args.list_tags:
                self._list_tag_usage(filters)

            # Show unused tags if requested
            if args.unused_tags:
                # Add a blank line if both tags and unused tags are listed for better readability
                if args.list_tags:
                    print()
                self._list_unused_tags(filters)

            # Show payment method usage if requested
            if args.list_payment_methods:
                # Add a blank line if both are listed for better readability
                if args.list_tags:
                    print()
                self._list_payment_method_usage(filters)

            # Display filter information if filters were applied
            self._display_filter_info(args, filters)

            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return 1

    def _list_tag_usage(self, filters):
        """List all distinct tags in use with usage count."""
        db_manager = DatabaseManager()
        tag_counts = db_manager.get_tag_usage(filters)

        if not tag_counts:
            print("No tags in use.")
            return

        print("Tags in use:")

        # Determine the longest tag name for proper alignment
        max_length = max(len(tag) for tag in tag_counts.keys()) if tag_counts else 0

        # Print sorted by count (descending)
        for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"{tag:<{max_length}} – {count}")

    def _list_payment_method_usage(self, filters):
        """List all distinct payment methods in use with usage count."""
        db_manager = DatabaseManager()
        method_counts = db_manager.get_payment_method_usage(filters)

        if not method_counts:
            print("No payment methods in use.")
            return

        print("Payment Methods:")

        # Determine the longest payment method name for proper alignment
        max_length = max(len(method) for method in method_counts.keys()) if method_counts else 0

        # Print sorted by count (descending)
        for method, count in sorted(method_counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"{method:<{max_length}} – {count}")

    def _list_unused_tags(self, filters):
        """List tags from the global registry that are not currently in use."""
        # Get all valid tags from the registry
        valid_tags = set(ValidationRegistry.VALID_TAGS)

        # Get tags that are currently in use based on filters
        used_tags = set(self.db_manager.get_tag_usage(filters).keys())

        # Find tags that are in the registry but not in use
        unused_tags = valid_tags - used_tags

        # Display results
        print("Unused Tags:")
        if unused_tags:
            # Sort alphabetically for consistent output
            for tag in sorted(unused_tags):
                print(f"- {tag}")
        else:
            print("All tags are currently in use.")

    def _display_filter_info(self, args, filters):
        """Display information about active filters."""
        if not filters:
            return

        filter_info = []

        if args.status:
            filter_info.append(f"status=[{', '.join(args.status)}]")

        if args.payment_methods:
            filter_info.append(f"payment_methods=[{', '.join(args.payment_methods)}]")

        if args.tags:
            filter_info.append(f"tags=[{', '.join(args.tags)}]")

        if args.currency:
            filter_info.append(f"currency='{args.currency}'")

        if filter_info:
            print(f"\nFilters applied: {' AND '.join(filter_info)}")