
from datetime import datetime as dt, timedelta
from collections import defaultdict
import textwrap
from colorama import Fore, Style

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
        parser.add_argument(
            "--currency",
            help="Filter subscriptions by currency"
        )

        parser.add_argument(
            "--status",
            nargs="*",
            choices=Subscription.VALID_STATUSES,
            help="Filter subscriptions by status (multiple values allowed)"
        )

        parser.add_argument(
            "--expiring-days",
            type=int,
            default=7,
            help="Days threshold for classifying subscriptions as expiring (default: 7)"
        )

        parser.add_argument(
            "--payment-method",
            help="Filter subscriptions by payment method"
        )

        return parser

    def execute(self, args):
        """Execute summary command."""
        try:
            # Initialize database if it doesn't exist
            db_manager = DatabaseManager()

            # Build filters dictionary based on provided arguments
            filters = {}

            if args.currency:
                filters["currency"] = args.currency

            if args.status:
                filters["status"] = args.status

            if args.payment_method:
                filters["payment_method"] = args.payment_method

            # Get subscriptions with filters
            subscriptions = db_manager.get_filtered_subscriptions(filters=filters)

            if not subscriptions:
                print("No subscriptions found.")
                return 0

            # Process subscriptions for summary information
            current_date = dt.now().date()
            expiring_threshold = current_date + timedelta(days=args.expiring_days)

            # Initialize counters
            status_counts = {status: 0 for status in Subscription.VALID_STATUSES}
            status_counts["expiring"] = 0  # Add expiring which might not be in database statuses

            total_by_currency = defaultdict(float)
            spend_by_status_currency = defaultdict(lambda: defaultdict(float))

            upcoming_renewals = 0

            # Process each subscription
            for subscription in subscriptions:
                # Add a display_status attribute for showing in the view
                subscription.display_status = subscription.status

                # Check if the subscription should be marked as expiring
                if (subscription.status in ["active", "trial"] and
                        subscription.renewal_date and
                        self._is_date_within_range(subscription.renewal_date, current_date, expiring_threshold)):
                    subscription.display_status = "expiring"
                    upcoming_renewals += 1

                # Count by display status
                status_counts[subscription.display_status] += 1

                # Track total spending by currency
                currency = subscription.currency
                total_by_currency[currency] += subscription.cost

                # Track spending by status and currency
                spend_by_status_currency[subscription.display_status][currency] += subscription.cost

            # Display summary
            self._display_summary(
                subscriptions=subscriptions,
                status_counts=status_counts,
                total_by_currency=total_by_currency,
                spend_by_status_currency=spend_by_status_currency,
                upcoming_renewals=upcoming_renewals,
                expiring_days=args.expiring_days,
                target_currency=args.currency
            )

            # Display filter information if filters were applied
            filter_info = []
            if args.currency:
                filter_info.append(f"currency='{args.currency}'")
            if args.status:
                filter_info.append(f"status=[{', '.join(args.status)}]")
            if args.payment_method:
                filter_info.append(f"payment_method='{args.payment_method}'")

            if filter_info:
                print(f"\nFilters applied: {', '.join(filter_info)}")

            return 0

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return 1

    def _display_summary(self, subscriptions, status_counts, total_by_currency,
                         spend_by_status_currency, upcoming_renewals, expiring_days,
                         target_currency=None):
        """Display the summary information."""
        # Section divider
        divider = "=" * 60

        # Header
        print(f"\n{Fore.CYAN}{Style.BRIGHT}SUBSCRIPTION PORTFOLIO SUMMARY{Style.RESET_ALL}")
        print(divider)

        # Subscription counts
        print(f"{Fore.GREEN}Subscription Counts:{Style.RESET_ALL}")
        print(f"  Total Subscriptions: {Fore.YELLOW}{len(subscriptions)}{Style.RESET_ALL}")

        # Status counts
        status_parts = []
        for status in ["active", "trial", "expiring", "cancelled"]:
            if status_counts[status] > 0:
                color = self._get_status_color(status)
                status_parts.append(f"  {status}: {color}{status_counts[status]}{Style.RESET_ALL}")

        if status_parts:
            print("  By Status:")
            for part in status_parts:
                print(part)

        print(divider)

        # Total spend
        print(f"{Fore.GREEN}Financial Overview:{Style.RESET_ALL}")

        if target_currency and target_currency in self.EXCHANGE_RATES:
            # Convert all amounts to target currency
            total_in_target = 0
            for currency, amount in total_by_currency.items():
                if currency in self.EXCHANGE_RATES:
                    # First convert to USD, then to target currency
                    amount_in_usd = amount * self.EXCHANGE_RATES[currency]
                    amount_in_target = amount_in_usd / self.EXCHANGE_RATES[target_currency]
                    total_in_target += amount_in_target

            symbol = self._get_currency_symbol(target_currency)
            print(
                f"  Total Monthly Spend: {Fore.YELLOW}{symbol}{total_in_target:.2f} ({target_currency}){Style.RESET_ALL}")

            # Spending by status in target currency
            if any(status_counts.values()):
                print("  Spend by Status:")
                for status in ["active", "trial", "expiring", "cancelled"]:
                    if status in spend_by_status_currency and status_counts[status] > 0:
                        total_status_spend = 0
                        for currency, amount in spend_by_status_currency[status].items():
                            if currency in self.EXCHANGE_RATES:
                                amount_in_usd = amount * self.EXCHANGE_RATES[currency]
                                amount_in_target = amount_in_usd / self.EXCHANGE_RATES[target_currency]
                                total_status_spend += amount_in_target

                        color = self._get_status_color(status)
                        print(f"    {status}: {color}{symbol}{total_status_spend:.2f}{Style.RESET_ALL}")

        else:
            # Show totals by currency
            print("  Total Monthly Spend:")
            for currency, amount in sorted(total_by_currency.items()):
                symbol = self._get_currency_symbol(currency)
                print(f"    {Fore.YELLOW}{symbol}{amount:.2f} ({currency}){Style.RESET_ALL}")

            # Spending by status and currency (only if we have statuses with counts)
            shown_status_header = False
            for status in ["active", "trial", "expiring", "cancelled"]:
                if status in spend_by_status_currency and status_counts[status] > 0:
                    if not shown_status_header:
                        print("  Spend by Status:")
                        shown_status_header = True

                    color = self._get_status_color(status)
                    print(f"    {status}:")
                    for currency, amount in sorted(spend_by_status_currency[status].items()):
                        symbol = self._get_currency_symbol(currency)
                        print(f"      {color}{symbol}{amount:.2f} ({currency}){Style.RESET_ALL}")

        print(divider)

        # Renewals section
        print(f"{Fore.GREEN}Upcoming Activity:{Style.RESET_ALL}")
        renewal_color = Fore.RED if upcoming_renewals > 0 else Fore.YELLOW
        print(f"  Upcoming Renewals: {renewal_color}{upcoming_renewals} in next {expiring_days} days{Style.RESET_ALL}")

        # Calculate average cost if possible
        if len(subscriptions) > 0:
            if target_currency and target_currency in self.EXCHANGE_RATES:
                avg_cost = total_in_target / len(subscriptions)
                symbol = self._get_currency_symbol(target_currency)
                print(f"  Average Subscription Cost: {Fore.YELLOW}{symbol}{avg_cost:.2f}{Style.RESET_ALL}")
            else:
                # If more than one currency, don't show average
                if len(total_by_currency) == 1:
                    currency = list(total_by_currency.keys())[0]
                    avg_cost = total_by_currency[currency] / len(subscriptions)
                    symbol = self._get_currency_symbol(currency)
                    print(f"  Average Subscription Cost: {Fore.YELLOW}{symbol}{avg_cost:.2f}{Style.RESET_ALL}")
                else:
                    print("  Average Subscription Cost: (multiple currencies)")

    def _is_date_within_range(self, date_str, start_date, end_date):
        """Check if a date string is within a given date range."""
        try:
            # Parse the date string (assuming YYYY-MM-DD format)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()

            # Check if date is in range [start_date, end_date]
            return start_date <= date_obj <= end_date
        except (ValueError, TypeError):
            # Return False if date is invalid
            return False

    def _get_currency_symbol(self, currency_code):
        """Get the symbol for a currency code."""
        return self.CURRENCY_SYMBOLS.get(currency_code, currency_code)

    def _get_status_color(self, status):
        """Return appropriate color for a subscription status."""
        colors = {
            "active": Fore.GREEN,
            "trial": Fore.BLUE,
            "expiring": Fore.RED,
            "cancelled": Fore.YELLOW
        }
        return colors.get(status, Fore.WHITE)