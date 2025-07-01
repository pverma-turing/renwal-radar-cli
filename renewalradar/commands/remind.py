"""
File: renewalradar/commands/remind.py

This module implements the 'remind' command for RenewalRadar CLI, which
displays upcoming subscription renewals within a specified number of days.
"""

import argparse
import datetime
from typing import List

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

        # Get all active or trial subscriptions
        db_manager = DatabaseManager()
        subscriptions = db_manager.get_filtered_subscriptions(
            {'status': ["active", "trial"]}
        )

        if not subscriptions:
            print("No active or trial subscriptions found.")
            return

        # Filter subscriptions for those with renewals within the specified window
        upcoming_renewals = self._get_upcoming_renewals(subscriptions, today, end_date)

        # Display the renewals
        self._display_renewals(upcoming_renewals, today, end_date, args.days)

    def _get_upcoming_renewals(
            self,
            subscriptions: List[Subscription],
            start_date: datetime.date,
            end_date: datetime.date
    ) -> List[dict]:
        """
        Filter subscriptions to include only those with renewals in the specified window.
        Returns a list of dictionaries with subscription info and days until renewal.
        """
        upcoming_renewals = []

        for subscription in subscriptions:
            # Skip canceled subscriptions
            if hasattr(subscription, 'status') and subscription.status == 'canceled':
                continue

            # Calculate next renewal date (could be in the past if subscription is overdue)
            renewal_date = parse_date(subscription.renewal_date).date()

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
                    'renewal_date': renewal_date
                }

                upcoming_renewals.append(renewal_info)

        # Sort renewals by days until renewal (ascending)
        upcoming_renewals.sort(key=lambda x: x['days_until_renewal'])

        return upcoming_renewals

    def _display_renewals(
            self,
            upcoming_renewals: List[dict],
            today: datetime.date,
            end_date: datetime.date,
            days_window: int
    ) -> None:
        """Display the upcoming subscription renewals in a table format."""
        if not upcoming_renewals:
            print(f"No upcoming renewals in the next {days_window} days.")
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
        print(f"\nUpcoming Subscription Renewals (Next {days_window} Days)")
        print("=" * 60)

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