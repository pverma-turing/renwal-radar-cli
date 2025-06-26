"""
ViewCommand implementation for RenewalRadar subscription manager.
Handles displaying subscriptions from the command line.
"""

import datetime
import shutil
from collections import defaultdict

from colorama import init, Fore, Style
from tabulate import tabulate
from datetime import datetime as dt
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
    },
    # Currency symbols for display
    CURRENCY_SYMBOLS = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "INR": "₹",
        "JPY": "¥",
        "CAD": "C$",
        "AUD": "A$",
        "CNY": "¥"
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

        parser.add_argument(
            "--payment-method",
            action="append",
            dest="payment_methods",
            help="Filter subscriptions by payment method. Can be used multiple times for multiple payment methods."
        )

        parser.add_argument(
            "--tag",
            action="append",
            dest="tags",
            help="Filter subscriptions by tag. Can be used multiple times for multiple tags (OR filter)."
        )

        parser.add_argument(
            "--total-spend",
            action="store_true",
            help="Show total spending across subscriptions, grouped by currency"
        )

        parser.add_argument(
            "--by-status",
            action="store_true",
            help="When used with --total-spend, show spending breakdown by subscription status"
        )

        parser.add_argument(
            "--trial-warning",
            action="store_true",
            help="Flag trial subscriptions with renewal dates within the expiring threshold"
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
            # Initialize database if it doesn't exist
            db_manager = DatabaseManager()

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

            # Get subscriptions
            subscriptions = db_manager.get_filtered_subscriptions(filters, args.sort)

            # Apply limit if specified
            if args.limit and args.limit > 0 and len(subscriptions) > args.limit:
                subscriptions = subscriptions[:args.limit]

            if not subscriptions:
                print("No subscriptions found.")
                return 0

            # Process subscriptions to classify expiring ones
            current_date = dt.now().date()
            expiring_threshold = current_date + datetime.timedelta(days=args.expiring_days)

            # Track how many subscriptions were classified as expiring
            expiring_count = 0

            # Initialize counters for status summary
            status_counts = {status: 0 for status in Subscription.VALID_STATUSES}
            status_counts["expiring"] = 0  # Add expiring which might not be in database statuses

            # Track upcoming renewals
            upcoming_renewals = 0

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

                    # Count this as an upcoming renewal
                    upcoming_renewals += 1

                # Count by display status for summary
                if subscription.display_status in status_counts:
                    status_counts[subscription.display_status] += 1

            # Group by status if requested
            if args.by_status:
                self._display_by_status(subscriptions, current_date)
                return 0

            # Prepare table data
            table_data = []
            for sub in subscriptions:
                # Use display_status instead of status
                status_display = sub.display_status
                # Add days until renewal if the status is expiring
                if status_display == "expiring" and sub.renewal_date:
                    try:
                        renewal_date = dt.strptime(sub.renewal_date, "%Y-%m-%d").date()
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
                    status_display,
                    ", ".join(sub.tags) if sub.tags else "N/A"
                ])

            # Define headers
            headers = ["Name", "Cost", "Billing Cycle", "Start Date", "Renewal Date", "Payment Method", "Status",
                       "Tags"]

            # Display table
            print(tabulate(table_data, headers=headers, tablefmt="grid"))

            # Display summary
            total_cost = sum(sub.cost for sub in subscriptions)
            annual_cost = sum(sub.annual_cost for sub in subscriptions)

            print(f"\nTotal Monthly Cost: {subscriptions[0].currency} {total_cost:.2f}")
            print(f"Total Annual Cost: {subscriptions[0].currency} {annual_cost:.2f}")

            # Show total spend summary if requested
            if args.total_spend:
                self._display_total_spend(subscriptions, args.total_spend)

            # Show dependency tree if requested
            if args.show_dependency_tree:
                self._display_dependency_tree(subscriptions)

            # Display status summary
            self._display_status_summary(status_counts, upcoming_renewals, args.expiring_days)

            # Display filter information if filters were applied
            filter_info = []
            if args.payment_methods:
                filter_info.append(f"payment_methods=[{', '.join(args.payment_methods)}]")
            if args.status:
                filter_info.append(f"status=[{', '.join(args.status)}]")
            if args.tags:
                filter_info.append(f"tags=[{', '.join(args.tags)}]")
            if args.currency:
                filter_info.append(f"currency='{args.currency}'")

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

    def _display_status_summary(self, status_counts, upcoming_renewals, expiring_days):
        """Display a summary of subscription statuses and upcoming renewals."""
        # Build the status summary string, only include non-zero counts
        status_parts = []
        for status in ["active", "trial", "expiring", "cancelled"]:  # Order matters for readability
            if status_counts[status] > 0:
                status_parts.append(f"{status_counts[status]} {status}")

        # Only display if we have any subscriptions
        if status_parts:
            status_summary = ", ".join(status_parts)
            print(f"\nSummary: {status_summary}")
            print(f"Upcoming Renewals: {upcoming_renewals} in next {expiring_days} days")

    def _display_by_status(self, subscriptions, current_date):
        """Display subscriptions grouped by status."""
        # Group subscriptions by display_status
        status_groups = {}
        for sub in subscriptions:
            status = sub.display_status
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append(sub)

        # Display each group
        for status in ["active", "trial", "expiring", "canceled"]:
            if status in status_groups and status_groups[status]:
                print(f"\n{status.upper()} SUBSCRIPTIONS:")

                # Prepare table data for this status
                table_data = []
                for sub in status_groups[status]:
                    # Special display for expiring status
                    status_display = status
                    if status == "expiring" and sub.renewal_date:
                        try:
                            renewal_date = dt.strptime(sub.renewal_date, "%Y-%m-%d").date()
                            days_until_renewal = (renewal_date - current_date).days
                            status_display = f"expiring ({days_until_renewal} days)"
                        except (ValueError, TypeError):
                            pass

                    table_data.append([
                        sub.name,
                        f"{sub.currency} {sub.cost:.2f}",
                        sub.billing_cycle,
                        sub.renewal_date or "N/A",
                        sub.payment_method or "N/A",
                        ", ".join(sub.tags) if sub.tags else "N/A"
                    ])

                headers = ["Name", "Cost", "Billing Cycle", "Renewal Date", "Payment Method", "Tags"]
                print(tabulate(table_data, headers=headers, tablefmt="grid"))

                # Display cost summary for this group
                group_cost = sum(sub.cost for sub in status_groups[status])
                print(f"Total {status.capitalize()} Monthly Cost: {subscriptions[0].currency} {group_cost:.2f}")

    def _display_total_spend(self, subscriptions, period):
        """Display total spend breakdown by various dimensions."""
        print(f"\nTotal Spend Analysis ({period.capitalize()}):")

        # Determine the multiplier for the period
        if period == "monthly":
            title = "Monthly"
            # Monthly cost is already the base
            get_cost = lambda sub: sub.cost
        else:  # annual
            title = "Annual"
            get_cost = lambda sub: sub.annual_cost

        # Analyze by payment method
        payment_methods = {}
        for sub in subscriptions:
            method = sub.payment_method or "Unknown"
            if method not in payment_methods:
                payment_methods[method] = 0
            payment_methods[method] += get_cost(sub)

        # Display by payment method
        if payment_methods:
            print(f"\n{title} Spend by Payment Method:")
            method_data = [[method, f"{subscriptions[0].currency} {cost:.2f}"]
                           for method, cost in sorted(payment_methods.items(), key=lambda x: x[1], reverse=True)]
            print(tabulate(method_data, headers=["Payment Method", "Cost"], tablefmt="simple"))

        # Analyze by tag (note: subscriptions can have multiple tags)
        tag_costs = {}
        for sub in subscriptions:
            if not sub.tags:
                tag = "Untagged"
                if tag not in tag_costs:
                    tag_costs[tag] = 0
                tag_costs[tag] += get_cost(sub)
            else:
                for tag in sub.tags:
                    if tag not in tag_costs:
                        tag_costs[tag] = 0
                    tag_costs[tag] += get_cost(sub)

        # Display by tag
        if tag_costs:
            print(f"\n{title} Spend by Tag:")
            tag_data = [[tag, f"{subscriptions[0].currency} {cost:.2f}"]
                        for tag, cost in sorted(tag_costs.items(), key=lambda x: x[1], reverse=True)]
            print(tabulate(tag_data, headers=["Tag", "Cost"], tablefmt="simple"))

    def _display_spend_by_status(self, spend_by_status_currency, target_currency=None):
        """Display spending breakdown by subscription status."""
        print("\nSpending by Status:")

        # Order of statuses for display
        status_order = ["active", "trial", "expiring", "canceled"]

        if target_currency and target_currency in self.EXCHANGE_RATES:
            # Convert all amounts to target currency and sum by status
            spend_by_status = defaultdict(float)

            for status, currencies in spend_by_status_currency.items():
                for currency, amount in currencies.items():
                    if currency in self.EXCHANGE_RATES:
                        # Convert to USD, then to target currency
                        amount_in_usd = amount * self.EXCHANGE_RATES[currency]
                        amount_in_target = amount_in_usd / self.EXCHANGE_RATES[target_currency]
                        spend_by_status[status] += amount_in_target

            # Display spending by status in target currency
            for status in status_order:
                if status in spend_by_status and spend_by_status[status] > 0:
                    print(f"  {status}: {self._get_currency_symbol(target_currency)}{spend_by_status[status]:.2f}")

        else:
            # Show breakdown by status and currency
            for status in status_order:
                if status in spend_by_status_currency and spend_by_status_currency[status]:
                    currencies_list = []
                    for currency, amount in sorted(spend_by_status_currency[status].items()):
                        if amount > 0:
                            symbol = self._get_currency_symbol(currency)
                            currencies_list.append(f"{symbol}{amount:.2f} ({currency})")

                    if currencies_list:
                        print(f"  {status}: {', '.join(currencies_list)}")

    def _display_dependency_tree(self, subscriptions):
        """Display dependency tree for linked subscriptions."""
        print("\nDependency Tree:")

        # This is a simplified implementation - in a real application,
        # this would display an actual dependency hierarchy
        for sub in subscriptions:
            # Use display_status for consistency with table view
            status_display = sub.display_status

            # Add trial warning if applicable
            trial_warning = ""
            if hasattr(sub, 'trial_warning') and sub.trial_warning:
                trial_warning = f" {Fore.YELLOW}⚠️ TRIAL ENDING SOON{Style.RESET_ALL}"

            print(f"- {sub.name} ({status_display}{trial_warning})")

        print("(Full dependency tree functionality not implemented in this example)")

    def _is_date_within_range(self, date_str, start_date, end_date):
        """Check if a date string is within a given date range."""
        try:
            # Parse the date string (assuming YYYY-MM-DD format)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()

            # Check if date is in range [start_date, end_date]
            return start_date <= date_obj <= end_date
        except (ValueError, TypeError):
            # Return False if date is invalid
            return False

    def _get_currency_symbol(self, currency_code):
        """Get the symbol for a currency code."""
        return self.CURRENCY_SYMBOLS.get(currency_code, currency_code)
