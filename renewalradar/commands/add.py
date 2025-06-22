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


@register_command
class AddCommand(Command):
    """Command to add a new subscription."""

    name = 'add'
    description = 'Add a new subscription'

    @classmethod
    def register_arguments(cls, parser):
        """Register command-specific arguments."""
        parser.add_argument(
            '--name',
            required=True,
            help='Name of the subscription'
        )

        parser.add_argument(
            '--cost',
            required=True,
            type=float,
            help='Cost of the subscription'
        )

        parser.add_argument(
            '--billing-cycle',
            required=True,
            choices=['monthly', 'yearly'],
            help='Billing cycle (monthly or yearly)'
        )

        parser.add_argument(
            '--currency',
            required=True,
            help='Currency code (e.g., USD, EUR, GBP)'
        )

        parser.add_argument(
            '--start-date',
            required=True,
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
            help='Additional notes about the subscription'
        )

    def execute(self, args):
        """Execute the add command."""
        try:
            # Validate dates
            if not validate_date_format(args.start_date):
                print(f"Error: Invalid start date format. Use YYYY-MM-DD format.")
                return 1

            if args.renewal_date and not validate_date_format(args.renewal_date):
                print(f"Error: Invalid renewal date format. Use YYYY-MM-DD format.")
                return 1

            # Create subscription object
            subscription = Subscription(
                name=args.name,
                cost=args.cost,
                billing_cycle=args.billing_cycle,
                currency=args.currency,
                start_date=args.start_date,
                renewal_date=args.renewal_date,
                payment_method=args.payment_method,
                notes=args.notes
            )

            # Save to database
            db_manager = DatabaseManager()
            try:
                subscription_id = db_manager.add_subscription(subscription.to_dict())
                print(f"Subscription '{args.name}' added successfully (ID: {subscription_id}).")
                print(f"Next renewal: {subscription.renewal_date} ({subscription.days_until_renewal()} days from now)")
                return 0
            finally:
                db_manager.close()

        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return 1