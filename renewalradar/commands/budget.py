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
        if args.set:
            if args.set <= 0:
                return False, "Budget amount must be positive"
            if not args.currency:
                return False, "Currency must be specified when setting a budget"
            if args.month and (args.month < 1 or args.month > 12):
                return False, "Month must be between 1 and 12"
        return True, ""

    def execute(self, args):
        """Execute the budget command."""
        db_manager = DatabaseManager()

        # Use current year/month if not specified
        current_date = datetime.datetime.now()
        year = args.year if args.year else current_date.year
        month = args.month if args.month else current_date.month

        if args.set:
           self.set_budget(db_manager, year, month, args.currency, args.set)
        elif args.view:
           self.view_budgets(db_manager, year, month, args.currency, args.detailed)

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

    def view_budgets(self, db_manager, year=None, month=None, currency=None, detailed=False):
        """View all budgets with usage statistics."""
        budgets = db_manager.get_budgets(year, month, currency)

        if not budgets:
            print("No budgets found.")
            return

        table_data = []
        current_date = datetime.datetime.now()
        current_month = current_date.month
        current_year = current_date.year

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

            row = [
                month_year,
                budget_currency,
                f"{budget_amount:.2f}",
                f"{utilized:.2f}",
                f"{Fore.RED}{remaining:.2f}{Style.RESET_ALL}" if is_overspent else f"{remaining:.2f}",
                f"{Fore.RED}{percent_used:.1f}%{Style.RESET_ALL}" if is_overspent else f"{percent_used:.1f}%",
                f"{Fore.RED}YES{Style.RESET_ALL}" if is_overspent else "NO",
                costs.get(f"{budget_currency}_count", 0)  # Number of subscriptions
            ]

            table_data.append(row)

            # Sort table - current month first, then by date (most recent first)
        table_data.sort(key=lambda x: (0 if "Current" in x[0] else 1, x[0]), reverse=True)

        # Display the table
        headers = ["Month", "Currency", "Budget", "Utilized", "Remaining", "% Used", "Overspent?", "# Subscriptions"]
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

        # Add a note about what's included in calculations
        print("\nNote:")
        print("- 'Utilized' includes all active (non-cancelled) subscriptions in the given month")
        print("- Calculations are based on subscription start and renewal dates")
        print("- All amounts are treated as monthly (no proration by billing cycle)")
        if not year and not month:
            print(f"- Current month is highlighted: {calendar.month_name[current_month]} {current_year}")

        # Show detailed subscription lists if requested
        if detailed:
            print("\nSubscriptions included in budget calculations:")
            print("=============================================")
            for budget in budgets:
                budget_year, budget_month, budget_currency, budget_amount = budget
                month_name = calendar.month_name[budget_month]

                # Get subscription costs and details for this budget period
                costs = db_manager.get_subscription_costs_by_budget_period(
                    budget_year, budget_month, budget_currency
                )

                # Get subscription details
                subscription_names = costs.get(f"{budget_currency}_details", [])
                count = costs.get(f"{budget_currency}_count", 0)
                utilized = costs.get(budget_currency, 0)

                print(
                    f"\n{month_name} {budget_year} - {budget_currency} ({count} subscriptions, total: {utilized:.2f}):")

                if subscription_names:
                    for i, name in enumerate(subscription_names, 1):
                        print(f"  {i}. {name}")
                else:
                    print("  No subscriptions found for this period.")

                print("-" * 50)