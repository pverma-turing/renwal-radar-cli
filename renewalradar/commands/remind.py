"""
File: renewalradar/commands/remind.py

This module implements the 'remind' command for RenewalRadar CLI, which
displays upcoming subscription renewals within a specified number of days.
"""

import argparse
import datetime
from typing import List, Dict, Any, Optional

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

        # Get current date as the starting point
        today = datetime.date.today()

        # Calculate the end date for the reminder window
        end_date = today + datetime.timedelta(days=args.days)

        # Build filters dictionary
        filters = {
            "status": ["active", "trial"]  # Always filter by active/trial status
        }

        # Add tag filter if specified
        if args.tags:
            filters["tag"] = args.tags

        # Add payment method filter if specified
        if args.payment_methods:
            filters["payment_methods"] = args.payment_methods

        # Build filter description for output
        filter_description = self._build_filter_description(args)

        # Get filtered subscriptions
        db_manager = DatabaseManager()
        subscriptions = db_manager.get_filtered_subscriptions(filters)

        if not subscriptions:
            if filter_description:
                print(f"No subscriptions found matching the filters: {filter_description}.")
            else:
                print("No active or trial subscriptions found.")
            return

        # Filter subscriptions for those with renewals within the specified window
        upcoming_renewals = self._get_upcoming_renewals(subscriptions, today, end_date)

        # Display the renewals
        self._display_renewals(upcoming_renewals, today, end_date, args.days, filter_description)

    def _build_filter_description(self, args: argparse.Namespace) -> str:
        """Build a description of the filters being applied."""
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

    def _get_upcoming_renewals(
            self,
            subscriptions: List[Subscription],
            start_date: datetime.date,
            end_date: datetime.date
    ) -> List[Dict[str, Any]]:
        """
        Filter subscriptions to include only those with renewals in the specified window.
        Returns a list of dictionaries with subscription info and days until renewal.

        Note: Filtering by tag and payment method is already applied at this point.
        """
        upcoming_renewals = []

        for subscription in subscriptions:
            # Skip canceled subscriptions (though they should already be filtered out)
            if hasattr(subscription, 'status') and subscription.status == 'canceled':
                continue

            # Calculate next renewal date (could be in the past if subscription is overdue)
            renewal_date = parse_date(subscription.renewal_date).date()

            # Skip subscriptions without a renewal date
            if not renewal_date:
                continue

            # Check if renewal is within the specified window
            if start_date <= renewal_date <= end_date:
                # Calculate days until renewal
                days_until_renewal = (renewal_date - start_date).days

                # Create a dictionary with the required information
                renewal_info = {
                    'name': subscription.name,
                    'days_until_renewal': days_until_renewal,
                    'status': subscription.status,
                    'payment_method': subscription.payment_method,
                    'amount': subscription.cost,
                    'currency': subscription.currency,
                    'renewal_date': renewal_date,
                    'tags': subscription.tags if hasattr(subscription, 'tags') else []
                }

                upcoming_renewals.append(renewal_info)

        # Sort renewals by days until renewal (ascending)
        upcoming_renewals.sort(key=lambda x: x['days_until_renewal'])

        return upcoming_renewals

    def _display_renewals(
            self,
            upcoming_renewals: List[Dict[str, Any]],
            today: datetime.date,
            end_date: datetime.date,
            days_window: int,
            filter_description: Optional[str] = None
    ) -> None:
        """Display the upcoming subscription renewals in a table format."""
        if not upcoming_renewals:
            filter_msg = f" matching {filter_description}" if filter_description else ""
            print(f"No upcoming renewals{filter_msg} in the next {days_window} days.")
            return

        # Create table rows
        table_data = []

        for renewal in upcoming_renewals:
            # Format days until renewal with colors
            days = renewal['days_until_renewal']
            if days == 0:
                days_text = f"{Fore.RED}Today{Style.RESET_ALL}"
            elif days == 1:
                days_text = f"{Fore.RED}Tomorrow{Style.RESET_ALL}"
            elif days <= 3:
                days_text = f"{Fore.RED}{days} days{Style.RESET_ALL}"
            elif days <= 5:
                days_text = f"{Fore.YELLOW}{days} days{Style.RESET_ALL}"
            else:
                days_text = f"{days} days"

            # Format status with colors
            status = renewal['status']
            if status == 'trial':
                status_text = f"{Fore.CYAN}Trial{Style.RESET_ALL}"
            else:
                status_text = status.capitalize()

            # Format payment amount with currency
            amount = f"{renewal['amount']} {renewal['currency']}"

            # Format renewal date
            renewal_date = renewal['renewal_date'].strftime('%Y-%m-%d')

            # Add row to table
            row = [
                renewal['name'],
                days_text,
                status_text,
                renewal['payment_method'],
                amount,
                renewal_date
            ]

            table_data.append(row)

        # Print title
        title = f"Upcoming Subscription Renewals (Next {days_window} Days)"
        if filter_description:
            title += f" - Filtered by: {filter_description}"

        print(f"\n{title}")
        print("=" * len(title))

        # Display table
        headers = ["Name", "Renewal In", "Status", "Payment Method", "Amount", "Renewal Date"]
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

        # Print summary
        total_amount_by_currency = {}
        for renewal in upcoming_renewals:
            currency = renewal['currency']
            amount = float(renewal['amount'])

            if currency in total_amount_by_currency:
                total_amount_by_currency[currency] += amount
            else:
                total_amount_by_currency[currency] = amount

        print("\nTotal upcoming charges:")
        for currency, amount in total_amount_by_currency.items():
            print(f"  {currency}: {amount:.2f}")

        print(f"\nTip: Use 'project --months 1' to see all renewals for the next month.")