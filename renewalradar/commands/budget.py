import datetime
import calendar
from colorama import Fore, Style
from tabulate import tabulate
from ..commands.base import Command
from ..database.manager import DatabaseManager
from ..registry import register_command


@register_command
class BudgetCommand(Command):
    """Command for managing monthly budget caps per currency."""
    name = "budget"
    description = "manage budget"

    def register_arguments(self, parser):
        """Configure argument parser for the budget command."""
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--set", type=float, help="Set a budget amount")
        group.add_argument("--view", action="store_true", help="View all budgets")

        parser.add_argument("--currency", type=str, help="Currency code (e.g., USD)")
        parser.add_argument("--year", type=int, help="Year for the budget (defaults to current year)")
        parser.add_argument("--month", type=int, help="Month for the budget (1-12, defaults to current month)")
        parser.add_argument("--detailed", action="store_true", help="Show detailed subscription list in budget view")

        return parser

    def validate_args(self, args):
        """Validate command arguments."""
        # Validate month is between 1-12 if provided
        if args.month is not None:
            if not isinstance(args.month, int) or args.month < 1 or args.month > 12:
                return False, f"Error: Month must be between 1 and 12, got {args.month}"

        # Validate year is reasonable if provided
        if args.year is not None:
            current_year = datetime.datetime.now().year
            if not isinstance(args.year, int) or args.year < 2000 or args.year > current_year + 10:
                return False, f"Error: Year {args.year} seems invalid (must be between 2000 and {current_year + 10})"

        # Validate set command specific arguments
        if args.set:
            if args.set <= 0:
                return False, "Budget amount must be positive"
            if not args.currency:
                return False, "Currency must be specified when setting a budget"

        return True, ""

    def execute(self, args):
        """Execute the budget command."""
        db_manager = DatabaseManager()

        # Get current date for defaults
        current_date = datetime.datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        # Set year and month based on arguments, defaulting to current if not specified
        year = args.year if args.year is not None else current_year
        month = args.month if args.month is not None else current_month

        # Track if we're using defaults or user-specified values
        using_default_year = args.year is None
        using_default_month = args.month is None

        if args.set:
            self.set_budget(db_manager, year, month, args.currency, args.set)
        elif args.view:
            # Pass the default flags to the view function so we can customize output
            self.view_budgets(
                db_manager,
                year=year,
                month=month,
                currency=args.currency,
                detailed=args.detailed,
                using_default_year=using_default_year,
                using_default_month=using_default_month
            )

    def set_budget(self, db_manager, year, month, currency, amount):
        """Set a budget for a specific month, year, and currency."""
        try:
            is_new = db_manager.set_budget(year, month, currency, amount)
            month_name = calendar.month_name[month]

            if is_new:
                print(f"Budget of {amount} {currency} set for {month_name} {year}")
            else:
                print(f"Budget for {month_name} {year} in {currency} updated to {amount}")
        except ValueError as e:
            print(f"Error: {e}")

    def view_budgets(self, db_manager, year=None, month=None, currency=None,
                     detailed=False, using_default_year=True, using_default_month=True, show_rates=False):
        """
        View all budgets with usage statistics.

        Args:
            db_manager: Database manager instance
            year: Filter by year (or None for all years)
            month: Filter by month (or None for all months)
            currency: Filter by currency (or None for all currencies)
            detailed: Show detailed subscription list
            using_default_year: Whether the year value is the default (current year)
            using_default_month: Whether the month value is the default (current month)
            show_rates: Whether to display exchange rates
        """
        # Get the current date for reference
        current_date = datetime.datetime.now()
        current_month = current_date.month
        current_year = current_date.year

        # Build a description of the filters being used
        filter_descriptions = []
        if year is not None:
            filter_descriptions.append(f"year={year}")
        if month is not None:
            filter_descriptions.append(f"month={calendar.month_name[month]}")
        if currency is not None:
            filter_descriptions.append(f"currency={currency}")

        filter_text = f" with filters: {', '.join(filter_descriptions)}" if filter_descriptions else ""

        # Get budgets with the specified filters
        budgets = db_manager.get_budgets(year, month, currency)

        if not budgets:
            # Provide a helpful message based on which filters were used
            if year is not None and month is not None:
                print(
                    f"No budgets found for {calendar.month_name[month]} {year}{' with currency ' + currency if currency else ''}.")
            elif month is not None:
                print(
                    f"No budgets found for {calendar.month_name[month]}{' with currency ' + currency if currency else ''}.")
            elif year is not None:
                print(f"No budgets found for year {year}{' with currency ' + currency if currency else ''}.")
            elif currency is not None:
                print(f"No budgets found for currency {currency}.")
            else:
                print("No budgets found.")

            print("\nTo create a budget, use:")
            print("  budget --set AMOUNT --currency CURRENCY [--month MONTH] [--year YEAR]")
            return

        table_data = []

        for budget in budgets:
            budget_year, budget_month, budget_currency, budget_amount = budget

            # Get subscription costs for this budget period
            costs = db_manager.get_subscription_costs_by_budget_period(
                budget_year, budget_month, budget_currency
            )

            # Get utilized amount (or 0 if no subscriptions in this currency)
            utilized = costs.get(budget_currency, 0)

            # Calculate remaining budget and percentage used
            remaining = budget_amount - utilized
            percent_used = (utilized / budget_amount) * 100 if budget_amount > 0 else 0

            # Format for display
            month_name = calendar.month_name[budget_month]

            # Determine if this is the current month
            is_current = (budget_month == current_month and budget_year == current_year)
            is_overspent = remaining < 0

            # Create row with color formatting
            # Highlight current month with a different color
            month_year = f"{month_name} {budget_year}"
            if is_current:
                month_year = f"{Fore.CYAN}{month_year} (Current){Style.RESET_ALL}"

            # Determine risk level based on percentage used
            is_at_risk = percent_used > 90.0 and percent_used <= 100.0

            # Format the Overspent status with appropriate risk labels
            if is_overspent:
                overspent_status = f"{Fore.RED}Yes [OVER]{Style.RESET_ALL}"
            elif is_at_risk:
                overspent_status = f"{Fore.YELLOW}No [RISK]{Style.RESET_ALL}"
            else:
                overspent_status = "No"

            # Format percentage with color based on risk
            if is_overspent:
                percent_display = f"{Fore.RED}{percent_used:.1f}%{Style.RESET_ALL}"
            elif is_at_risk:
                percent_display = f"{Fore.YELLOW}{percent_used:.1f}%{Style.RESET_ALL}"
            else:
                percent_display = f"{percent_used:.1f}%"

            # Format remaining amount
            if is_overspent:
                remaining_display = f"{Fore.RED}{remaining:.2f}{Style.RESET_ALL}"
            elif is_at_risk:
                remaining_display = f"{Fore.YELLOW}{remaining:.2f}{Style.RESET_ALL}"
            else:
                remaining_display = f"{remaining:.2f}"

            row = [
                month_year,
                budget_currency,
                f"{budget_amount:.2f}",
                f"{utilized:.2f}",
                remaining_display,
                percent_display,
                overspent_status,
                costs.get(f"{budget_currency}_count", 0)  # Number of subscriptions
            ]

            table_data.append(row)

        # Sort table - current month first, then by date (most recent first)
        table_data.sort(key=lambda x: (0 if "Current" in x[0] else 1, x[0]), reverse=True)

        # Create a title that includes filter information
        if month is not None and year is not None:
            title = f"Budget for {calendar.month_name[month]} {year}"
            if currency is not None:
                title += f" in {currency}"
        elif month is not None:
            title = f"Budget for {calendar.month_name[month]}" + (f" {year}" if year else "")
            if currency is not None:
                title += f" in {currency}"
        elif year is not None:
            title = f"Budgets for {year}"
            if currency is not None:
                title += f" in {currency}"
        elif currency is not None:
            title = f"All Budgets in {currency}"
        else:
            title = "All Budgets"

        # Show title with filter information
        print(f"\n{title}")
        print("=" * len(title))

        # Display the table
        headers = ["Month", "Currency", "Budget", "Utilized", "Remaining", "% Used", "Overspent?",
                   "# Subscriptions"]
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

        # Calculate totals in base currency (USD)
        total_budget_usd = 0
        total_utilized_usd = 0

        # Calculate totals in base currency
        for row in table_data:
            currency = row[1]
            budget = float(row[2])
            utilized = float(row[3])

            try:
                # Convert amounts to USD
                budget_usd = self._convert_currency(budget, currency, "USD")
                utilized_usd = self._convert_currency(utilized, currency, "USD")

                # Add to totals
                total_budget_usd += budget_usd
                total_utilized_usd += utilized_usd
            except ValueError:
                # Skip currencies that we don't have exchange rates for
                print(f"Warning: Skipping {currency} - no exchange rate available for conversion to USD")

        # Calculate remaining and percentage used
        total_remaining_usd = total_budget_usd - total_utilized_usd
        total_percent_used = (total_utilized_usd / total_budget_usd * 100) if total_budget_usd > 0 else 0

        # Determine if overspent
        is_overspent = total_remaining_usd < 0
        overspent_text = "Yes [OVER]" if is_overspent else "No"

        # Display total row
        print("\nTOTAL (USD): " +
              f"Budget = {total_budget_usd:.2f}, " +
              f"Utilized = {total_utilized_usd:.2f}, " +
              f"Remaining = {total_remaining_usd:.2f}, " +
              f"% Used = {total_percent_used:.2f}%, " +
              f"Overspent? = {overspent_text}")

        # Add a note about what's included in calculations
        print("\nNote:")
        print("- 'Utilized' includes all active (non-cancelled) subscriptions in the given month")
        print("- Calculations are based on subscription start and renewal dates")
        print("- All amounts are treated as monthly (no proration by billing cycle)")

        # Add note about current month highlighting
        if using_default_month and using_default_year:
            print(f"- Current month is highlighted: {calendar.month_name[current_month]} {current_year}")
        elif any("Current" in row[0] for row in table_data):
            print(f"- Current month is highlighted: {calendar.month_name[current_month]} {current_year}")

        # Mention filter usage
        if filter_descriptions:
            print(f"- Showing results {filter_text}")

        # Show detailed subscription lists if requested
        if detailed:
            detail_title = "Subscriptions included in budget calculations"
            print(f"\n{detail_title}")
            print("=" * len(detail_title))

            # If we're looking at a filtering by month/year/currency, make the header specific
            detail_header = ""
            if month is not None and year is not None:
                detail_header = f"Showing subscriptions for {calendar.month_name[month]} {year}"
                if currency is not None:
                    detail_header += f" in {currency}"
            elif currency is not None:
                detail_header = f"Showing subscriptions in {currency}"

            if detail_header:
                print(detail_header)
                print("-" * len(detail_header))

            # Sort budgets by date (most recent first)
            sorted_budgets = sorted(budgets, key=lambda b: (b[0], b[1]), reverse=True)

            # Process each budget
            for budget in sorted_budgets:
                budget_year, budget_month, budget_currency, budget_amount = budget
                month_name = calendar.month_name[budget_month]

                # Mark current month
                is_current = (budget_month == current_month and budget_year == current_year)
                month_display = f"{month_name} {budget_year}"
                if is_current:
                    month_display = f"{month_display} (Current)"

                # Get subscription costs and details for this budget period
                costs = db_manager.get_subscription_costs_by_budget_period(
                    budget_year, budget_month, budget_currency
                )

                # Get subscription details
                subscription_names = costs.get(f"{budget_currency}_details", [])
                count = costs.get(f"{budget_currency}_count", 0)
                utilized = costs.get(budget_currency, 0)

                # Format header with budget information
                header = f"\n{month_display} - {budget_currency}"
                print(f"{header}:")
                print(f"  Budget amount: {budget_amount:.2f}")
                print(f"  Utilized: {utilized:.2f} ({count} subscriptions)")
                remaining = budget_amount - utilized
                is_overspent = remaining < 0

                # Show overspent status with coloring
                if is_overspent:
                    print(f"  Remaining: {Fore.RED}{remaining:.2f} (OVERSPENT){Style.RESET_ALL}")
                else:
                    print(f"  Remaining: {remaining:.2f}")

                # Show subscription details
                print("\n  Subscriptions:")
                if subscription_names:
                    for i, name in enumerate(subscription_names, 1):
                        print(f"    {i}. {name}")
                else:
                    print("    No active subscriptions found for this period.")

                print("-" * 50)