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
from renewalradar.utils.date_utils import parse_date

# Exchange rates dictionary (fixed rates for conversion)
# All rates are relative to USD (USD = 1.0)
EXCHANGE_RATES = {
    'USD': 1.0,
    'EUR': 1.1,
    'GBP': 1.31,
    'CAD': 0.74,
    'AUD': 0.67,
    'JPY': 0.0067,
    'INR': 0.012,
    'CHF': 1.15,
    'CNY': 0.14,
    'HKD': 0.13,
    'SGD': 0.75,
    'MXN': 0.058
}

# Valid group-by options
VALID_GROUP_BY = ['tag', 'payment-method']

# Billing cycle to months mapping for normalization
BILLING_CYCLE_MONTHS = {
    'weekly': 1/4.33,  # Average weeks per month (52/12)
    'monthly': 1,
    'quarterly': 3,
    'biannual': 6,
    'semi-annual': 6,
    'yearly': 12,
    'annual': 12
}

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
        parser.add_argument(
            "--tag",
            type=str,
            help="Filter projections by specified tag"
        )
        parser.add_argument(
            "--payment-method",
            type=str,
            help="Filter projections by payment method"
        )
        parser.add_argument(
            "--base-currency",
            type=str,
            choices=list(EXCHANGE_RATES.keys()),
            help="Convert all amounts to specified base currency"
        )
        parser.add_argument(
            "--group-by",
            type=str,
            choices=VALID_GROUP_BY,
            help="Group projections by 'tag' or 'payment-method'"
        )
        parser.add_argument(
            "--normalize",
            action="store_true",
            help="Normalize costs by prorating longer billing cycles to monthly amounts"
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

        # Get all active or trial subscriptions with specified filters
        db_manager = DatabaseManager()

        # Prepare filters
        filters = {
            "status": ["active", "trial"]  # Always filter for active or trial subscriptions
        }

        # Add tag filter if provided
        if args.tag:
            filters["tag"] = args.tag

        # Add payment method filter if provided
        if args.payment_method:
            filters["payment_method"] = args.payment_method

        # Get filtered subscriptions
        subscriptions = db_manager.get_filtered_subscriptions(filters=filters)

        # Show filter info for user awareness
        self._print_filter_info(args)

        if not subscriptions:
            print("No subscriptions found matching the specified criteria.")
            return

        # Project renewals for each subscription
        if args.group_by:
            # Project with grouping
            projection = self._project_renewals_grouped(
                subscriptions,
                today,
                end_date,
                args.base_currency,
                args.group_by
            )
            # Display with grouping
            self._display_projection_grouped(
                projection,
                today,
                end_date,
                args.base_currency,
                args.group_by
            )
        else:
            # Standard projection (no grouping)
            projection = self._project_renewals(
                subscriptions,
                today,
                end_date,
                args.base_currency
            )
            # Standard display
            self._display_projection(
                projection,
                today,
                end_date,
                args.base_currency
            )

    def _print_filter_info(self, args: argparse.Namespace) -> None:
        """Print information about active filters."""
        filters_applied = []

        if args.tag:
            filters_applied.append(f"tag: '{args.tag}'")

        if args.payment_method:
            filters_applied.append(f"payment method: '{args.payment_method}'")

        if args.base_currency:
            filters_applied.append(f"converted to base currency: '{args.base_currency}'")

        if args.group_by:
            filters_applied.append(f"grouped by: '{args.group_by}'")

        if args.normalize:
            filters_applied.append("costs normalized to monthly amounts")

        if filters_applied:
            print(f"Applying filters: {', '.join(filters_applied)}")

    def _convert_currency(self, amount: float, from_currency: str, to_currency: str) -> float:
        """
        Convert amount from one currency to another using the exchange rates.
        All conversions go through USD as the intermediate currency.
        """
        if from_currency == to_currency:
            return amount

        # Check if currencies are supported
        if from_currency not in EXCHANGE_RATES:
            print(f"Warning: Unknown currency '{from_currency}'. Cannot convert accurately.")
            return amount

        if to_currency not in EXCHANGE_RATES:
            print(f"Warning: Unknown currency '{to_currency}'. Cannot convert accurately.")
            return amount

        # Convert to USD first (divide by source currency rate)
        usd_amount = amount / EXCHANGE_RATES[from_currency]

        # Convert from USD to target currency (multiply by target currency rate)
        converted_amount = usd_amount * EXCHANGE_RATES[to_currency]

        # Round to 2 decimal places
        return round(converted_amount, 2)

    def _get_group_value(self, subscription: Subscription, group_by: str) -> str:
        """Get the value to use for grouping a subscription."""
        if group_by == 'tag':
            # Get the tag value, or 'Uncategorized' if no tag
            tag = getattr(subscription, 'tag', None)
            return tag if tag else 'Uncategorized'
        elif group_by == 'payment-method':
            # Get the payment method value, or 'Uncategorized' if no payment method
            payment_method = getattr(subscription, 'payment_method', None)
            return payment_method if payment_method else 'Uncategorized'
        else:
            # Should not happen due to validation, but just in case
            print(f"Warning: Unknown group by '{group_by}'. Using 'Uncategorized'.")
            return 'Uncategorized'

    def _get_billing_cycle_months(self, billing_cycle: str) -> float:
        """Get the number of months in a billing cycle."""
        billing_cycle = billing_cycle.lower()
        if billing_cycle in BILLING_CYCLE_MONTHS:
            return BILLING_CYCLE_MONTHS[billing_cycle]
        else:
            # Default to monthly if unknown
            print(f"Warning: Unknown billing cycle '{billing_cycle}'. Assuming monthly.")
            return 1

    def _normalize_cost(self, cost: float, billing_cycle: str) -> float:
        """Normalize a cost to a monthly amount based on the billing cycle."""
        months = self._get_billing_cycle_months(billing_cycle)
        if months == 0:
            return cost  # Avoid division by zero

        # Calculate monthly cost and round to 2 decimal places
        return round(cost / months, 2)

    def _get_trial_end_date(self, subscription: Subscription) -> datetime.date:
        """
        Calculate when a trial subscription will end and convert to paid.
        Trial period is assumed to be one billing cycle starting from start_date.
        """
        if not hasattr(subscription, 'start_date') or not hasattr(subscription, 'billing_cycle'):
            # If missing required attributes, use renewal date as fallback
            return parse_date(subscription.renewal_date)

        # Get the trial start date
        start_date = parse_date(subscription.start_date)

        # Calculate trial end date based on billing cycle
        billing_cycle = subscription.billing_cycle.lower()

        if billing_cycle == 'monthly':
            # Add 1 month to start date
            month = start_date.month + 1
            year = start_date.year

            if month > 12:
                month = 1
                year += 1

            # Adjust for month length differences
            max_day = calendar.monthrange(year, month)[1]
            day = min(start_date.day, max_day)

            return datetime.date(year, month, day)

        elif billing_cycle == 'yearly' or billing_cycle == 'annual':
            # Add 1 year to start date
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

        elif billing_cycle == 'weekly':
            # Add 7 days to start date
            return start_date + datetime.timedelta(days=7)

        elif billing_cycle == 'quarterly':
            # Add 3 months to start date
            month = start_date.month + 3
            year = start_date.year

            if month > 12:
                month = month - 12
                year += 1

            # Adjust for month length differences
            max_day = calendar.monthrange(year, month)[1]
            day = min(start_date.day, max_day)

            return datetime.date(year, month, day)

        elif billing_cycle == 'biannual' or billing_cycle == 'semi-annual':
            # Add 6 months to start date
            month = start_date.month + 6
            year = start_date.year

            if month > 12:
                month = month - 12
                year += 1

            # Adjust for month length differences
            max_day = calendar.monthrange(year, month)[1]
            day = min(start_date.day, max_day)

            return datetime.date(year, month, day)

        else:
            # Default to monthly for unknown billing cycles
            print(f"Warning: Unknown billing cycle '{billing_cycle}'. Assuming monthly trial.")
            month = start_date.month + 1
            year = start_date.year

            if month > 12:
                month = 1
                year += 1

            max_day = calendar.monthrange(year, month)[1]
            day = min(start_date.day, max_day)

            return datetime.date(year, month, day)

    def _project_renewals(
            self,
            subscriptions: List[Subscription],
            start_date: datetime.date,
            end_date: datetime.date,
            base_currency: Optional[str] = None,
            normalize: bool = False
    ) -> Dict[Tuple[int, int], Dict[str, float]]:
        """
        Project renewals for the given subscriptions within the time window.
        Returns a dictionary mapping (year, month) to a dictionary of currency -> amount.
        If base_currency is provided, converts all amounts to that currency.
        If normalize is True, prorates costs for longer billing cycles to monthly amounts.
        """
        # Initialize a dictionary to store the projection
        # Key: (year, month), Value: dictionary of currency -> total amount
        projection = defaultdict(lambda: defaultdict(float))

        for subscription in subscriptions:
            # Skip canceled subscriptions
            if hasattr(subscription, 'status') and subscription.status == 'canceled':
                continue

            # Get the subscription cost
            cost = float(subscription.cost)

            # Check if this is a trial subscription
            is_trial = False
            if hasattr(subscription, 'status') and subscription.status == 'trial':
                is_trial = True
                # Calculate when the trial ends
                trial_end_date = self._get_trial_end_date(subscription)

            # Set the initial renewal date
            if is_trial:
                # For trial subscriptions, first renewal is when trial ends
                renewal_date = trial_end_date
            else:
                # For active subscriptions, use the current renewal date
                renewal_date = subscription.renewal_date

            if normalize:
                # Normalize the cost to a monthly amount
                monthly_cost = self._normalize_cost(cost, subscription.billing_cycle)

                # For normalized projections, we need to handle the trial period differently
                if is_trial:
                    # Calculate the first month after trial ends
                    first_paid_month = max(start_date, trial_end_date)

                    # Only include months after trial ends
                    current_date = first_paid_month
                else:
                    # For non-trial subscriptions, start from the projection start date
                    current_date = max(start_date, renewal_date)

                # Add normalized cost for each month in the projection period
                while current_date <= end_date:
                    year_month = (current_date.year, current_date.month)

                    # Convert currency if needed
                    if base_currency:
                        converted_cost = self._convert_currency(
                            monthly_cost,
                            subscription.currency,
                            base_currency
                        )
                        projection[year_month][base_currency] += converted_cost
                    else:
                        projection[year_month][subscription.currency] += monthly_cost

                    # Move to the next month
                    month = current_date.month + 1
                    year = current_date.year
                    if month > 12:
                        month = 1
                        year += 1

                    # Last day might exceed the days in the month, so we handle that
                    max_day = calendar.monthrange(year, month)[1]
                    day = min(current_date.day, max_day)
                    current_date = datetime.date(year, month, day)
            else:
                # Use the unnormalized projection logic

                # For trial subscriptions, we don't include costs during the trial
                # Only start projecting costs from the first renewal after trial ends

                # Project all renewals until the end date
                while renewal_date <= end_date:
                    # Skip if the renewal date is before the start date
                    if renewal_date >= start_date:
                        # Add the cost to the appropriate month and currency
                        year_month = (renewal_date.year, renewal_date.month)

                        # Convert currency if needed
                        if base_currency:
                            # Convert to base currency
                            converted_cost = self._convert_currency(
                                cost,
                                subscription.currency,
                                base_currency
                            )
                            projection[year_month][base_currency] += converted_cost
                        else:
                            # Use original currency
                            projection[year_month][subscription.currency] += cost

                    # Calculate the next renewal date based on the billing cycle
                    renewal_date = self._calculate_next_renewal(renewal_date, subscription.billing_cycle)

        return projection

    def _project_renewals_grouped(
            self,
            subscriptions: List[Subscription],
            start_date: datetime.date,
            end_date: datetime.date,
            base_currency: Optional[str] = None,
            group_by: str = 'tag',
            normalize: bool = False
    ) -> Dict[Tuple[int, int], Dict[str, float]]:
        """
        Project renewals for the given subscriptions within the time window,
        grouped by the specified attribute (tag or payment-method).
        Returns a dictionary mapping (year, month) to a dictionary of group -> amount.
        If base_currency is provided, converts all amounts to that currency before grouping.
        If normalize is True, prorates costs for longer billing cycles to monthly amounts.
        """
        # Initialize a dictionary to store the projection
        # Key: (year, month), Value: dictionary of group -> total amount
        projection = defaultdict(lambda: defaultdict(float))

        for subscription in subscriptions:
            # Skip canceled subscriptions
            if hasattr(subscription, 'status') and subscription.status == 'canceled':
                continue

            # Get the group value for this subscription
            group_value = self._get_group_value(subscription, group_by)

            # Get the subscription cost
            cost = float(subscription.cost)

            # Check if this is a trial subscription
            is_trial = False
            if hasattr(subscription, 'status') and subscription.status == 'trial':
                is_trial = True
                # Calculate when the trial ends
                trial_end_date = self._get_trial_end_date(subscription)

            # Set the initial renewal date
            if is_trial:
                # For trial subscriptions, first renewal is when trial ends
                renewal_date = trial_end_date
            else:
                # For active subscriptions, use the current renewal date
                renewal_date = subscription.renewal_date

            if normalize:
                # Normalize the cost to a monthly amount
                monthly_cost = self._normalize_cost(cost, subscription.billing_cycle)

                # For normalized projections, we need to handle the trial period differently
                if is_trial:
                    # Calculate the first month after trial ends
                    first_paid_month = max(start_date, trial_end_date)

                    # Only include months after trial ends
                    current_date = first_paid_month
                else:
                    # For non-trial subscriptions, start from the projection start date
                    current_date = max(start_date, renewal_date)

                # Add normalized cost for each month in the projection period
                while current_date <= end_date:
                    year_month = (current_date.year, current_date.month)

                    # Convert currency if needed
                    if base_currency:
                        converted_cost = self._convert_currency(
                            monthly_cost,
                            subscription.currency,
                            base_currency
                        )
                    else:
                        converted_cost = monthly_cost

                    # Add to the group total for this month
                    projection[year_month][group_value] += converted_cost

                    # Move to the next month
                    month = current_date.month + 1
                    year = current_date.year
                    if month > 12:
                        month = 1
                        year += 1

                    # Last day might exceed the days in the month, so we handle that
                    max_day = calendar.monthrange(year, month)[1]
                    day = min(current_date.day, max_day)
                    current_date = datetime.date(year, month, day)
            else:
                # Use the unnormalized projection logic

                # For trial subscriptions, we don't include costs during the trial
                # Only start projecting costs from the first renewal after trial ends

                # Project all renewals until the end date
                while renewal_date <= end_date:
                    # Skip if the renewal date is before the start date
                    if renewal_date >= start_date:
                        # Add the cost to the appropriate month and group
                        year_month = (renewal_date.year, renewal_date.month)

                        # Convert currency if needed
                        if base_currency:
                            # Convert to base currency
                            converted_cost = self._convert_currency(
                                cost,
                                subscription.currency,
                                base_currency
                            )
                        else:
                            # Use original currency
                            converted_cost = cost

                        # Add to the group total for this month
                        projection[year_month][group_value] += converted_cost

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

        elif billing_cycle.lower() == 'yearly' or billing_cycle.lower() == 'annual':
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
            end_date: datetime.date,
            base_currency: Optional[str] = None,
            normalize: bool = False
    ) -> None:
        """Display the projection in a table format (currency-based columns)."""
        if not projection:
            print("No renewals projected in the specified time period.")
            return

        # Get sorted list of all months in the projection
        months = sorted(projection.keys())

        # Get currencies to display
        currencies = []
        if base_currency:
            # When a base currency is specified, we only show that one
            currencies = [base_currency]
        else:
            # Otherwise show all currencies used
            currency_set = set()
            for month_data in projection.values():
                currency_set.update(month_data.keys())
            currencies = sorted(currency_set)

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
        period_months = (end_date - start_date).days // 30

        # Customize message based on whether we're using base currency and normalization
        header_text = f"\nProjection of renewal costs for the next {period_months} months"

        if normalize:
            header_text += " (normalized to monthly amounts"
        else:
            header_text += " (actual renewal amounts"

        if base_currency:
            header_text += f", in {base_currency}"

        header_text += "):"

        print(header_text)
        print(tabulate(rows, headers=headers, tablefmt="simple_grid"))

        # Calculate and display totals by currency
        totals = defaultdict(float)
        for month_data in projection.values():
            for currency, amount in month_data.items():
                totals[currency] += amount

        # Show totals
        if base_currency:
            print(f"\nTotal projected cost: {totals[base_currency]:.2f} {base_currency}")
        else:
            print("\nTotal projected costs by currency:")
            for currency, total in sorted(totals.items()):
                print(f"{currency}: {total:.2f}")

    def _display_projection_grouped(
            self,
            projection: Dict[Tuple[int, int], Dict[str, float]],
            start_date: datetime.date,
            end_date: datetime.date,
            base_currency: Optional[str] = None,
            group_by: str = 'tag',
            normalize: bool = False
    ) -> None:
        """Display the projection in a table format (group-based columns)."""
        if not projection:
            print("No renewals projected in the specified time period.")
            return

        # Get sorted list of all months in the projection
        months = sorted(projection.keys())

        # Get all groups used
        groups = set()
        for month_data in projection.values():
            groups.update(month_data.keys())
        groups = sorted(groups)

        # Create the header row
        headers = ["Month"] + groups

        # Create the table rows
        rows = []
        for year, month in months:
            # Format the month name
            month_name = f"{calendar.month_name[month]} {year}"

            # Create a row with the month name and the amount for each group
            row = [month_name]
            for group in groups:
                amount = projection[(year, month)].get(group, 0)
                row.append(f"{amount:.2f}")

            rows.append(row)

        # Display the table
        period_months = (end_date - start_date).days // 30

        # Create header text
        group_type = "tag" if group_by == "tag" else "payment method"
        header_text = f"\nProjection of renewal costs for the next {period_months} months"

        # Add normalization info
        if normalize:
            header_text += " (normalized to monthly amounts"
        else:
            header_text += " (actual renewal amounts"

        # Add grouping and currency info
        header_text += f", grouped by {group_type}"
        if base_currency:
            header_text += f", in {base_currency}"
        header_text += "):"

        print(header_text)
        print(tabulate(rows, headers=headers, tablefmt="simple_grid"))

        # Calculate and display totals by group
        totals = defaultdict(float)
        for month_data in projection.values():
            for group, amount in month_data.items():
                totals[group] += amount

        # Show totals by group
        print(f"\nTotal projected costs by {group_type}:")
        total_all = sum(totals.values())
        for group, total in sorted(totals.items()):
            # Show percentage of total
            percentage = (total / total_all * 100) if total_all > 0 else 0
            currency_label = f" {base_currency}" if base_currency else ""
            print(f"{group}: {total:.2f}{currency_label} ({percentage:.1f}%)")

        # Show grand total
        currency_label = f" {base_currency}" if base_currency else ""
        print(f"\nGrand total: {total_all:.2f}{currency_label}")
