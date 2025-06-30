import argparse
import csv
import datetime
import calendar
import sys
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional, NamedTuple

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
    'weekly': 1 / 4.33,  # Average weeks per month (52/12)
    'monthly': 1,
    'quarterly': 3,
    'biannual': 6,
    'semi-annual': 6,
    'yearly': 12,
    'annual': 12
}


class ProjectionConfig(NamedTuple):
    """Configuration for a projection calculation."""
    start_date: datetime.date
    end_date: datetime.date
    base_currency: Optional[str] = None
    group_by: Optional[str] = None
    normalize: bool = False
    dry_run: bool = False
    output_format: str = 'table'


class RenewalEvent(NamedTuple):
    """Represents a subscription renewal event."""
    date: datetime.date
    cost: float
    currency: str
    group_value: Optional[str] = None
    is_normalized: bool = False


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
            help="Convert all amounts to specified base currency"
        )
        parser.add_argument(
            "--group-by",
            type=str,
            help="Group projections by 'tag' or 'payment-method'"
        )
        parser.add_argument(
            "--normalize",
            action="store_true",
            help="Normalize costs by prorating longer billing cycles to monthly amounts"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be included in the projection without calculating costs"
        )
        parser.add_argument(
            "--format",
            type=str,
            default="table",
            help="Output format: 'table' or 'csv' (default: table)"
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

        # Create projection configuration
        config = ProjectionConfig(
            start_date=today,
            end_date=end_date,
            base_currency=args.base_currency,
            group_by=args.group_by,
            normalize=args.normalize,
            dry_run=args.dry_run,
            output_format=args.format.lower()
        )

        # Get filtered subscriptions
        subscriptions = self._get_filtered_subscriptions(args)

        # Show filter info for user awareness
        self._print_filter_info(args)

        if not subscriptions:
            print("No subscriptions found matching the specified criteria.")
            return

        # Generate renewal events for each subscription
        events = self._generate_renewal_events(subscriptions, config)

        # Check if any events were generated
        if not events:
            self._show_no_projections_message(subscriptions, config)
            return

        # Process events into a projection
        projection = self._process_events_to_projection(events, config)

        # Check if the projection has any data
        if not projection:
            self._show_empty_projection_message(subscriptions, config)
            return

        # Display the projection in the requested format
        if config.output_format == 'csv':
            self._output_csv_projection(projection, config)
        else:
            self._display_projection(projection, config)

    def _validate_arguments(self, args: argparse.Namespace) -> Optional[str]:
        """Validate command arguments and return error message if invalid."""
        # Validate months
        if args.months is not None and args.months <= 0:
            return "The number of months must be greater than zero."

        # Validate base currency
        if args.base_currency and args.base_currency not in EXCHANGE_RATES:
            supported_currencies = ", ".join(sorted(EXCHANGE_RATES.keys()))
            return f"Unsupported currency: '{args.base_currency}'. Supported currencies: {supported_currencies}"

        # Validate group-by
        if args.group_by and args.group_by not in VALID_GROUP_BY:
            valid_options = ", ".join(f"'{option}'" for option in VALID_GROUP_BY)
            return f"Invalid group-by option: '{args.group_by}'. Valid options are: {valid_options}"

        # Validate format
        if args.format and args.format.lower() not in VALID_FORMATS:
            valid_formats = ", ".join(f"'{fmt}'" for fmt in VALID_FORMATS)
            return f"Unsupported output format: '{args.format}'. Supported formats are: {valid_formats}"

            # All validations passed
            return None

        # All validations passed
        return None

    def _show_empty_projection_message(self, subscriptions: List[Subscription], config: ProjectionConfig) -> None:
        """Show a helpful message when the projection calculation resulted in empty data."""
        if config.output_format == 'csv':
            print("Month,No Data")
            print("Error,Projection calculation completed but no costs were found")
            return

        print("\nProjection calculation completed, but no costs were found to display.")
        print("This could happen if all subscriptions are filtered out during processing.")

        # Give more specific guidance
        if config.normalize:
            print("\nPossible issue: Normalization with unusual billing cycles")
            print("Try running without --normalize to see if that affects the results")

        print("\nTip: Use the `view` command to check your subscription details")
        print("     Example: renewalradar view --upcoming")

    def _show_no_subscriptions_message(self, args: argparse.Namespace) -> None:
        """Show a helpful message when no subscriptions match the filters."""
        print("\nNo subscriptions matched the current filters. Nothing to project.")

        # Provide more specific guidance based on the applied filters
        if args.tag:
            print(f"No subscriptions found with tag: '{args.tag}'")

        if args.payment_method:
            print(f"No subscriptions found with payment method: '{args.payment_method}'")

        print("\nTip: Use the `view` command to inspect your subscription data.")
        print("     Example: renewalradar view --all")

    def _show_no_projections_message(self, subscriptions: List[Subscription], config: ProjectionConfig) -> None:
        """Show a helpful message when subscriptions exist but no projections can be made."""
        if config.output_format == 'csv':
            print("Month,No Data")
            print("Error,No renewal projections could be generated for the selected time period")
            return

        print("\nNo renewal projections could be generated for the selected time period.")
        print(f"Selected period: {config.start_date.strftime('%b %d, %Y')} to {config.end_date.strftime('%b %d, %Y')}")

        # Count active and trial subscriptions
        active_count = sum(1 for s in subscriptions if getattr(s, 'status', '') == 'active')
        trial_count = sum(1 for s in subscriptions if getattr(s, 'status', '') == 'trial')

        print(f"\nSelected subscriptions: {len(subscriptions)} total ({active_count} active, {trial_count} trial)")

        # Suggest possible solutions
        print("\nPossible reasons:")
        print("- All selected subscriptions renew outside the projection period")
        print("- Trial subscriptions don't convert to paid within the projection period")

        print("\nTip: Try extending the projection period with --months or check renewal dates")
        print("     Example: renewalradar project --months 12")

    def _get_filtered_subscriptions(self, args: argparse.Namespace) -> List[Subscription]:
        """Get subscriptions with applied filters."""
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
        return db_manager.get_filtered_subscriptions(filters)

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

        if args.dry_run:
            filters_applied.append("dry run (preview only)")

        if filters_applied:
            print(f"Applying filters: {', '.join(filters_applied)}")

    def _display_dry_run_info(self, subscriptions: List[Subscription], config: ProjectionConfig,
                              args: argparse.Namespace) -> None:
        """Display information about what would be included in the projection."""
        # For CSV format, output a simple header and info
        if config.output_format == 'csv':
            print("Field,Value")
            print(f"SubscriptionsTotal,{len(subscriptions)}")
            active_count = sum(1 for s in subscriptions if getattr(s, 'status', '') == 'active')
            trial_count = sum(1 for s in subscriptions if getattr(s, 'status', '') == 'trial')
            print(f"SubscriptionsActive,{active_count}")
            print(f"SubscriptionsTrial,{trial_count}")
            print(f"ProjectionMonths,{args.months}")
            print(f"Tag,{args.tag or 'None'}")
            print(f"PaymentMethod,{args.payment_method or 'None'}")
            print(f"BaseCurrency,{args.base_currency or 'None'}")
            print(f"GroupBy,{args.group_by or 'None'}")
            print(f"Normalize,{args.normalize}")
            print("Message,This is a dry run - no projection calculations were performed")
            return

        print("\n===== PROJECTION DRY RUN =====")

        # Count active and trial subscriptions
        active_count = sum(1 for s in subscriptions if getattr(s, 'status', '') == 'active')
        trial_count = sum(1 for s in subscriptions if getattr(s, 'status', '') == 'trial')

        # Display subscription counts
        print(f"Subscriptions selected: {len(subscriptions)} total")
        print(f"  - {active_count} active subscription(s)")
        print(f"  - {trial_count} trial subscription(s)")

        # Display date range
        months = (config.end_date - config.start_date).days // 30
        print(f"\nProjection period: {months} months")
        print(f"  - From: {config.start_date.strftime('%B %d, %Y')}")
        print(f"  - To:   {config.end_date.strftime('%B %d, %Y')}")

        # Display active filters
        print("\nActive filters:")
        if args.tag:
            print(f"  - Tag filter: '{args.tag}'")
        else:
            print("  - Tag filter: None (including all tags)")

        if args.payment_method:
            print(f"  - Payment method filter: '{args.payment_method}'")
        else:
            print("  - Payment method filter: None (including all payment methods)")

        # Display projection options
        print("\nProjection options:")
        if args.normalize:
            print("  - Cost normalization: Enabled (prorating longer billing cycles to monthly amounts)")
        else:
            print("  - Cost normalization: Disabled (showing actual renewal amounts)")

        if args.group_by:
            group_type = "tag" if args.group_by == "tag" else "payment method"
            print(f"  - Grouping: By {group_type}")
        else:
            print("  - Grouping: None (grouping by currency)")

        if args.base_currency:
            print(f"  - Currency conversion: Converting all amounts to {args.base_currency}")
        else:
            print("  - Currency conversion: None (keeping original currencies)")

        if args.format:
            print(f"  - Output format: {args.format}")

        # Display trial handling info
        print("\nTrial subscription handling:")
        print("  - Trials will convert to paid when they end")
        print("  - Trial costs will only be included after conversion to paid")

        # Display billing cycles info
        billing_cycles = set(s.billing_cycle.lower() for s in subscriptions if hasattr(s, 'billing_cycle'))
        if billing_cycles:
            print("\nBilling cycles in selected subscriptions:")
            for cycle in sorted(billing_cycles):
                print(f"  - {cycle}")

        # Message about dry run
        print("\nNOTE: This is a dry run - no projection calculations were performed.")
        print("Run command without --dry-run to see actual cost projections.")
        print("=" * 30)

    def _convert_currency(self, amount: float, from_currency: str, to_currency: str) -> float:
        """
        Convert amount from one currency to another using the exchange rates.
        All conversions go through USD as the intermediate currency.
        """
        if from_currency == to_currency:
            return amount

        # Check if currencies are supported
        if from_currency not in EXCHANGE_RATES:
            print(f"Warning: Unknown currency '{from_currency}'. Using 1:1 conversion.")
            from_rate = 1.0
        else:
            from_rate = EXCHANGE_RATES[from_currency]

        if to_currency not in EXCHANGE_RATES:
            print(f"Warning: Unknown currency '{to_currency}'. Using 1:1 conversion.")
            to_rate = 1.0
        else:
            to_rate = EXCHANGE_RATES[to_currency]

        # Convert to USD first (divide by source currency rate)
        usd_amount = amount / EXCHANGE_RATES[from_currency]

        # Convert from USD to target currency (multiply by target currency rate)
        converted_amount = usd_amount * EXCHANGE_RATES[to_currency]

        # Round to 2 decimal places
        return round(converted_amount, 2)

    def _get_group_value(self, subscription: Subscription, group_by: str) -> str:
        """Get the value to use for grouping a subscription."""
        if not group_by:
            return None

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
        if months <= 0:
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

    def _add_month_to_date(self, date: datetime.date) -> datetime.date:
        """Add one month to a date, handling month transitions properly."""
        month = date.month + 1
        year = date.year
        if month > 12:
            month = 1
            year += 1

        # Handle month length differences
        max_day = calendar.monthrange(year, month)[1]
        day = min(date.day, max_day)

        return datetime.date(year, month, day)

    def _generate_renewal_events(
            self,
            subscriptions: List[Subscription],
            config: ProjectionConfig
    ) -> List[RenewalEvent]:
        """
        Generate a chronological list of renewal events for the given subscriptions.
        Takes into account trial periods, normalization, and currency conversion.
        """
        events = []

        for subscription in subscriptions:
            # Skip canceled subscriptions
            if hasattr(subscription, 'status') and subscription.status == 'canceled':
                continue

            # Get subscription details
            cost = float(subscription.cost)
            currency = subscription.currency
            billing_cycle = subscription.billing_cycle

            # Get group value if grouping is enabled
            group_value = self._get_group_value(subscription, config.group_by)

            # Handle trial subscriptions
            is_trial = hasattr(subscription, 'status') and subscription.status == 'trial'

            # Determine the first renewal date
            if is_trial:
                # For trial subscriptions, first renewal is when trial ends
                first_renewal_date = self._get_trial_end_date(subscription)
            else:
                # For active subscriptions, use the current renewal date
                first_renewal_date = parse_date(subscription.renewal_date)

            if config.normalize:
                # For normalized projections, we create monthly events
                monthly_cost = self._normalize_cost(cost, billing_cycle)

                # Apply currency conversion if needed
                if config.base_currency:
                    monthly_cost = self._convert_currency(monthly_cost, currency, config.base_currency)
                    event_currency = config.base_currency
                else:
                    event_currency = currency

                # For trial subscriptions, start from trial end date
                if is_trial:
                    current_date = max(config.start_date, first_renewal_date)
                else:
                    current_date = max(config.start_date, parse_date(subscription.renewal_date))

                # Create monthly events until the end date
                while current_date <= config.end_date:
                    events.append(RenewalEvent(
                        date=current_date,
                        cost=monthly_cost,
                        currency=event_currency,
                        group_value=group_value,
                        is_normalized=True
                    ))

                    # Move to the next month
                    current_date = self._add_month_to_date(current_date)
            else:
                # For non-normalized projections, we create events at each renewal date
                renewal_date = first_renewal_date

                # Apply currency conversion if needed
                if config.base_currency:
                    event_cost = self._convert_currency(cost, currency, config.base_currency)
                    event_currency = config.base_currency
                else:
                    event_cost = cost
                    event_currency = currency

                # Create events for each renewal date until the end date
                while renewal_date <= config.end_date:
                    if renewal_date >= config.start_date:
                        events.append(RenewalEvent(
                            date=renewal_date,
                            cost=event_cost,
                            currency=event_currency,
                            group_value=group_value,
                            is_normalized=False
                        ))

                    # Calculate next renewal date
                    renewal_date = self._calculate_next_renewal(renewal_date, billing_cycle)

        # Sort events by date
        return sorted(events, key=lambda e: e.date)

    def _process_events_to_projection(
            self,
            events: List[RenewalEvent],
            config: ProjectionConfig
    ) -> Dict[Tuple[int, int], Dict[str, float]]:
        """
        Process renewal events into a month-by-month projection.
        """
        # Initialize projection dictionary
        # Key: (year, month), Value: dictionary of currency/group -> amount
        projection = defaultdict(lambda: defaultdict(float))

        for event in events:
            # Extract year and month for grouping
            year_month = (event.date.year, event.date.month)

            if config.group_by:
                # When grouping, use group_value as the key
                key = event.group_value
            else:
                # When not grouping, use currency as the key
                key = event.currency

            # Add the cost to the appropriate bucket
            projection[year_month][key] += event.cost

        return projection

    def _display_projection(
            self,
            projection: Dict[Tuple[int, int], Dict[str, float]],
            config: ProjectionConfig
    ) -> None:
        """Display the projection in a table format."""
        if not projection:
            print("No renewals projected in the specified time period.")
            return

        # Get sorted list of all months in the projection
        months = sorted(projection.keys())

        # Get all column headers (either currencies or groups)
        columns = set()
        for month_data in projection.values():
            columns.update(month_data.keys())
        columns = sorted(columns)

        # Create the header row
        headers = ["Month"] + columns

        # Create the table rows
        rows = []
        for year, month in months:
            # Format the month name
            month_name = f"{calendar.month_name[month]} {year}"

            # Create a row with the month name and the amount for each column
            row = [month_name]
            for column in columns:
                amount = projection[(year, month)].get(column, 0)
                row.append(f"{amount:.2f}")

            rows.append(row)

        # Display the table
        period_months = (config.end_date - config.start_date).days // 30

        # Create header text based on configuration
        if config.group_by:
            group_type = "tag" if config.group_by == "tag" else "payment method"
            header_text = f"\nProjection of renewal costs for the next {period_months} months"

            if config.normalize:
                header_text += " (normalized to monthly amounts"
            else:
                header_text += " (actual renewal amounts"

            header_text += f", grouped by {group_type}"

            if config.base_currency:
                header_text += f", in {config.base_currency}"
        else:
            header_text = f"\nProjection of renewal costs for the next {period_months} months"

            if config.normalize:
                header_text += " (normalized to monthly amounts"
            else:
                header_text += " (actual renewal amounts"

            if config.base_currency:
                header_text += f", in {config.base_currency}"

        header_text += "):"

        print(header_text)
        print(tabulate(rows, headers=headers, tablefmt="simple_grid"))

        # Calculate and display totals
        totals = defaultdict(float)
        for month_data in projection.values():
            for key, amount in month_data.items():
                totals[key] += amount

        # Show totals
        if config.group_by:
            # When grouped, show totals by group with percentages
            print(f"\nTotal projected costs by {group_type}:")
            total_all = sum(totals.values())
            for group, total in sorted(totals.items()):
                # Show percentage of total
                percentage = (total / total_all * 100) if total_all > 0 else 0
                currency_label = f" {config.base_currency}" if config.base_currency else ""
                print(f"{group}: {total:.2f}{currency_label} ({percentage:.1f}%)")

            # Show grand total
            currency_label = f" {config.base_currency}" if config.base_currency else ""
            print(f"\nGrand total: {total_all:.2f}{currency_label}")
        else:
            # When not grouped, show totals by currency
            if config.base_currency:
                # When using base currency, there's only one total
                total = sum(totals.values())
                print(f"\nTotal projected cost: {total:.2f} {config.base_currency}")
            else:
                # When using multiple currencies, show total for each
                print("\nTotal projected costs by currency:")
                for currency, total in sorted(totals.items()):
                    print(f"{currency}: {total:.2f}")

    def _output_csv_projection(
            self,
            projection: Dict[Tuple[int, int], Dict[str, float]],
            config: ProjectionConfig
    ) -> None:
        """Output the projection in CSV format to stdout."""
        if not projection:
            print("Month,No Data")
            return

        # Get sorted list of all months in the projection
        months = sorted(projection.keys())

        # Get all column headers (either currencies or groups)
        columns = set()
        for month_data in projection.values():
            columns.update(month_data.keys())
        columns = sorted(columns)

        # Create CSV writer for stdout
        writer = csv.writer(sys.stdout)

        # Write header row
        writer.writerow(["Month"] + columns)

        # Write data rows
        for year, month in months:
            # Format the month name
            month_name = f"{calendar.month_name[month]} {year}"

            # Create a row with the month name and the amount for each column
            row = [month_name]
            for column in columns:
                amount = projection[(year, month)].get(column, 0)
                row.append(f"{amount:.2f}")

            writer.writerow(row)

        # Write summary rows
        writer.writerow([])  # Empty row as separator

        # Calculate totals
        totals = defaultdict(float)
        for month_data in projection.values():
            for key, amount in month_data.items():
                totals[key] += amount

        # Write total row
        total_row = ["Total"]
        for column in columns:
            total_row.append(f"{totals.get(column, 0):.2f}")
        writer.writerow(total_row)
