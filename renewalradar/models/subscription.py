"""
Subscription model for RenewalRadar subscription manager.
Defines the Subscription class and related utilities.
"""

import datetime
from ..utils.date_utils import (
    parse_date, validate_date_format, calculate_next_renewal, days_until_renewal
)


class Subscription:
    """
    Class representing a subscription with validation and utility methods.
    """

    VALID_BILLING_CYCLES = ["monthly", "quarterly", "biannual", "annual"]
    VALID_STATUSES = ["active", "trial", "expiring", "cancelled"]

    def __init__(self, name, cost, billing_cycle, currency, start_date,
                 renewal_date=None, payment_method='', notes=None, status='active',
                 trial_end_date=None, parent_subscription_id=None, tags=None, id=None):
        """
        Initialize a new subscription.

        Args:
            name (str): The name of the subscription
            cost (float): The cost of the subscription
            billing_cycle (str): The billing cycle ('monthly' or 'yearly')
            currency (str): The currency code (e.g., 'USD', 'EUR')
            start_date (str): The start date in ISO format (YYYY-MM-DD)
            renewal_date (str, optional): The renewal date in ISO format
            payment_method (str, optional): The payment method
            notes (str, optional): Additional notes about the subscription
            status (str, optional): Subscription status ('active', 'cancelled', 'paused')
            trial_end_date (str, optional): Date when the trial period ends in ISO format
            parent_subscription_id (int, optional): ID of the parent subscription

        Raises:
            ValueError: If any of the required fields are invalid
        """
        self.name = name
        self.set_cost(cost)
        self.set_billing_cycle(billing_cycle)
        self.currency = currency
        self.set_start_date(start_date)

        # Set renewal date or calculate it if not provided
        if renewal_date:
            self.set_renewal_date(renewal_date)
        else:
            self.calculate_renewal_date()

        self.payment_method = payment_method
        self.notes = notes
        self.status = status
        self.trial_end_date = trial_end_date
        self.parent_subscription_id = parent_subscription_id

        # Set timestamps
        current_time = datetime.datetime.now().isoformat()
        self.created_at = current_time
        self.updated_at = current_time
        self.tags = tags if tags else []
        self.id = None

    def __str__(self):
        """String representation of subscription."""
        tags_str = f", tags: [{', '.join(self.tags)}]" if self.tags else ""
        payment_str = f", payment: {self.payment_method}" if self.payment_method else ""
        return f"{self.name} ({self.currency} {self.cost} {self.billing_cycle}, status: {self.status}{payment_str}{tags_str})"

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not value:
            raise ValueError("Subscription name cannot be empty")
        self._name = value

    @property
    def cost(self):
        return self._cost

    @cost.setter
    def cost(self, value):
        try:
            self._cost = float(value)
            if self._cost <= 0:
                raise ValueError("Cost must be a positive number")
        except ValueError:
            raise ValueError("Cost must be a valid number")

    @property
    def billing_cycle(self):
        return self._billing_cycle

    @billing_cycle.setter
    def billing_cycle(self, value):
        if value not in self.VALID_BILLING_CYCLES:
            raise ValueError(f"Billing cycle must be one of: {', '.join(self.VALID_BILLING_CYCLES)}")
        self._billing_cycle = value

    @property
    def currency(self):
        return self._currency

    @currency.setter
    def currency(self, value):
        self._currency = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value not in self.VALID_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(self.VALID_STATUSES)}")
        self._status = value

    @property
    def payment_method(self):
        return self._payment_method

    @payment_method.setter
    def payment_method(self, value):
        if not value:
            self._payment_method = None
        else:
            self._payment_method = value

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        if isinstance(value, str):
            # If tags is stored as a comma-separated string, convert to list
            self._tags = [tag.strip() for tag in value.split(',')] if value else []
        else:
            # Otherwise, assume it's already a list or None
            self._tags = value if value else []

    @property
    def tags_string(self):
        """Return tags as a comma-separated string for storage."""
        return ','.join(self.tags) if self.tags else ""

    @property
    def annual_cost(self):
        """Calculate annual cost based on billing cycle and cost."""
        multipliers = {
            "monthly": 12,
            "quarterly": 4,
            "biannual": 2,
            "annual": 1
        }
        return self.cost * multipliers.get(self.billing_cycle, 0)

    def set_cost(self, cost):
        """
        Set and validate the cost.

        Args:
            cost: The subscription cost

        Raises:
            ValueError: If the cost is negative or not a number
        """
        try:
            cost_float = float(cost)
        except (ValueError, TypeError):
            raise ValueError("Cost must be a number")

        if cost_float < 0:
            raise ValueError("Cost cannot be negative")

        self.cost = cost_float

    def set_billing_cycle(self, billing_cycle):
        """
        Set and validate the billing cycle.

        Args:
            billing_cycle (str): The billing cycle ('monthly' or 'yearly')

        Raises:
            ValueError: If the billing cycle is invalid
        """
        if billing_cycle.lower() not in self.VALID_BILLING_CYCLES:
            raise ValueError(
                f"Invalid billing cycle: {billing_cycle}. "
                f"Valid options are: {', '.join(self.VALID_BILLING_CYCLES)}"
            )

        self.billing_cycle = billing_cycle.lower()

    def set_start_date(self, start_date):
        """
        Set and validate the start date.

        Args:
            start_date (str): The start date in ISO format (YYYY-MM-DD)

        Raises:
            ValueError: If the start date format is invalid
        """
        if isinstance(start_date, str):
            if not validate_date_format(start_date):
                raise ValueError(
                    f"Invalid start date format: {start_date}. Use YYYY-MM-DD format."
                )
            self.start_date = start_date
        else:
            # If it's a datetime object, convert to ISO string
            self.start_date = start_date.isoformat().split('T')[0]

    def set_renewal_date(self, renewal_date):
        """
        Set and validate the renewal date.

        Args:
            renewal_date (str): The renewal date in ISO format (YYYY-MM-DD)

        Raises:
            ValueError: If the renewal date format is invalid
        """
        if isinstance(renewal_date, str):
            if not validate_date_format(renewal_date):
                raise ValueError(
                    f"Invalid renewal date format: {renewal_date}. Use YYYY-MM-DD format."
                )
            self.renewal_date = renewal_date
        else:
            # If it's a datetime object, convert to ISO string
            self.renewal_date = renewal_date.isoformat().split('T')[0]

    def calculate_renewal_date(self):
        """Calculate the renewal date based on start date and billing cycle."""
        start_date_obj = parse_date(self.start_date)
        renewal_date_obj = calculate_next_renewal(start_date_obj, self.billing_cycle)
        self.set_renewal_date(renewal_date_obj)

    def calculate_annual_cost(self):
        """
        Calculate the annual cost based on the billing cycle.

        Returns:
            float: The annual cost
        """
        if self.billing_cycle == 'monthly':
            return self.cost * 12
        return self.cost

    def days_until_renewal(self):
        """
        Calculate the number of days until the next renewal.

        Returns:
            int: Number of days until renewal
        """
        return days_until_renewal(self.renewal_date)

    def to_dict(self):
        """
        Convert the subscription to a dictionary for database storage.

        Returns:
            dict: Dictionary representation of the subscription
        """
        return {
            'name': self.name,
            'cost': self.cost,
            'billing_cycle': self.billing_cycle,
            'currency': self.currency,
            'start_date': self.start_date,
            'renewal_date': self.renewal_date,
            'payment_method': self.payment_method,
            'notes': self.notes,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'trial_end_date': self.trial_end_date,
            'parent_subscription_id': self.parent_subscription_id,
            'tags': self.tags_string
        }

    @classmethod
    def from_dict(cls, data):
        """
        Create a new Subscription from a dictionary.

        Args:
            data (dict): Dictionary containing subscription data

        Returns:
            Subscription: A new Subscription instance
        """
        # Create a new subscription with required fields
        subscription = cls(
            name=data['name'],
            cost=data['cost'],
            billing_cycle=data['billing_cycle'],
            currency=data['currency'],
            start_date=data['start_date'],
            renewal_date=data['renewal_date'],
            payment_method=data.get('payment_method', ''),
            notes=data.get('notes'),
            status=data.get('status', 'active'),
            trial_end_date=data.get('trial_end_date'),
            parent_subscription_id=data.get('parent_subscription_id'),
            tags=data.get("tags", ""),
        )
        if 'id' in data:
            subscription.id = data['id']

        # Set timestamps if available
        if 'created_at' in data:
            subscription.created_at = data['created_at']
        if 'updated_at' in data:
            subscription.updated_at = data['updated_at']

        return subscription
