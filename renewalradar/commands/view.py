"""
ViewCommand implementation for RenewalRadar subscription manager.
Handles displaying subscriptions from the command line.
"""

import datetime
import shutil

from colorama import init, Fore, Style

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
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
        'HEADER': Fore.CYAN + Style.BRIGHT,
        'RESET': Style.RESET_ALL,
    }

    # Days thresholds for highlighting
    DUE_SOON_THRESHOLD = 7  # Days

    @classmethod
    def register_arguments(cls, parser):
        """Register command-specific arguments."""
        parser.add_argument(
            '--sort',
            choices=['name', 'cost', 'renewal_date', 'billing_cycle', 'days'],
            help='Sort subscriptions by the specified field'
        )

        parser.add_argument(
            '--status',
            choices=['all', 'upcoming', 'overdue'],
            default='all',
            help='Filter subscriptions by status: all (default), upcoming (next 30 days), or overdue'
        )

    def execute(self, args):
        """Execute the view command with enhanced output and filtering."""
        try:
            db_manager = DatabaseManager()
            try:
                # Get all subscriptions first
                subscriptions = db_manager.get_all_subscriptions()

                if not subscriptions:
                    print("No subscriptions found.")
                    return 0

                # Enhance subscriptions with calculated fields
                enhanced_subscriptions = self._enhance_subscriptions(subscriptions)

                # Apply status filtering
                filtered_subscriptions = self._filter_by_status(enhanced_subscriptions, args.status)

                if not filtered_subscriptions:
                    status_message = "No subscriptions found"
                    if args.status != 'all':
                        status_message += f" with status: {args.status}"
                    print(status_message + ".")
                    return 0

                # Apply sorting (if specified)
                sorted_subscriptions = self._sort_subscriptions(filtered_subscriptions, args.sort)

                # Display the subscriptions in a nicely formatted table
                self._display_subscriptions(sorted_subscriptions)

                # Display summary information
                self._display_summary(sorted_subscriptions, status=args.status)
                return 0
            finally:
                db_manager.close()

        except Exception as e:
            print(f"An error occurred: {e}")
            return 1

    def _enhance_subscriptions(self, subscriptions):
        """
        Enhance subscriptions with additional calculated fields.

        Args:
            subscriptions (list): List of subscription dictionaries

        Returns:
            list: Enhanced subscription dictionaries
        """
        today = datetime.datetime.now().date()
        enhanced = []

        for sub in subscriptions:
            # Calculate days until renewal
            days = days_until_renewal(sub["renewal_date"])

            # Determine status for coloring
            if days < 0:
                status = "OVERDUE"
            elif days <= self.DUE_SOON_THRESHOLD:
                status = "DUE_SOON"
            else:
                status = "NORMAL"

            # Create enhanced subscription with additional fields
            enhanced_sub = {**sub}  # Create a copy
            enhanced_sub["days_until_renewal"] = days
            enhanced_sub["status"] = status

            # Add parsed dates for easier handling
            enhanced_sub["start_date_obj"] = parse_date(sub["start_date"]).date()
            enhanced_sub["renewal_date_obj"] = parse_date(sub["renewal_date"]).date()

            enhanced.append(enhanced_sub)

        return enhanced

    def _filter_by_status(self, subscriptions, status):
        """
        Filter subscriptions by specified status.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            status (str): One of 'all', 'upcoming', 'overdue'

        Returns:
            list: Filtered subscription dictionaries
        """
        if status == 'all':
            return subscriptions

        today = datetime.datetime.now().date()
        thirty_days_from_now = today + datetime.timedelta(days=30)

        if status == 'upcoming':
            return [
                sub for sub in subscriptions
                if today <= sub["renewal_date_obj"] <= thirty_days_from_now
            ]

        if status == 'overdue':
            return [
                sub for sub in subscriptions
                if sub["renewal_date_obj"] < today
            ]

        return subscriptions  # Fallback

    def _sort_subscriptions(self, subscriptions, sort_by):
        """
        Sort subscriptions by the specified field.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            sort_by (str): Field to sort by

        Returns:
            list: Sorted subscription dictionaries
        """
        if not sort_by:
            # Default sort by name if no sort field specified
            return sorted(subscriptions, key=lambda s: s["name"].lower())

        # Map sort fields to their key functions
        sort_keys = {
            'name': lambda s: s["name"].lower(),
            'cost': lambda s: s["cost"],
            'renewal_date': lambda s: s["renewal_date_obj"],
            'billing_cycle': lambda s: s["billing_cycle"],
            'days': lambda s: s["days_until_renewal"]
        }

        key_function = sort_keys.get(sort_by, lambda s: s["name"].lower())
        return sorted(subscriptions, key=key_function)

    def _get_terminal_width(self):
        """
        Get the terminal width for display formatting.

        Returns:
            int: Terminal width or default width
        """
        terminal_size = shutil.get_terminal_size((80, 20))  # Default to 80x20
        return terminal_size.columns

    def _truncate_text(self, text, max_width):
        """
        Truncate text to fit within max_width.

        Args:
            text (str): Text to truncate
            max_width (int): Maximum width

        Returns:
            str: Truncated text
        """
        if len(text) > max_width:
            return text[:max_width - 3] + "..."
        return text

    def _calculate_column_widths(self, subscriptions):
        """
        Calculate optimal column widths based on data and terminal width.

        Args:
            subscriptions (list): List of subscriptions

        Returns:
            dict: Column width configuration
        """
        # Get terminal width
        terminal_width = self._get_terminal_width()

        # Define minimum column widths
        min_widths = {
            "name": 10,
            "cost": 8,
            "currency": 3,
            "cycle": 6,
            "start_date": 10,
            "renewal_date": 10,
            "payment": 8,
            "days": 5
        }

        # Calculate max content lengths
        max_widths = {
            "name": max(min_widths["name"], max([len(s["name"]) for s in subscriptions])),
            "cost": max(min_widths["cost"], max([len(f"{s['cost']:.2f}") for s in subscriptions])),
            "currency": max(min_widths["currency"], max([len(s["currency"]) for s in subscriptions])),
            "cycle": max(min_widths["cycle"], max([len(s["billing_cycle"]) for s in subscriptions])),
            "start_date": min_widths["start_date"],  # Fixed width for dates
            "renewal_date": min_widths["renewal_date"],  # Fixed width for dates
            "payment": max(min_widths["payment"], max([len(s["payment_method"] or "N/A") for s in subscriptions])),
            "days": min_widths["days"]  # Fixed width for days
        }

        # Calculate total width needed
        spacers = len(min_widths) + 1  # +1 for edge
        total_width = sum(max_widths.values()) + spacers

        # Adjust widths if terminal is too narrow
        if total_width > terminal_width:
            # Define priorities for shrinking columns (higher = less important)
            priorities = {
                "name": 3,
                "payment": 2,
                "cost": 5,
                "cycle": 4,
                "currency": 4,
                "start_date": 5,
                "renewal_date": 5,
                "days": 6
            }

            # Sort columns by priority
            columns_by_priority = sorted(max_widths.keys(), key=lambda k: priorities.get(k, 0))

            # Reduce widths until we fit
            excess_width = total_width - terminal_width
            for col in columns_by_priority:
                if excess_width <= 0:
                    break

                reducible = max(0, max_widths[col] - min_widths[col])
                reduction = min(reducible, excess_width)
                max_widths[col] -= reduction
                excess_width -= reduction

        return max_widths

    def _display_subscriptions(self, subscriptions):
        """
        Display subscriptions in a nicely formatted table with color highlighting.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
        """
        if not subscriptions:
            return

        # Calculate optimal column widths
        widths = self._calculate_column_widths(subscriptions)

        # Print header
        header = (
            f"{self.COLORS['HEADER']}{'NAME':<{widths['name']}} "
            f"{'COST':<{widths['cost']}} "
            f"{'CUR':<{widths['currency']}} "
            f"{'CYCLE':<{widths['cycle']}} "
            f"{'START':<{widths['start_date']}} "
            f"{'RENEWAL':<{widths['renewal_date']}} "
            f"{'PAYMENT':<{widths['payment']}} "
            f"{'DAYS':<{widths['days']}}{self.COLORS['RESET']}"
        )
        print("\n" + header)
        print("-" * len(header.replace(self.COLORS['HEADER'], '').replace(self.COLORS['RESET'], '')))

        # Print each subscription
        for sub in subscriptions:
            # Get the appropriate color based on status
            color = self.COLORS[sub["status"]]

            # Get days string with sign for overdue
            days = sub["days_until_renewal"]
            if days < 0:
                days_str = f"{days}"  # Negative number for overdue
            else:
                days_str = f"{days}"

            # Format each field with truncation if needed
            name = self._truncate_text(sub['name'], widths['name'])
            payment = self._truncate_text(sub['payment_method'] or 'N/A', widths['payment'])

            # Print the formatted row with color
            row = (
                f"{color}{name:<{widths['name']}} "
                f"{sub['cost']:<{widths['cost']}.2f} "
                f"{sub['currency']:<{widths['currency']}} "
                f"{sub['billing_cycle']:<{widths['cycle']}} "
                f"{sub['start_date']:<{widths['start_date']}} "
                f"{sub['renewal_date']:<{widths['renewal_date']}} "
                f"{payment:<{widths['payment']}} "
                f"{days_str:<{widths['days']}}{self.COLORS['RESET']}"
            )
            print(row)

    def _display_summary(self, subscriptions, status='all'):
        """
        Display summary information about subscriptions.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            status (str): Current status filter
        """
        # Count subscriptions
        total_count = len(subscriptions)

        # Calculate total monthly and yearly costs by currency
        monthly_totals = {}
        yearly_totals = {}

        for sub in subscriptions:
            cost = sub["cost"]
            currency = sub["currency"]

            # Initialize totals for this currency if not exist
            if currency not in monthly_totals:
                monthly_totals[currency] = 0
                yearly_totals[currency] = 0

            if sub["billing_cycle"] == "monthly":
                monthly_totals[currency] += cost
                yearly_totals[currency] += cost * 12
            elif sub["billing_cycle"] == "yearly":
                monthly_totals[currency] += cost / 12
                yearly_totals[currency] += cost

        # Count status breakdown
        overdue_count = sum(1 for sub in subscriptions if sub["days_until_renewal"] < 0)
        due_soon_count = sum(1 for sub in subscriptions if 0 <= sub["days_until_renewal"] <= self.DUE_SOON_THRESHOLD)

        # Print summary
        status_desc = {'all': 'All subscriptions', 'upcoming': 'Upcoming renewals', 'overdue': 'Overdue subscriptions'}

        print(f"\n{self.COLORS['HEADER']}SUMMARY: {status_desc.get(status, 'Subscriptions')}{self.COLORS['RESET']}")
        print(f"Total subscriptions: {total_count}")

        # Show status breakdown only if showing all subscriptions
        if status == 'all':
            print(f"{self.COLORS['OVERDUE']}Overdue: {overdue_count}{self.COLORS['RESET']}")
            print(
                f"{self.COLORS['DUE_SOON']}Due within {self.DUE_SOON_THRESHOLD} days: {due_soon_count}{self.COLORS['RESET']}")

        # Show cost total by currency
        print("\nMonthly costs:")
        for currency, total in monthly_totals.items():
            print(f"  {currency}: {total:.2f}")

        print("\nYearly costs:")
        for currency, total in yearly_totals.items():
            print(f"  {currency}: {total:.2f}")

        # Show most imminent renewals if there are any
        upcoming_renewals = [
            (sub["name"], sub["renewal_date"], sub["days_until_renewal"])
            for sub in subscriptions
            if -30 <= sub["days_until_renewal"] <= 30  # Show renewals within +/- 30 days
        ]

        if upcoming_renewals:
            print("\nRecent & upcoming renewals (±30 days):")
            for name, date, days in sorted(upcoming_renewals, key=lambda x: x[2]):
                if days < 0:
                    print(f"  {self.COLORS['OVERDUE']}{name}: {date} ({days} days ago - OVERDUE){self.COLORS['RESET']}")
                elif days <= self.DUE_SOON_THRESHOLD:
                    print(f"  {self.COLORS['DUE_SOON']}{name}: {date} (in {days} days){self.COLORS['RESET']}")
                else:
                    print(f"  {name}: {date} (in {days} days)")