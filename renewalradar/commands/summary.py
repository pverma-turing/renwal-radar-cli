
from datetime import datetime as dt, timedelta
from collections import defaultdict
import textwrap
from colorama import Fore, Style
from tabulate import tabulate

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.models.subscription import Subscription
from renewalradar.registry import register_command


@register_command
class SummaryCommand(Command):
    """Command for displaying a summary of subscriptions."""

    name = "summary"
    description = "Display a high-level summary of your subscription portfolio"

    # Define exchange rates to USD (static rates for demonstration)
    EXCHANGE_RATES = {
        "USD": 1.0,  # 1 USD = 1.0 USD
        "EUR": 1.1,  # 1 EUR = 1.1 USD
        "GBP": 1.3,  # 1 GBP = 1.3 USD
        "INR": 0.012,  # 1 INR = 0.012 USD
        "JPY": 0.0073,  # 1 JPY = 0.0073 USD
        "CAD": 0.74,  # 1 CAD = 0.74 USD
        "AUD": 0.66,  # 1 AUD = 0.66 USD
        "CNY": 0.14  # 1 CNY = 0.14 USD
    }

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
        # Support the same filters as the view command
        # Filtering options
        parser.add_argument(
            "--status",
            nargs="*",
            choices=Subscription.VALID_STATUSES,
            help="Filter subscriptions by status (multiple values allowed)"
        )

        parser.add_argument(
            "--payment-method",
            action="append",
            dest="payment_methods",
            help="Filter subscriptions by payment method. Can be used multiple times."
        )

        parser.add_argument(
            "--tag",
            action="append",
            dest="tags",
            help="Filter subscriptions by tag. Can be used multiple times (OR filter)."
        )

        parser.add_argument(
            "--currency",
            help="Currency to use for display (default: use the currency of each subscription)"
        )

        # Breakdown options
        parser.add_argument(
            "--by-tag",
            action="store_true",
            help="Show full cost breakdown by tag"
        )

        parser.add_argument(
            "--by-payment-method",
            action="store_true",
            help="Show full cost breakdown by payment method"
        )

        # NEW: Top-N options
        parser.add_argument(
            "--top-tags",
            type=int,
            metavar="N",
            help="Show top N tags by spend"
        )

        parser.add_argument(
            "--top-payments",
            type=int,
            metavar="N",
            help="Show top N payment methods by spend"
        )

        parser.add_argument(
            "--period",
            choices=["monthly", "annual"],
            default="monthly",
            help="Period for cost calculation (default: monthly)"
        )

        parser.add_argument(
            "--include-cancelled",
            action="store_true",
            help="Include cancelled subscriptions in summary (excluded by default)"
        )

        parser.add_argument(
            "--expiring-days",
            type=int,
            default=7,
            help="Days threshold for classifying active/trial subscriptions as expiring (default: 7)"
        )

        return parser

    def execute(self, args):
        """Execute summary command."""
        try:
            # Initialize database if it doesn't exist
            db_manager = DatabaseManager()

            # Build filters based on provided arguments
            filters = {}

            if args.status:
                filters["status"] = args.status
            elif not args.include_cancelled:
                # By default, exclude cancelled subscriptions
                filters["status"] = ["active", "trial", "expiring"]

            if args.payment_methods:
                filters["payment_methods"] = args.payment_methods

            if args.tags:
                filters["tag"] = args.tags

            # Get filtered subscriptions
            subscriptions = db_manager.get_filtered_subscriptions(filters)

            if not subscriptions:
                print("No matching subscriptions found.")
                return 0

            # Process subscriptions to classify expiring ones
            current_date = dt.now().date()
            expiring_threshold = current_date + timedelta(days=args.expiring_days)

            # Track status counts
            status_counts = defaultdict(int)

            # Reference currency for conversions if needed
            reference_currency = args.currency or subscriptions[0].currency

            # Process each subscription to check for expiring status and count by status
            for subscription in subscriptions:
                # Add a display_status attribute for showing in the view
                # This doesn't change the actual status stored in the database
                subscription.display_status = subscription.status

                # Check if the subscription should be marked as expiring
                if (subscription.status in ["active", "trial"] and
                        subscription.renewal_date and
                        self._is_date_within_range(subscription.renewal_date, current_date, expiring_threshold)):
                    subscription.display_status = "expiring"

                # Count by display status
                status_counts[subscription.display_status] += 1

                # Apply currency conversion if needed
                if args.currency and subscription.currency != args.currency:
                    # In a real app, this would use actual exchange rates
                    # Here we'll just note that conversion would happen
                    subscription.original_currency = subscription.currency
                    subscription.original_cost = subscription.cost
                    # For demo, we'll just assume a 1:1 conversion
                    subscription.currency = args.currency

            # Show overall summary
            self._display_overall_summary(subscriptions, status_counts, args.period, reference_currency)

            # NEW: Show top-N tags if requested
            if args.top_tags:
                self._display_top_tags(subscriptions, args.period, reference_currency, args.top_tags)

            # NEW: Show top-N payment methods if requested
            if args.top_payments:
                self._display_top_payment_methods(subscriptions, args.period, reference_currency, args.top_payments)

            # Show full breakdowns if requested
            if args.by_payment_method:
                self._display_payment_method_breakdown(subscriptions, args.period, reference_currency)

            if args.by_tag:
                self._display_tag_breakdown(subscriptions, args.period, reference_currency)

            # Display filter information
            self._display_filter_info(args)

            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An error occurred: {e}")
            return 1

    def _display_overall_summary(self, subscriptions, status_counts, period, currency):
        """Display overall subscription summary."""
        print("\n=== SUBSCRIPTION SUMMARY ===\n")

        # Total counts by status
        status_parts = []
        for status in ["active", "trial", "expiring", "cancelled"]:
            if status_counts[status] > 0:
                status_parts.append(f"{status_counts[status]} {status}")

        if status_parts:
            status_summary = ", ".join(status_parts)
            print(f"Total Subscriptions: {sum(status_counts.values())} ({status_summary})")

        # Calculate costs
        if period == "monthly":
            total_cost = sum(sub.cost for sub in subscriptions)
            period_name = "Monthly"
        else:  # annual
            total_cost = sum(sub.annual_cost for sub in subscriptions)
            period_name = "Annual"

        print(f"Total {period_name} Cost: {currency} {total_cost:.2f}")

        # Average cost
        if subscriptions:
            if period == "monthly":
                avg_cost = total_cost / len(subscriptions)
            else:
                avg_cost = total_cost / len(subscriptions)
            print(f"Average {period_name} Cost per Subscription: {currency} {avg_cost:.2f}")

        # Most expensive subscription
        if subscriptions:
            if period == "monthly":
                most_expensive = max(subscriptions, key=lambda x: x.cost)
                cost_value = most_expensive.cost
            else:
                most_expensive = max(subscriptions, key=lambda x: x.annual_cost)
                cost_value = most_expensive.annual_cost

            print(f"Most Expensive Subscription: {most_expensive.name} ({currency} {cost_value:.2f} {period})")

    def _display_top_tags(self, subscriptions, period, currency, count):
        """Display top N tags by spend."""
        # Skip if no tags present
        if not any(sub.tags for sub in subscriptions):
            return

        print(f"\nTop {count} Tags:")

        # Group by tag (note: subscriptions can have multiple tags)
        tag_costs = defaultdict(float)

        for sub in subscriptions:
            # Choose cost based on period
            cost = sub.cost if period == "monthly" else sub.annual_cost

            if not sub.tags:
                # Handle untagged subscriptions
                tag = "Untagged"
                tag_costs[tag] += cost
            else:
                # For tagged subscriptions
                for tag in sub.tags:
                    tag_costs[tag] += cost

        # Get top N tags by spend
        top_tags = sorted(tag_costs.items(), key=lambda x: x[1], reverse=True)[:count]

        # Display as simple ranked list
        for i, (tag, cost) in enumerate(top_tags, 1):
            print(f"{i}. {tag:<10} – {currency} {cost:.2f}")

    def _display_top_payment_methods(self, subscriptions, period, currency, count):
        """Display top N payment methods by spend."""
        print(f"\nTop {count} Payment Methods:")

        # Group by payment method
        payment_costs = defaultdict(float)

        for sub in subscriptions:
            method = sub.payment_method or "Unknown"
            # Choose cost based on period
            cost = sub.cost if period == "monthly" else sub.annual_cost
            payment_costs[method] += cost

        # Get top N payment methods by spend
        top_methods = sorted(payment_costs.items(), key=lambda x: x[1], reverse=True)[:count]

        # Display as simple ranked list
        for i, (method, cost) in enumerate(top_methods, 1):
            print(f"{i}. {method:<15} – {currency} {cost:.2f}")

    def _display_payment_method_breakdown(self, subscriptions, period, currency):
        """Display breakdown of costs by payment method."""
        print("\n=== BREAKDOWN BY PAYMENT METHOD ===\n")

        # Group by payment method
        payment_method_costs = defaultdict(float)
        payment_method_counts = defaultdict(int)

        for sub in subscriptions:
            method = sub.payment_method or "Unknown"
            payment_method_counts[method] += 1

            if period == "monthly":
                payment_method_costs[method] += sub.cost
            else:
                payment_method_costs[method] += sub.annual_cost

        if not payment_method_costs:
            print("No payment method data available.")
            return

        # Prepare data for display
        table_data = []
        total_cost = sum(payment_method_costs.values())

        for method, cost in sorted(payment_method_costs.items(), key=lambda x: x[1], reverse=True):
            count = payment_method_counts[method]
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            table_data.append([
                method,
                count,
                f"{currency} {cost:.2f}",
                f"{percentage:.1f}%"
            ])

        # Add total row
        table_data.append([
            "TOTAL",
            sum(payment_method_counts.values()),
            f"{currency} {total_cost:.2f}",
            "100.0%"
        ])

        # Display table
        headers = ["Payment Method", "Count", f"{period.capitalize()} Cost", "% of Total"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

    def _display_tag_breakdown(self, subscriptions, period, currency):
        """Display breakdown of costs by tag."""
        print("\n=== BREAKDOWN BY TAG ===\n")

        # Group by tag (note: subscriptions can have multiple tags)
        tag_costs = defaultdict(float)
        tag_counts = defaultdict(int)

        for sub in subscriptions:
            if not sub.tags:
                # Handle untagged subscriptions
                tag = "Untagged"
                tag_counts[tag] += 1
                if period == "monthly":
                    tag_costs[tag] += sub.cost
                else:
                    tag_costs[tag] += sub.annual_cost
            else:
                # For tagged subscriptions, distribute cost across all tags
                # This means the sum of tag costs will be higher than total cost
                # if subscriptions have multiple tags
                for tag in sub.tags:
                    tag_counts[tag] += 1
                    if period == "monthly":
                        tag_costs[tag] += sub.cost
                    else:
                        tag_costs[tag] += sub.annual_cost

        if not tag_costs:
            print("No tag data available.")
            return

        # Prepare data for display
        table_data = []
        # Note: We don't calculate percentage here because tag costs can sum to more than
        # total cost due to multiple tags per subscription

        for tag, cost in sorted(tag_costs.items(), key=lambda x: x[1], reverse=True):
            count = tag_counts[tag]
            table_data.append([
                tag,
                count,
                f"{currency} {cost:.2f}"
            ])

        # Display table with note
        headers = ["Tag", "Count", f"{period.capitalize()} Cost"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print("\nNote: Subscriptions with multiple tags are counted in each applicable category.")

    def _display_filter_info(self, args):
        """Display information about active filters."""
        filter_info = []

        if args.status:
            filter_info.append(f"status=[{', '.join(args.status)}]")
        elif not args.include_cancelled:
            filter_info.append("status=[active, trial, expiring] (cancelled excluded)")

        if args.payment_methods:
            filter_info.append(f"payment_methods=[{', '.join(args.payment_methods)}]")

        if args.tags:
            filter_info.append(f"tags=[{', '.join(args.tags)}]")

        if args.currency:
            filter_info.append(f"currency='{args.currency}'")

        if args.top_tags:
            filter_info.append(f"top-tags={args.top_tags}")

        if args.top_payments:
            filter_info.append(f"top-payments={args.top_payments}")

        if filter_info:
            print(f"\nFilters applied: {' AND '.join(filter_info)}")

    def _is_date_within_range(self, date_str, start_date, end_date):
        """Check if a date string is within a given date range."""
        try:
            from datetime import datetime, timedelta
            # Parse the date string (assuming YYYY-MM-DD format)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Check if date is in range [start_date, end_date]
            return start_date <= date_obj <= end_date
        except (ValueError, TypeError):
            # Return False if date is invalid
            return False