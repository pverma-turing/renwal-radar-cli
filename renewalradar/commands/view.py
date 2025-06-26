"""
ViewCommand implementation for RenewalRadar subscription manager.
Handles displaying subscriptions from the command line.
"""

import datetime
import shutil

from colorama import init, Fore, Style
from tabulate import tabulate

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from renewalradar.registry import register_command
from renewalradar.utils.date_utils import days_until_renewal, parse_date

# Initialize colorama for cross-platform color support
init()
@register_command
class ViewCommand(Command):
    """Command to view subscriptions with enhanced formatting and filtering."""

    name = 'view'
    description = 'View all subscriptions'

    # Color constants for better readability
    COLORS = {
        'OVERDUE': Fore.RED,
        'DUE_SOON': Fore.YELLOW,
        'NORMAL': Fore.WHITE,
        'TRIAL': Fore.CYAN,
        'HEADER': Fore.CYAN + Style.BRIGHT,
        'NOTES': Fore.GREEN,
        'PARENT': Fore.MAGENTA,
        'TREE_LINE': Fore.BLUE,
        'RESET': Style.RESET_ALL,
    }

    # Days thresholds for highlighting
    DUE_SOON_THRESHOLD = 7  # Days

    # Symbols for tree display
    INDENT_SYMBOL = "  ↳ "  # For tabular view
    TREE_BRANCH = "↳ "  # For dependency tree view

    # Sample exchange rates (base: USD)
    # Format: {'CURRENCY_CODE': rate_against_USD}
    EXCHANGE_RATES = {
        'USD': 1.00,
        'EUR': 0.85,
        'GBP': 0.74,
        'JPY': 113.50,
        'CAD': 1.25,
        'AUD': 1.35,
        'CHF': 0.92,
        'INR': 74.50,
        'CNY': 6.39,
        'HKD': 7.78,
        # Add more currencies as needed
    }

    @classmethod
    def register_arguments(cls, parser):
        """Register command-specific arguments."""
        parser.add_argument(
            "--sort",
            choices=["name", "cost", "billing_cycle", "renewal_date", "status"],
            help="Sort subscriptions by a specific field"
        )

        parser.add_argument(
            "--currency",
            help="Filter subscriptions by currency"
        )

        parser.add_argument(
            "--limit",
            type=int,
            help="Limit the number of subscriptions displayed"
        )
        parser.add_argument(
            "--status",
            nargs="*",
            choices=Subscription.VALID_STATUSES,
            help="Filter subscriptions by status (multiple values allowed)"
        )

        parser.add_argument(
            "--expiring-days",
            type=int,
            default=7,
            help="Days threshold for classifying active/trial subscriptions as expiring (default: 7)"
        )

        # Display format options - make these mutually exclusive
        display_group = parser.add_mutually_exclusive_group()

        display_group.add_argument(
            '--flat',
            action='store_true',
            help='Display subscriptions in a flat list (no parent-child indentation)'
        )

        display_group.add_argument(
            '--show-dependency-tree',
            action='store_true',
            help='Display subscriptions as a parent-child dependency tree'
        )

    def execute(self, args):
        """Execute view command."""
        try:
            db_manager = DatabaseManager()
            # Initialize database if it doesn't exist

            # Build filters dictionary based on provided arguments
            filters = {}

            if args.currency:
                filters["currency"] = args.currency

            if args.status:
                filters["status"] = args.status

            # Get subscriptions with filters and sort
            subscriptions = db_manager.get_filtered_subscriptions(
                filters=filters,
                sort_by=args.sort
            )

            # Apply limit if specified
            if args.limit and args.limit > 0 and len(subscriptions) > args.limit:
                subscriptions = subscriptions[:args.limit]

            if not subscriptions:
                print("No subscriptions found.")
                return 0

            # Process subscriptions to classify expiring ones
            current_date = datetime.datetime.now().date()
            expiring_threshold = current_date + datetime.timedelta(days=args.expiring_days)

            # Track how many subscriptions were classified as expiring
            expiring_count = 0

            # Process each subscription to check for expiring status
            for subscription in subscriptions:
                # Add a display_status attribute for showing in the view
                # This doesn't change the actual status stored in the database
                subscription.display_status = subscription.status

                # Check if the subscription should be marked as expiring
                if (subscription.status in ["active", "trial"] and
                        subscription.renewal_date and
                        self._is_date_within_range(subscription.renewal_date, current_date, expiring_threshold)):
                    subscription.display_status = "expiring"
                    expiring_count += 1

            # Prepare table data
            table_data = []
            for sub in subscriptions:
                # Use display_status instead of status
                status_display = sub.display_status
                # Add days until renewal if the status is expiring
                if status_display == "expiring" and sub.renewal_date:
                    try:
                        renewal_date = datetime.datetime.strptime(sub.renewal_date, "%Y-%m-%d").date()
                        days_until_renewal = (renewal_date - current_date).days
                        status_display = f"expiring ({days_until_renewal} days)"
                    except (ValueError, TypeError):
                        # In case of invalid date format
                        pass

                table_data.append([
                    sub.name,
                    f"{sub.currency} {sub.cost:.2f}",
                    sub.billing_cycle,
                    sub.start_date or "N/A",
                    sub.renewal_date or "N/A",
                    sub.payment_method or "N/A",
                    status_display
                ])

            # Define headers
            headers = ["Name", "Cost", "Billing Cycle", "Start Date", "Renewal Date", "Payment Method", "Status"]

            # Display table
            print(tabulate(table_data, headers=headers, tablefmt="grid"))

            # Display summary
            total_cost = sum(sub.cost for sub in subscriptions)
            # annual_cost = sum(sub.annual_cost for sub in subscriptions)

            print(f"\nTotal Monthly Cost: {subscriptions[0].currency} {total_cost:.2f}")
            # print(f"Total Annual Cost: {subscriptions[0].currency} {annual_cost:.2f}")

            # Show dependency tree if requested
            if args.show_dependency_tree:
                self._display_dependency_tree(subscriptions)

            # Display filter information if filters were applied
            filter_info = []
            if args.currency:
                filter_info.append(f"currency='{args.currency}'")
            if args.status:
                filter_info.append(f"status=[{', '.join(args.status)}]")

            # Add expiring days information if subscriptions were classified as expiring
            if expiring_count > 0:
                filter_info.append(f"expiring-days={args.expiring_days}")
                print(f"\nNOTE: {expiring_count} subscription(s) automatically classified as expiring " +
                      f"(renewal within {args.expiring_days} days)")

            if filter_info:
                print(f"\nFilters applied: {', '.join(filter_info)}")

            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An error occurred: {e}")
            return 1

    def _display_dependency_tree(self, subscriptions):
        """Display dependency tree for linked subscriptions."""
        print("\nDependency Tree:")

        # This is a simplified implementation - in a real application,
        # this would display an actual dependency hierarchy
        for sub in subscriptions:
            # Use display_status for consistency with table view
            print(f"- {sub.name} ({sub.display_status})")

        print("(Full dependency tree functionality not implemented in this example)")

    def _is_date_within_range(self, date_str, start_date, end_date):
        """Check if a date string is within a given date range."""
        try:
            # Parse the date string (assuming YYYY-MM-DD format)
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

            # Check if date is in range [start_date, end_date]
            return start_date <= date_obj <= end_date
        except (ValueError, TypeError):
            # Return False if date is invalid
            return False

    def _format_date_for_display(self, date_str):
        """Format a date string for display, with days until or since current date."""
        if not date_str:
            return "N/A"

        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            current_date = datetime.datetime.now().date()
            days_diff = (date_obj - current_date).days

            if days_diff > 0:
                return f"{date_str} (in {days_diff} days)"
            elif days_diff < 0:
                return f"{date_str} ({abs(days_diff)} days ago)"
            else:
                return f"{date_str} (today)"
        except ValueError:
            return date_str