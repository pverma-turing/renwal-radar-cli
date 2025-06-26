"""
AddCommand implementation for RenewalRadar subscription manager.
Handles adding new subscriptions from the command line.
"""

import argparse
import datetime
from dateutil.relativedelta import relativedelta
import sys

from .base import Command
from ..models.subscription import Subscription
from ..database.manager import DatabaseManager
from ..utils.date_utils import parse_date, validate_date_format

from renewalradar.registry import register_command
from ..utils.status_utils import print_status_help, VALID_STATUSES, get_status_error_message


@register_command
class AddCommand(Command):
    """Command to add a new subscription."""

    name = 'add'
    description = 'Add a new subscription'

    # List of supported currency codes
    SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'INR', 'CNY', 'HKD']

    # Valid billing cycles
    VALID_BILLING_CYCLES = ['monthly', 'yearly']

    @classmethod
    def register_arguments(cls, parser):
        """Register command-specific arguments."""
        parser.add_argument(
            '--name',
            required=False,
            help='Name of the subscription'
        )

        parser.add_argument(
            '--cost',
            required=False,
            type=str,  # Changed to str to handle custom validation
            help='Cost of the subscription (must be a positive number)'
        )

        parser.add_argument(
            '--billing-cycle',
            required=False,
            choices=cls.VALID_BILLING_CYCLES,
            help=f'Billing cycle ({" or ".join(cls.VALID_BILLING_CYCLES)})'
        )

        parser.add_argument(
            '--currency',
            required=False,
            help=f'Currency code ({", ".join(cls.SUPPORTED_CURRENCIES)})'
        )

        parser.add_argument(
            '--start-date',
            required=False,
            help='Start date (YYYY-MM-DD)'
        )

        parser.add_argument(
            '--renewal-date',
            help='Renewal date (YYYY-MM-DD) - calculated from start date if not provided'
        )

        parser.add_argument(
            '--payment-method',
            default='',
            help='Payment method used for this subscription'
        )

        parser.add_argument(
            '--notes',
            default=None,
            help='Additional notes or comments about the subscription (free text)'
        )

        parser.add_argument(
            '--trial-end-date',
            default=None,
            help='Date when the trial period ends (YYYY-MM-DD)'
        )

        parser.add_argument(
            '--linked-to',
            default=None,
            help='Name of the parent subscription to link this subscription to'
        )

        parser.add_argument(
            "--status",
            choices=Subscription.VALID_STATUSES,
            default="active",
            help="Current status of subscription (default: active)"
        )

        parser.add_argument(
            "--help-status",
            action="store_true",
            help="Show information about valid subscription statuses"
        )

        parser.add_argument(
            "--tag",
            action="append",
            dest="tags",
            help="Assign a tag to the subscription. Can be used multiple times for multiple tags."
        )

    def _validate_cost(self, cost_str):
        """
        Validate that cost is a positive number.

        Args:
            cost_str (str): Cost as a string

        Returns:
            float: Parsed cost value

        Raises:
            ValueError: If cost is invalid
        """
        try:
            cost = float(cost_str)
            if cost <= 0:
                raise ValueError("Cost must be a positive number")
            return cost
        except ValueError:
            raise ValueError(f"Invalid cost: '{cost_str}'. Cost must be a positive number.")

    def _validate_currency(self, currency):
        """
        Validate that currency is supported.

        Args:
            currency (str): Currency code

        Raises:
            ValueError: If currency is not supported
        """
        if currency.upper() not in self.SUPPORTED_CURRENCIES:
            raise ValueError(
                f"Unsupported currency: '{currency}'. "
                f"Supported currencies are: {', '.join(self.SUPPORTED_CURRENCIES)}"
            )
        return currency.upper()  # Normalize to uppercase

    def _validate_dates(self, start_date, renewal_date=None, trial_end_date=None):
        """
        Validate start_date, renewal_date and trial_end_date.

        Args:
            start_date (str): Start date as string
            renewal_date (str, optional): Renewal date as string
            trial_end_date (str, optional): Trial end date as string

        Returns:
            tuple: (start_date, renewal_date, trial_end_date) as strings

        Raises:
            ValueError: If dates are invalid or have invalid relationships
        """
        # Validate start_date format
        if not validate_date_format(start_date):
            raise ValueError(
                f"Invalid start date format: '{start_date}'. Use YYYY-MM-DD format."
            )

        start_date_obj = parse_date(start_date).date()
        renewal_date_obj = None
        trial_end_date_obj = None

        # If renewal_date is provided, validate it
        if renewal_date:
            if not validate_date_format(renewal_date):
                raise ValueError(
                    f"Invalid renewal date format: '{renewal_date}'. Use YYYY-MM-DD format."
                )

            renewal_date_obj = parse_date(renewal_date).date()

            if renewal_date_obj < start_date_obj:
                raise ValueError(
                    f"Renewal date ({renewal_date}) cannot be earlier than start date ({start_date})."
                )

        # If trial_end_date is provided, validate it
        if trial_end_date:
            if not validate_date_format(trial_end_date):
                raise ValueError(
                    f"Invalid trial end date format: '{trial_end_date}'. Use YYYY-MM-DD format."
                )

            trial_end_date_obj = parse_date(trial_end_date).date()

            # Trial end date should not be before start date
            if trial_end_date_obj < start_date_obj:
                raise ValueError(
                    f"Trial end date ({trial_end_date}) cannot be earlier than start date ({start_date})."
                )

            # If renewal date is provided, check relationship with trial end date
            if renewal_date_obj and trial_end_date_obj > renewal_date_obj:
                print(f"Warning: Trial end date ({trial_end_date}) is after renewal date ({renewal_date}).")

        return start_date, renewal_date, trial_end_date

    def _validate_notes(self, notes):
        """
        Process and validate notes.

        Args:
            notes (str): User provided notes

        Returns:
            str or None: Processed notes
        """
        if notes is None:
            return None

        # Trim whitespace but preserve content
        notes = notes.strip()

        # Return None if empty string after trimming
        if not notes:
            return None

        return notes

    def _find_parent_subscription(self, db_manager, parent_name):
        """
        Find a parent subscription by name.

        Args:
            db_manager (DatabaseManager): Database manager to use
            parent_name (str): Name of the parent subscription

        Returns:
            dict or None: Parent subscription if found, None otherwise
        """
        if not parent_name:
            return None

        # Get all subscriptions
        subscriptions = db_manager.get_all_subscriptions()

        # Find the subscription with the matching name
        for sub in subscriptions:
            if sub["name"].lower() == parent_name.lower():
                return sub

        return None

    def execute(self, args):
        """
        Execute the add command with enhanced validation.

        Args:
            args: Command line arguments

        Returns:
            int: Exit code (0 for success, 1 for errors)
        """
        try:
            # Check if help-status flag is set
            if args.help_status:
                print_status_help()
                return 0
            # Validate all input fields
            cost = self._validate_cost(args.cost)
            currency = self._validate_currency(args.currency)
            start_date, renewal_date, trial_end_date = self._validate_dates(
                args.start_date, args.renewal_date, args.trial_end_date
            )
            notes = self._validate_notes(args.notes)

            # Validate status
            if args.status not in VALID_STATUSES:
                print(get_status_error_message(args.status))
                return 1

            # Validate name is not empty
            if not args.name.strip():
                raise ValueError("Name cannot be empty")

            # Create database manager
            db_manager = DatabaseManager()
            try:
                # Find parent subscription if linked-to argument is provided
                parent_subscription_id = None
                parent_subscription_name = None

                if args.linked_to:
                    parent_sub = self._find_parent_subscription(db_manager, args.linked_to)
                    if parent_sub:
                        parent_subscription_id = parent_sub["id"]
                        parent_subscription_name = parent_sub["name"]
                    else:
                        raise ValueError(f"Parent subscription '{args.linked_to}' not found")

                # Create subscription object with validated data
                subscription_data = {
                    'name': args.name.strip(),
                    'cost': cost,
                    'billing_cycle': args.billing_cycle,
                    'currency': currency,
                    'start_date': start_date,
                    'payment_method': args.payment_method.strip() if args.payment_method else '',
                    'status': args.status,
                    'notes': notes,
                    'trial_end_date': trial_end_date,
                    'parent_subscription_id': parent_subscription_id,
                    'tags': args.tags
                }

                # Add renewal_date if provided
                if renewal_date:
                    subscription_data['renewal_date'] = renewal_date

                subscription = Subscription(**subscription_data)

                # Save to database
                subscription_id = db_manager.add_subscription(subscription.to_dict())

                # Display success feedback
                print(f"\nSubscription '{args.name}' added successfully (ID: {subscription_id}).")
                print(f"Details:")
                print(f"  Cost: {cost:.2f} {currency} ({args.billing_cycle})")
                print(f"  Start Date: {start_date}")
                print(f"  Renewal Date: {subscription.renewal_date}")
                print(f"  Days until renewal: {subscription.days_until_renewal()}")

                # Display trial information if provided
                if trial_end_date:
                    today = datetime.datetime.now().date()
                    trial_end_date_obj = parse_date(trial_end_date).date()
                    days_until_trial_end = (trial_end_date_obj - today).days

                    trial_status = ""
                    if days_until_trial_end < 0:
                        trial_status = " (expired)"
                    elif days_until_trial_end == 0:
                        trial_status = " (expires today)"
                    else:
                        trial_status = f" ({days_until_trial_end} days remaining)"

                    print(f"  Trial End Date: {trial_end_date}{trial_status}")

                # Display parent subscription if linked
                if parent_subscription_id:
                    print(f"  Linked to: {parent_subscription_name} (ID: {parent_subscription_id})")

                if args.billing_cycle == 'monthly':
                    print(f"  Annual cost: {subscription.calculate_annual_cost():.2f} {currency}")

                # Display notes if provided
                if notes:
                    print(f"  Notes: {notes}")

                return 0
            finally:
                db_manager.close()

        except ValueError as e:
            # Display clear error message for validation errors
            print(f"Error: {e}")
            return 1
        except Exception as e:
            # Catch-all for unexpected errors
            print(f"An unexpected error occurred: {e}")
            return 1