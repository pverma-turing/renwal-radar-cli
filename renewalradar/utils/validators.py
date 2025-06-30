class ValidationRegistry:
    """Central registry for allowed values and validation functions."""

    # Define allowed payment methods
    VALID_PAYMENT_METHODS = [
        "Visa",
        "Mastercard",
        "PayPal",
        "BankTransfer",
        "UPI"
    ]

    # Define allowed tags
    VALID_TAGS = [
        "personal",
        "work",
        "shared",
        "family",
        "business"
    ]

    @classmethod
    def validate_payment_method(cls, payment_method):
        """Validate that payment method is allowed.

        Args:
            payment_method (str): Payment method to validate

        Returns:
            bool: True if valid, False otherwise

        Raises:
            ValueError: If payment method is not valid, with helpful error message
        """
        if not payment_method:
            return True  # Allow empty payment methods (will be set to None)

        if payment_method not in cls.VALID_PAYMENT_METHODS:
            allowed_methods = ", ".join(cls.VALID_PAYMENT_METHODS)
            raise ValueError(f"'{payment_method}' is not a supported payment method. Allowed: {allowed_methods}")

        return True

    @classmethod
    def validate_tag(cls, tag):
        """Validate a single tag.

        Args:
            tag (str): Tag to validate

        Returns:
            bool: True if valid, False otherwise

        Raises:
            ValueError: If tag is not valid, with helpful error message
        """
        if not tag:
            return False  # Empty tags are not valid

        if tag not in cls.VALID_TAGS:
            allowed_tags = ", ".join(cls.VALID_TAGS)
            raise ValueError(f"'{tag}' is not a supported tag. Allowed: {allowed_tags}")

        return True

    @classmethod
    def validate_tags(cls, tags):
        """Validate a list of tags.

        Args:
            tags (list): List of tags to validate

        Returns:
            bool: True if all tags are valid, False otherwise

        Raises:
            ValueError: If any tag is not valid, with helpful error message
        """
        if not tags:
            return True  # Allow empty tag list

        for tag in tags:
            cls.validate_tag(tag)

        return True

    @classmethod
    def print_valid_payment_methods(cls):
        """Print list of valid payment methods."""
        print("Valid payment methods:")
        for method in cls.VALID_PAYMENT_METHODS:
            print(f"  - {method}")

    @classmethod
    def print_valid_tags(cls):
        """Print list of valid tags."""
        print("Valid tags:")
        for tag in cls.VALID_TAGS:
            print(f"  - {tag}")

    @classmethod
    def print_tags_in_use(cls, db_manager):
        """Print list of tags currently in use.

        Args:
            db_manager: Instance of DatabaseManager
        """
        tags_in_use = db_manager.get_tag_usage()
        valid_tags = set(cls.VALID_TAGS)

        if not tags_in_use:
            print("No tags currently in use.")
            return

        print("Tags currently in use:")
        for tag, count in sorted(tags_in_use.items(), key=lambda x: (-x[1], x[0])):
            status = "✓" if tag in valid_tags else "!"
            print(f"  {status} {tag} ({count})")

        print("\nLegend: ✓ = valid tag, ! = custom/unregistered tag")

    @classmethod
    def print_payment_methods_in_use(cls, db_manager):
        """Print list of payment methods currently in use.

        Args:
            db_manager: Instance of DatabaseManager
        """
        methods_in_use = db_manager.get_payment_method_usage()
        valid_methods = set(cls.VALID_PAYMENT_METHODS)

        if not methods_in_use:
            print("No payment methods currently in use.")
            return

        print("Payment methods currently in use:")
        for method, count in sorted(methods_in_use.items(), key=lambda x: (-x[1], x[0])):
            status = "✓" if method in valid_methods else "!"
            print(f"  {status} {method} ({count})")

        print("\nLegend: ✓ = valid method, ! = custom/unregistered method")