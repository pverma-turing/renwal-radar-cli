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

        # Display the renewals
        self._display_renewals(
            upcoming_renewals,
            totals_by_currency,
            args.days,
            filter_description
        )

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
        """
        filters = {
            "status": ["active", "trial"],  # Always filter by active/trial status
            "renewal_date_range": (today, end_date)  # Filter by renewal date range
        }

        # Add tag filter if specified (no change)
        if args.tags:
            filters["tag"] = args.tags

        # Add payment method filter if specified (no change)
        if args.payment_methods:
            filters["payment_methods"] = args.payment_methods

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
        """
        # Pre-allocate collections to avoid resizing
        upcoming_renewals = []
        totals_by_currency = {}

        # Optimize: Compute frequently used values once outside the loop
        status_trial = 'trial'  # String constants used in comparisons

        # Process each subscription (should be pre-filtered by DB query)
        for subscription in subscriptions:
            # Optimization: Access object attributes directly once
            renewal_date = parse_date(subscription.renewal_date).date()

            # Skip if there's no renewal date (safety check)
            if not renewal_date:
                continue

            # Calculate days until renewal
            days_until_renewal = (renewal_date - today).days

            # Access all required attributes once to minimize lookups
            name = subscription.name
            status = subscription.status
            payment_method = subscription.payment_method
            amount = subscription.cost
            currency = subscription.currency
            tags = getattr(subscription, 'tags', [])

            # Create a dictionary with only the required information
            # Optimization: Only create the necessary fields
            renewal_info = {
                'name': name,
                'days_until_renewal': days_until_renewal,
                'status': status,
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

        # Sort renewals by days until renewal (ascending)
        # Optimization: Use key function without lambda for slightly better performance
        upcoming_renewals.sort(key=self._renewal_sort_key)

        return upcoming_renewals, totals_by_currency

    # Optimization: Define sort key function separately to avoid lambda creation in hot loops
    @staticmethod
    def _renewal_sort_key(renewal: Dict[str, Any]) -> int:
        """Key function for sorting renewals by days until renewal."""
        return renewal['days_until_renewal']

    def _display_renewals(
            self,
            upcoming_renewals: List[Dict[str, Any]],
            totals_by_currency: Dict[str, float],
            days_window: int,
            filter_description: Optional[str] = None
    ) -> None:
        """Display the upcoming subscription renewals in a table format."""
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
            status_text = trial_text if status == 'trial' else status.capitalize()

            # Format payment amount with currency (single string operation)
            amount = f"{renewal['amount']} {renewal['currency']}"

            # Format renewal date
            renewal_date = renewal['renewal_date'].strftime('%Y-%m-%d')

            # Add row to table
            table_data[i] = [
                renewal['name'],
                days_text,
                status_text,
                renewal['payment_method'],
                amount,
                renewal_date
            ]

        # Print title
        title = f"Upcoming Subscription Renewals (Next {days_window} Days)"
        if filter_description:
            title += f" - Filtered by: {filter_description}"

        print(f"\n{title}")
        print("=" * len(title))

        # Display table (no change to preserve output format)
        headers = ["Name", "Renewal In", "Status", "Payment Method", "Amount", "Renewal Date"]
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

        # Print summary (using pre-calculated totals)
        print("\nTotal upcoming charges:")
        for currency, amount in totals_by_currency.items():
            print(f"  {currency}: {amount:.2f}")

        print(f"\nTip: Use 'project --months 1' to see all renewals for the next month.")