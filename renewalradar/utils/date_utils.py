"""
Date utility functions for RenewalRadar subscription manager.
Handles date parsing, validation, and calculations.
"""

import datetime
from dateutil.relativedelta import relativedelta
import re


def parse_date(date_str):
    """
    Parse a date string into a datetime object.
    Supports ISO format (YYYY-MM-DD) and other common formats.

    Args:
        date_str (str): Date string to parse

    Returns:
        datetime.datetime: Parsed datetime object

    Raises:
        ValueError: If the date format is invalid
    """
    # Try ISO format first (YYYY-MM-DD)
    try:
        return datetime.datetime.fromisoformat(date_str)
    except ValueError:
        pass

    # Try common formats
    formats = [
        '%Y-%m-%d',  # 2023-01-31
        '%d/%m/%Y',  # 31/01/2023
        '%m/%d/%Y',  # 01/31/2023
        '%d-%m-%Y',  # 31-01-2023
        '%m-%d-%Y',  # 01-31-2023
        '%d.%m.%Y',  # 31.01.2023
        '%m.%d.%Y',  # 01.31.2023
        '%B %d, %Y',  # January 31, 2023
        '%d %B %Y',  # 31 January 2023
    ]

    for date_format in formats:
        try:
            return datetime.datetime.strptime(date_str, date_format)
        except ValueError:
            continue

    # If we get here, none of the formats worked
    raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD format.")


def format_date(date_obj, format_str='%Y-%m-%d'):
    """
    Format a date object as a string.

    Args:
        date_obj (datetime.datetime): Date object to format
        format_str (str, optional): Format string. Defaults to ISO format.

    Returns:
        str: Formatted date string
    """
    return date_obj.strftime(format_str)


def calculate_next_renewal(start_date, billing_cycle):
    """
    Calculate the next renewal date based on start date and billing cycle.

    Args:
        start_date (datetime.datetime): The start date
        billing_cycle (str): Either 'monthly' or 'yearly'

    Returns:
        datetime.datetime: The next renewal date

    Raises:
        ValueError: If the billing cycle is invalid
    """
    if isinstance(start_date, str):
        start_date = parse_date(start_date)

    if billing_cycle.lower() == 'monthly':
        return start_date + relativedelta(months=1)
    elif billing_cycle.lower() == 'yearly':
        return start_date + relativedelta(years=1)
    else:
        raise ValueError(f"Invalid billing cycle: {billing_cycle}. Use 'monthly' or 'yearly'.")


def validate_date_format(date_str):
    """
    Validate if a string is in ISO date format (YYYY-MM-DD).

    Args:
        date_str (str): Date string to validate

    Returns:
        bool: True if valid ISO format, False otherwise
    """
    pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(pattern, date_str):
        return False

    # Check if it's a valid date
    try:
        datetime.datetime.fromisoformat(date_str)
        return True
    except ValueError:
        return False


def days_until_renewal(renewal_date):
    """
    Calculate the number of days until a renewal date.

    Args:
        renewal_date (str or datetime): The renewal date

    Returns:
        int: Number of days until renewal
    """
    if isinstance(renewal_date, str):
        renewal_date = parse_date(renewal_date)

    # Strip time component for accurate day calculation
    renewal_date = datetime.datetime(
        renewal_date.year, renewal_date.month, renewal_date.day
    )

    # Get today's date without time component
    today = datetime.datetime.now()
    today = datetime.datetime(today.year, today.month, today.day)

    # Calculate the difference in days
    delta = renewal_date - today
    return delta.days