import argparse
import datetime
import calendar
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

from tabulate import tabulate  # Assuming tabulate is used for other table displays

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from renewalradar.registry import register_command
from renewalradar.utils import date_utils


@register_command
class ProjectCommand(Command):
    """Command for projecting future subscription renewal costs."""
    name = "project"
    description = "Command for projecting future subscription renewal costs."

    @classmethod
    def register_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Configure the argument parser for the project command."""
        parser.add_argument(
            "--months",
            type=int,
            default=3,
            help="Number of months to project renewals for (default: 3)"
        )

    def execute(self, args: argparse.Namespace) -> None:
        """Handle the project command."""
        # Validate input
        if args.months <= 0:
            print("Error: The number of months must be greater than zero.")
            return

        # Get current date as the starting point
        today = datetime.date.today()

        # Calculate the end date for projections
        end_date = today + datetime.timedelta(days=args.months * 30)  # Approximation

        # Get all active or trial subscriptions
        db_manager = DatabaseManager()
        subscriptions = db_manager.get_filtered_subscriptions(
            filters={'status': ["active", "trial"]}  # Assuming these are the status values used
        )

        if not subscriptions:
            print("No active or trial subscriptions found.")
            return

        # Project renewals for each subscription
        projection = self._project_renewals(subscriptions, today, end_date)

        # Display the projection in a table format
        self._display_projection(projection, today, end_date)

    def _project_renewals(
            self,
            subscriptions: List[Subscription],
            start_date: datetime.date,
            end_date: datetime.date
    ) -> Dict[Tuple[int, int], Dict[str, float]]:
        """
        Project renewals for the given subscriptions within the time window.
        Returns a dictionary mapping (year, month) to a dictionary of currency -> amount.
        """
        # Initialize a dictionary to store the projection
        # Key: (year, month), Value: dictionary of currency -> total amount
        projection = defaultdict(lambda: defaultdict(float))

        for subscription in subscriptions:
            # Skip canceled subscriptions
            if hasattr(subscription, 'status') and subscription.status == 'canceled':
                continue

            # Start with the current renewal date
            renewal_date = datetime.datetime.strptime(subscription.renewal_date, '%Y-%m-%d').date()
            # For trial subscriptions, calculate when they'll convert to paid
            if hasattr(subscription, 'status') and subscription.status == 'trial':
                # Use the renewal date as the conversion date for trials
                pass  # The default logic works for trials too

            # Project all renewals until the end date
            while renewal_date <= end_date:
                # Skip if the renewal date is before the start date
                if renewal_date >= start_date:
                    # Add the cost to the appropriate month and currency
                    year_month = (renewal_date.year, renewal_date.month)
                    projection[year_month][subscription.currency] += float(subscription.cost)

                # Calculate the next renewal date based on the billing cycle
                renewal_date = self._calculate_next_renewal(renewal_date, subscription.billing_cycle)

        return projection

    def _calculate_next_renewal(
            self,
            current_date: datetime.date,
            billing_cycle: str
    ) -> datetime.date:
        """Calculate the next renewal date based on the billing cycle."""
        if billing_cycle.lower() == 'monthly':
            # Add 1 month, handling month transitions
            month = current_date.month + 1
            year = current_date.year

            if month > 12:
                month = 1
                year += 1

            # Adjust the day if it exceeds the days in the new month
            max_day = calendar.monthrange(year, month)[1]
            day = min(current_date.day, max_day)

            return datetime.date(year, month, day)

        elif billing_cycle.lower() == 'yearly':
            # Add 1 year
            try:
                return datetime.date(
                    current_date.year + 1,
                    current_date.month,
                    current_date.day
                )
            except ValueError:  # Handle February 29th in leap years
                return datetime.date(
                    current_date.year + 1,
                    current_date.month,
                    28  # Default to Feb 28th
                )

        elif billing_cycle.lower() == 'weekly':
            # Add 7 days
            return current_date + datetime.timedelta(days=7)

        elif billing_cycle.lower() == 'quarterly':
            # Add 3 months
            month = current_date.month + 3
            year = current_date.year

            if month > 12:
                month = month - 12
                year += 1

            # Adjust the day if it exceeds the days in the new month
            max_day = calendar.monthrange(year, month)[1]
            day = min(current_date.day, max_day)

            return datetime.date(year, month, day)

        elif billing_cycle.lower() == 'biannual' or billing_cycle.lower() == 'semi-annual':
            # Add 6 months
            month = current_date.month + 6
            year = current_date.year

            if month > 12:
                month = month - 12
                year += 1

            # Adjust the day if it exceeds the days in the new month
            max_day = calendar.monthrange(year, month)[1]
            day = min(current_date.day, max_day)

            return datetime.date(year, month, day)

        else:
            # Default to monthly if cycle is unknown
            print(f"Warning: Unknown billing cycle '{billing_cycle}'. Assuming monthly.")
            return self._calculate_next_renewal(current_date, 'monthly')

    def _display_projection(
            self,
            projection: Dict[Tuple[int, int], Dict[str, float]],
            start_date: datetime.date,
            end_date: datetime.date
    ) -> None:
        """Display the projection in a table format."""
        if not projection:
            print("No renewals projected in the specified time period.")
            return

        # Get sorted list of all months in the projection
        months = sorted(projection.keys())

        # Get all currencies used
        currencies = set()
        for month_data in projection.values():
            currencies.update(month_data.keys())
        currencies = sorted(currencies)

        # Create the header row
        headers = ["Month"] + currencies

        # Create the table rows
        rows = []
        for year, month in months:
            # Format the month name
            month_name = f"{calendar.month_name[month]} {year}"

            # Create a row with the month name and the amount for each currency
            row = [month_name]
            for currency in currencies:
                amount = projection[(year, month)].get(currency, 0)
                row.append(f"{amount:.2f}")

            rows.append(row)

        # Display the table
        print(f"\nProjection of renewal costs for the next {(end_date - start_date).days // 30} months:")
        print(tabulate(rows, headers=headers, tablefmt="simple_grid"))

        # Calculate and display totals by currency
        totals = defaultdict(float)
        for month_data in projection.values():
            for currency, amount in month_data.items():
                totals[currency] += amount

        print("\nTotal projected costs by currency:")
        for currency, total in sorted(totals.items()):
            print(f"{currency}: {total:.2f}")
