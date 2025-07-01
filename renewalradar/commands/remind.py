"""
File: renewalradar/commands/remind.py

This module implements the 'remind' command for RenewalRadar CLI, which
displays upcoming subscription renewals within a specified number of days.
"""

import argparse
import datetime
from typing import List, Dict, Any, Optional, Tuple

from tabulate import tabulate

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from colorama import Fore, Style

from renewalradar.registry import register_command
from renewalradar.utils.date_utils import parse_date


@register_command
class RemindCommand(Command):
    """Command for displaying upcoming subscription renewals."""
    name = "remind"
    description = "Command for displaying upcoming subscription renewals."

    # Optimization: Define sort key function separately to avoid lambda creation in hot loops
    @staticmethod
    def _renewal_sort_key(renewal: Dict[str, Any]) -> tuple:
        """
        Key function for sorting renewals by days until renewal.

        Returns a tuple for consistent sorting:
        1. Primary sort: days until renewal (ascending)
        2. Secondary sort: subscription name (ascending alphabetically)

        This ensures:
        - Subscriptions are strictly ordered by how soon they renew
        - Subscriptions with the same renewal date appear together
        - Consistent ordering when multiple subscriptions renew on the same date
        """
        return (
            renewal['days_until_renewal'],  # Primary sort: days until renewal
            renewal['name'].lower()  # Secondary sort: name (case-insensitive)
        )

    @classmethod
    def register_arguments(cls, parser) -> None:
        """Configure the argument parser for the remind command."""
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Show renewals due within this many days (default: 7)"
        )
        parser.add_argument(
            "--tag",
            action="append",
            dest="tags",
            help="Filter by tag (can be used multiple times, combined with OR logic)"
        )
        parser.add_argument(
            "--payment-method",
            action="append",
            dest="payment_methods",
            help="Filter by payment method (can be used multiple times, combined with OR logic)"
        )
        parser.add_argument(
            "--notify-preview",
            action="store_true",
            help="Preview what subscriptions would trigger notifications if alerts were enabled"
        )

    def execute(self, args: argparse.Namespace) -> None:
        """Handle the remind command."""
        # Validate input
        if args.days <= 0:
            print("Error: The number of days must be greater than zero.")
            return

        # Get current date and calculate end date once
        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=args.days)

        # Optimize: Include renewal date range in database query to reduce processing
        # This will filter subscriptions at the database level before loading them
        filters = self._build_optimized_filters(args, today, end_date)

        # Get filter description for output (only computed once)
        filter_description = self._build_filter_description(args)

        # Get filtered subscriptions directly from database with date range filter
        db_manager = DatabaseManager()
        subscriptions = db_manager.get_filtered_subscriptions(filters)

        if not subscriptions:
            if filter_description:
                print(f"No subscriptions found matching the filters: {filter_description}.")
            else:
                print("No active or trial subscriptions found.")
            return

        # Process subscriptions to prepare for display (with minimal object creation)
        upcoming_renewals, totals_by_currency = self._process_subscriptions(
            subscriptions, today, filter_description
        )

        # Display the renewals, including notification preview if requested
        self._display_renewals(
            upcoming_renewals,
            totals_by_currency,
            args.days,
            filter_description,
            notify_preview=args.notify_preview
        )

    def _display_renewals(
            self,
            upcoming_renewals: List[Dict[str, Any]],
            totals_by_currency: Dict[str, float],
            days_window: int,
            filter_description: Optional[str] = None,
            notify_preview: bool = False
    ) -> None:
        """
        Display the upcoming subscription renewals in a formatted table.

        If notify_preview is True, adds a message about which subscriptions
        would trigger notifications if alerts were enabled.

        Optimized for clean terminal output even with long field values.
        """
        # Show message for notification preview if requested
        if notify_preview:
            print("\nThe following subscriptions would trigger a notification if alerts were enabled:")

        if not upcoming_renewals:
            filter_msg = f" matching {filter_description}" if filter_description else ""
            print(f"No upcoming renewals{filter_msg} in the next {days_window} days.")
            return

        # Optimization: Pre-allocate table data array with known size
        table_data = [] if not upcoming_renewals else [None] * len(upcoming_renewals)

        # Cache color codes to avoid repetitive string creations
        RED = Fore.RED
        YELLOW = Fore.YELLOW
        CYAN = Fore.CYAN
        RESET = Style.RESET_ALL

        # Optimization: String templates for common formats
        today_text = f"{RED}Today{RESET}"
        tomorrow_text = f"{RED}Tomorrow{RESET}"
        red_days_template = f"{RED}{{}} days{RESET}"
        yellow_days_template = f"{YELLOW}{{}} days{RESET}"
        trial_text = f"{CYAN}Trial{RESET}"

        # Define column max widths for clean formatting
        max_widths = {
            'name': 30,  # Limit name to 30 characters
            'payment_method': 20,  # Limit payment method to 20 characters
            'amount': 15,  # Limit amount display to 15 characters
        }

        # Generate table rows efficiently
        for i, renewal in enumerate(upcoming_renewals):
            # Format days until renewal with colors (optimized with templates)
            days = renewal['days_until_renewal']
            if days == 0:
                days_text = today_text
            elif days == 1:
                days_text = tomorrow_text
            elif days <= 3:
                days_text = red_days_template.format(days)
            elif days <= 5:
                days_text = yellow_days_template.format(days)
            else:
                days_text = f"{days} days"

            # Format status with colors (minimized string operations)
            status = renewal['status']
            # Since status is already normalized to lowercase in _process_subscriptions
            status_text = trial_text if status == 'trial' else status.capitalize()

            # Format payment amount with currency (single string operation)
            amount = f"{renewal['amount']} {renewal['currency']}"

            # Format renewal date
            renewal_date = renewal['renewal_date'].strftime('%Y-%m-%d')

            # Truncate long fields with ellipses for better table formatting
            name = self._truncate_text(renewal['name'], max_widths['name'])
            payment_method = self._truncate_text(renewal['payment_method'], max_widths['payment_method'])
            amount = self._truncate_text(amount, max_widths['amount'])

            # Add row to table
            table_data[i] = [
                name,
                days_text,
                status_text,
                payment_method,
                amount,
                renewal_date
            ]

        # Print title
        title = f"Upcoming Subscription Renewals (Next {days_window} Days)"
        if filter_description:
            title += f" - Filtered by: {filter_description}"

        print(f"\n{title}")
        print("=" * len(title))

        # Display table with improved formatting
        headers = ["Name", "Renewal In", "Status", "Payment Method", "Amount", "Renewal Date"]

        # Use tabulate with grid format for better column alignment
        # maxcolwidths parameter ensures columns don't expand too much
        # disable_numparse prevents numeric parsing which can affect alignment
        print(tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            maxcolwidths=[
                max_widths['name'],
                None,  # No limit on "Renewal In"
                None,  # No limit on "Status"
                max_widths['payment_method'],
                max_widths['amount'],
                None  # No limit on "Renewal Date"
            ],
            disable_numparse=True
        ))

        # Print summary (using pre-calculated totals)
        print("\nTotal upcoming charges:")
        for currency, amount in totals_by_currency.items():
            print(f"  {currency}: {amount:.2f}")

        print(f"\nTip: Use 'project --months 1' to see all renewals for the next month.")

    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        """
        Truncate text to specified maximum length, adding ellipsis if needed.
        Preserves color codes if present.

        Args:
            text: The text to truncate
            max_length: Maximum allowed length

        Returns:
            Truncated text with ellipsis if needed
        """
        if not text:
            return ""

        # Check for color codes (don't count them in length)
        has_color = Fore.RED in text or Fore.YELLOW in text or Fore.CYAN in text

        if has_color:
            # For colored text, we need to handle ANSI escape codes
            # This is simplified logic, assuming our limited use of color codes
            visible_length = len(text) - len(Fore.RED) - len(Style.RESET_ALL)
            if visible_length <= max_length:
                return text

            # Find reset position to preserve color structure
            reset_pos = text.find(Style.RESET_ALL)
            if reset_pos > 0:
                color_code = text[:text.find(Style.RESET_ALL) - visible_length]
                visible_text = text[len(color_code):reset_pos]
                if len(visible_text) > max_length - 3:  # Account for ellipsis
                    return color_code + visible_text[:max_length - 3] + "..." + Style.RESET_ALL

            # Fallback for complex color structures - return as is
            return text
        else:
            # Simple case: no color codes
            if len(text) <= max_length:
                return text
            return text[:max_length - 3] + "..."

    def _build_optimized_filters(
            self,
            args: argparse.Namespace,
            today: datetime.date,
            end_date: datetime.date
    ) -> Dict[str, Any]:
        """
        Build an optimized filters dictionary that includes date range filtering.

        Optimization: Add renewal date range to database query to minimize
        the number of subscription objects that need to be processed in memory.

        Note: Trial subscriptions require special handling in _process_subscriptions,
        but we still filter at the database level using renewal_date_range.
        """
        # We'll handle detailed status filtering in the process_subscriptions method
        # to ensure case-insensitive and null status handling is consistent
        filters = {
            "status_not_canceled": True,  # Add a flag to exclude canceled at DB level if possible
            "renewal_date_range": (today, end_date)  # Filter by renewal date range
        }

        # Add tag filter if specified (no change)
        if args.tags:
            filters["tag"] = args.tags

        # Add payment method filter if specified (no change)
        if args.payment_methods:
            filters["payment_methods"] = args.payment_methods

        # Note: For trial subscriptions, we'll do additional filtering in the
        # _process_subscriptions method to check if they're still in the trial period.
        # Database query only filters on renewal_date, but we'll need to compare
        # that with the calculated trial end date for each subscription.

        return filters

    def _build_filter_description(self, args: argparse.Namespace) -> str:
        """Build a description of the filters being applied."""
        # This function remains unchanged as it's used for display purposes only
        filter_parts = []

        # Add tag filter description
        if hasattr(args, 'tags') and args.tags:
            if len(args.tags) == 1:
                filter_parts.append(f"tag '{args.tags[0]}'")
            else:
                tags_str = "', '".join(args.tags)
                filter_parts.append(f"tags ('{tags_str}')")

        # Add payment method filter description
        if hasattr(args, 'payment_methods') and args.payment_methods:
            if len(args.payment_methods) == 1:
                filter_parts.append(f"payment method '{args.payment_methods[0]}'")
            else:
                pm_str = "', '".join(args.payment_methods)
                filter_parts.append(f"payment methods ('{pm_str}')")

        # Combine filter descriptions with AND logic
        if filter_parts:
            return " AND ".join(filter_parts)
        return ""

    def _process_subscriptions(
            self,
            subscriptions: List[Subscription],
            today: datetime.date,
            filter_description: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        Process subscription data for display, optimized for performance.

        Returns both the subscription data and currency totals to avoid
        multiple iterations over the data.

        Optimizations:
        1. Uses a single pass through subscriptions for better performance
        2. Calculates currency totals during the same loop
        3. Pre-allocates collections to minimize memory overhead
        4. Combines renewal date checking and days calculation
        5. Sorts results consistently by days until renewal, then by name
        """
        # Pre-allocate collections to avoid resizing
        upcoming_renewals = []
        totals_by_currency = {}

        # Optimize: Compute frequently used values once outside the loop
        status_trial = 'trial'  # String constants used in comparisons

        # Process each subscription (should be pre-filtered by DB query)
        for subscription in subscriptions:
            # Optimization: Access all required attributes once to minimize lookups
            name = subscription.name
            payment_method = subscription.payment_method
            amount = subscription.cost
            currency = subscription.currency
            renewal_date = parse_date(subscription.renewal_date).date()
            billing_cycle = subscription.billing_cycle
            start_date = getattr(subscription, 'start_date', None)
            tags = getattr(subscription, 'tags', [])

            if start_date:
                start_date = parse_date(start_date).date()

            # Get status (handle missing status)
            status = getattr(subscription, 'status', None)

            # Skip if there's no renewal date (safety check)
            if not renewal_date:
                continue

            # Normalize status to lowercase and handle None/missing values
            status_normalized = status.lower() if status else ""

            # Skip any subscription that:
            # 1. Has a status that contains "cancel" (case insensitive)
            # 2. Has a status that isn't exactly "active" or "trial" (case insensitive)
            # 3. Has a missing or null status
            if (
                    "cancel" in status_normalized or
                    status_normalized not in ["active", "trial"]
            ):
                continue

            # Special handling for trial subscriptions
            if status_normalized == "trial":
                # Determine if the subscription is still in trial period
                if not start_date:
                    # If no start_date, we can't determine trial status - use renewal date as fallback
                    trial_end_date = renewal_date
                else:
                    # Calculate trial end date based on billing cycle
                    trial_end_date = self._calculate_trial_end_date(start_date, billing_cycle)

                # If trial has ended, check if its next paid renewal is within window
                if today > trial_end_date:
                    # The trial has already ended, but this subscription is still marked as trial
                    # Skip it unless the renewal_date (first paid period) is still within our window
                    # (The renewal_date should already be filtered by the DB query)
                    pass
                # else: trial is still active, keep it (if renewal_date is within window)

            # Calculate days until renewal
            days_until_renewal = (renewal_date - today).days

            # Create a dictionary with only the required information
            # Optimization: Only create the necessary fields
            renewal_info = {
                'name': name,
                'days_until_renewal': days_until_renewal,
                'status': status_normalized,  # Use normalized status to ensure consistent display
                'payment_method': payment_method,
                'amount': amount,
                'currency': currency,
                'renewal_date': renewal_date
            }

            # Add to result collection
            upcoming_renewals.append(renewal_info)

            # Update currency totals in the same pass
            # Optimization: Avoid float conversion multiple times
            amount_float = float(amount)
            if currency in totals_by_currency:
                totals_by_currency[currency] += amount_float
            else:
                totals_by_currency[currency] = amount_float

        # Sort renewals by days until renewal (primary) and name (secondary)
        # Optimization: Use key function without lambda for slightly better performance
        # The sort is stable, which means items with the same key will maintain relative ordering
        upcoming_renewals.sort(key=self._renewal_sort_key)

        return upcoming_renewals, totals_by_currency

    def _calculate_trial_end_date(
            self,
            start_date: datetime.date,
            billing_cycle: str
    ) -> datetime.date:
        """
        Calculate when a trial period ends based on start date and billing cycle.
        For trials, this is typically one billing period from the start date.
        """
        # Trial period is typically one billing cycle
        if billing_cycle.lower() == 'monthly':
            # Add 1 month to start_date
            month = start_date.month + 1
            year = start_date.year

            if month > 12:
                month = 1
                year += 1

            # Handle months with different lengths
            day = min(start_date.day, self._days_in_month(year, month))
            return datetime.date(year, month, day)

        elif billing_cycle.lower() == 'yearly':
            # Add 1 year to start_date
            try:
                return datetime.date(
                    start_date.year + 1,
                    start_date.month,
                    start_date.day
                )
            except ValueError:  # Handle February 29th in leap years
                return datetime.date(
                    start_date.year + 1,
                    start_date.month,
                    28  # Default to Feb 28th
                )

        elif billing_cycle.lower() == 'weekly':
            # Add 7 days
            return start_date + datetime.timedelta(days=7)

        elif billing_cycle.lower() == 'quarterly':
            # Add 3 months
            month = start_date.month + 3
            year = start_date.year

            if month > 12:
                month = month - 12
                year += 1

            # Handle months with different lengths
            day = min(start_date.day, self._days_in_month(year, month))
            return datetime.date(year, month, day)

        elif billing_cycle.lower() in ['biannual', 'semi-annual']:
            # Add 6 months
            month = start_date.month + 6
            year = start_date.year

            if month > 12:
                month = month - 12
                year += 1

            # Handle months with different lengths
            day = min(start_date.day, self._days_in_month(year, month))
            return datetime.date(year, month, day)

        else:
            # Default to monthly if cycle is unknown
            return self._calculate_trial_end_date(start_date, 'monthly')

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        """Helper function to get the number of days in a month."""
        import calendar
        return calendar.monthrange(year, month)[1]