"""Utilities for subscription status management."""

# List of valid subscription statuses
VALID_STATUSES = ["active", "trial", "expiring", "cancelled"]

# Descriptions for each status
STATUS_DESCRIPTIONS = {
    "active": "currently ongoing subscription",
    "trial": "in trial period",
    "expiring": "about to end soon",
    "cancelled": "no longer active"
}


def validate_status(status):
    """
    Validate if a status is allowed.

    Args:
        status (str): Status value to validate

    Returns:
        bool: True if status is valid, False otherwise
    """
    return status in VALID_STATUSES


def get_status_error_message(invalid_status):
    """
    Generate a standardized error message for invalid status.

    Args:
        invalid_status (str): The invalid status that was provided

    Returns:
        str: Formatted error message
    """
    return f"Error: '{invalid_status}' is not a valid status. Allowed values: {', '.join(VALID_STATUSES)}."


def print_status_help():
    """Print help information about valid statuses."""
    print("Valid statuses:")
    for status in VALID_STATUSES:
        print(f"  {status:<8} – {STATUS_DESCRIPTIONS[status]}")