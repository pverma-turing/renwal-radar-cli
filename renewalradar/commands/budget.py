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
            self.view_budgets(db_manager, year, month, args.currency)

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

    def view_budgets(self, db_manager, year=None, month=None, currency=None):
        """View all budgets with usage statistics."""
        budgets = db_manager.get_budgets(year, month, currency)

        if not budgets:
            print("No budgets found.")
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
            is_overspent = remaining < 0

            # Create row with color formatting
            row = [
                f"{month_name} {budget_year}",
                budget_currency,
                f"{budget_amount:.2f}",
                f"{utilized:.2f}",
                f"{Fore.RED}{remaining:.2f}{Style.RESET_ALL}" if is_overspent else f"{remaining:.2f}",
                f"{Fore.RED}{percent_used:.1f}%{Style.RESET_ALL}" if is_overspent else f"{percent_used:.1f}%",
                f"{Fore.RED}YES{Style.RESET_ALL}" if is_overspent else "NO"
            ]

            table_data.append(row)

        # Display the table
        headers = ["Month", "Currency", "Budget", "Utilized", "Remaining", "% Used", "Overspent?"]
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))