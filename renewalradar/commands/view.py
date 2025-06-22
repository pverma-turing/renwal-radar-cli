"""
ViewCommand implementation for RenewalRadar subscription manager.
Handles displaying subscriptions from the command line.
"""

import argparse
import sys
import datetime
from dateutil.relativedelta import relativedelta

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.utils.date_utils import days_until_renewal

from renewalradar.registry import register_command


@register_command
class ViewCommand(Command):
    """Command to view subscriptions."""

    name = 'view'
    description = 'View all subscriptions'

    @classmethod
    def register_arguments(cls, parser):
        """Register command-specific arguments."""
        parser.add_argument(
            '--sort',
            choices=['name', 'cost', 'renewal_date'],
            help='Sort subscriptions by the specified field'
        )

    def execute(self, args):
        """Execute the view command."""
        try:
            db_manager = DatabaseManager()
            try:
                subscriptions = db_manager.get_all_subscriptions(sort_by=args.sort)

                if not subscriptions:
                    print("No subscriptions found.")
                    return 0

                self._display_subscriptions(subscriptions)
                self._display_summary(subscriptions)
                return 0
            finally:
                db_manager.close()

        except Exception as e:
            print(f"An error occurred: {e}")
            return 1

    def _display_subscriptions(self, subscriptions):
        """Display subscriptions in a formatted table."""
        # Calculate column widths
        col_widths = {
            "id": max(2, max([len(str(s["id"])) for s in subscriptions] + [2])),
            "name": max(4, max([len(s["name"]) for s in subscriptions] + [4])),
            "cost": max(4, max([len(f"{s['cost']:.2f} {s['currency']}") for s in subscriptions] + [4])),
            "cycle": max(5, max([len(s["billing_cycle"]) for s in subscriptions] + [5])),
            "renewal": max(8, max([len(s["renewal_date"]) for s in subscriptions] + [8])),
            "days": 6,
            "payment": max(7, max([len(s["payment_method"] or "N/A") for s in subscriptions] + [7]))
        }

        # Print header
        header = (
            f"{'ID':<{col_widths['id']}} "
            f"{'NAME':<{col_widths['name']}} "
            f"{'COST':<{col_widths['cost']}} "
            f"{'CYCLE':<{col_widths['cycle']}} "
            f"{'RENEWAL':<{col_widths['renewal']}} "
            f"{'DAYS':<{col_widths['days']}} "
            f"{'PAYMENT':<{col_widths['payment']}}"
        )
        print(header)
        print("-" * len(header))

        # Print each subscription
        for sub in subscriptions:
            days = days_until_renewal(sub["renewal_date"])
            days_str = str(days) if days >= 0 else f"OVERDUE({-days})"
            row = f"{sub['id']:<{col_widths['id']}} "\
                  f"{sub['name']:<{col_widths['name']}} "
            f"{sub['cost']:.2f} {sub['currency']:<{col_widths['cost']}}"
            f"{sub['billing_cycle']:<{col_widths['cycle']}} "
            f"{sub['renewal_date']:<{col_widths['renewal']}} "
            f"{days_str:<{col_widths['days']}} "
            f"{sub['payment_method'] or 'N/A':<{col_widths['payment']}}"

            print(row)


    def _display_summary(self, subscriptions):
        """Display summary information about subscriptions."""
        # Count subscriptions
        total_count = len(subscriptions)

        # Calculate total monthly and yearly costs
        monthly_total = 0
        yearly_total = 0
        currencies = set()

        for sub in subscriptions:
            cost = sub["cost"]
            currency = sub["currency"]
            currencies.add(currency)

            if sub["billing_cycle"] == "monthly":
                monthly_total += cost
                yearly_total += cost * 12
            elif sub["billing_cycle"] == "yearly":
                monthly_total += cost / 12
                yearly_total += cost

        # Upcoming renewals
        upcoming_renewals = []
        today = datetime.datetime.now().date()
        next_month = today + relativedelta(months=1)

        for sub in subscriptions:
            renewal_date = datetime.datetime.fromisoformat(sub["renewal_date"]).date()
            if today <= renewal_date <= next_month:
                days = days_until_renewal(sub["renewal_date"])
                upcoming_renewals.append((sub["name"], sub["renewal_date"], days))

        # Print summary
        print("\nSUMMARY:")
        print(f"Total subscriptions: {total_count}")

        if len(currencies) == 1:
            currency = list(currencies)[0]
            print(f"Monthly cost: {monthly_total:.2f} {currency}")
            print(f"Yearly cost: {yearly_total:.2f} {currency}")
        else:
            print("Monthly/yearly costs not summarized (multiple currencies)")

        if upcoming_renewals:
            print("\nUpcoming renewals (next 30 days):")
            for name, date, days in sorted(upcoming_renewals, key=lambda x: x[2]):
                print(f"• {name}: {date} ({days} days from now)")
        else:
            print("\nNo renewals in the next 30 days.")