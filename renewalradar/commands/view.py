"""
ViewCommand implementation for RenewalRadar subscription manager.
Handles displaying subscriptions from the command line.
"""

import datetime
import shutil

from colorama import init, Fore, Style

from renewalradar.commands.base import Command
from renewalradar.database.manager import DatabaseManager
from renewalradar.registry import register_command
from renewalradar.utils.date_utils import days_until_renewal, parse_date

# Initialize colorama for cross-platform color support
init()
@register_command
class ViewCommand(Command):
    """Command to view subscriptions with enhanced formatting and filtering."""

    name = 'view'
    description = 'View all subscriptions'

    # Color constants for better readability
    COLORS = {
        'OVERDUE': Fore.RED,
        'DUE_SOON': Fore.YELLOW,
        'NORMAL': Fore.WHITE,
        'TRIAL': Fore.CYAN,
        'HEADER': Fore.CYAN + Style.BRIGHT,
        'NOTES': Fore.GREEN,
        'PARENT': Fore.MAGENTA,
        'TREE_LINE': Fore.BLUE,
        'RESET': Style.RESET_ALL,
    }

    # Days thresholds for highlighting
    DUE_SOON_THRESHOLD = 7  # Days

    # Symbols for tree display
    INDENT_SYMBOL = "  ↳ "  # For tabular view
    TREE_BRANCH = "↳ "  # For dependency tree view

    # Sample exchange rates (base: USD)
    # Format: {'CURRENCY_CODE': rate_against_USD}
    EXCHANGE_RATES = {
        'USD': 1.00,
        'EUR': 0.85,
        'GBP': 0.74,
        'JPY': 113.50,
        'CAD': 1.25,
        'AUD': 1.35,
        'CHF': 0.92,
        'INR': 74.50,
        'CNY': 6.39,
        'HKD': 7.78,
        # Add more currencies as needed
    }

    @classmethod
    def register_arguments(cls, parser):
        """Register command-specific arguments."""
        parser.add_argument(
            '--sort',
            choices=['name', 'cost', 'renewal_date', 'billing_cycle', 'days', 'trial_end_date', 'parent'],
            help='Sort subscriptions by the specified field (ignored when using --show-dependency-tree)'
        )

        parser.add_argument(
            '--status',
            choices=['all', 'upcoming', 'overdue', 'trial'],
            default='all',
            help='Filter subscriptions by status: all (default), upcoming (next 30 days), '
                 'overdue, or trial (active trials)'
        )

        parser.add_argument(
            '--currency',
            choices=list(cls.EXCHANGE_RATES.keys()),
            help=f'Convert and display costs in the specified currency'
        )

        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of subscriptions displayed'
        )

        # Display format options - make these mutually exclusive
        display_group = parser.add_mutually_exclusive_group()

        display_group.add_argument(
            '--flat',
            action='store_true',
            help='Display subscriptions in a flat list (no parent-child indentation)'
        )

        display_group.add_argument(
            '--show-dependency-tree',
            action='store_true',
            help='Display subscriptions as a parent-child dependency tree'
        )

    def execute(self, args):
        """Execute the view command with enhanced output and filtering."""
        try:
            db_manager = DatabaseManager()
            try:
                # Get all subscriptions first
                subscriptions = db_manager.get_all_subscriptions()

                if not subscriptions:
                    print("No subscriptions found.")
                    return 0

                # Build parent-child relationships
                subscriptions = self._build_subscription_hierarchy(subscriptions)

                # Enhance subscriptions with calculated fields and currency conversion
                enhanced_subscriptions = self._enhance_subscriptions(subscriptions, target_currency=args.currency)

                # Apply status filtering
                filtered_subscriptions = self._filter_by_status(enhanced_subscriptions, args.status)

                if not filtered_subscriptions:
                    status_message = "No subscriptions found"
                    if args.status != 'all':
                        status_message += f" with status: {args.status}"
                    print(status_message + ".")
                    return 0

                # Store total count before applying limit
                total_subscription_count = len(filtered_subscriptions)

                # Choose display format based on flags
                if args.show_dependency_tree:
                    # Build and display dependency tree
                    self._display_dependency_tree(
                        filtered_subscriptions,
                        target_currency=args.currency,
                        limit=args.limit
                    )
                else:
                    # Apply sorting (if specified)
                    sorted_subscriptions = self._sort_subscriptions(
                        filtered_subscriptions, args.sort, target_currency=args.currency
                    )

                    # Apply limit (if specified)
                    limited_subscriptions = sorted_subscriptions
                    if args.limit is not None and args.limit > 0:
                        limited_subscriptions = sorted_subscriptions[:args.limit]

                    # Organize subscriptions into hierarchy for display
                    if args.flat:
                        display_subscriptions = limited_subscriptions
                    else:
                        display_subscriptions = self._organize_hierarchical_display(limited_subscriptions)

                    # Display the subscriptions in a nicely formatted table
                    self._display_subscriptions(
                        display_subscriptions,
                        target_currency=args.currency,
                        flat_view=args.flat
                    )

                    # Show limit message if applicable
                    if args.limit is not None and args.limit > 0 and args.limit < total_subscription_count:
                        print(
                            f"\nShowing first {len(limited_subscriptions)} of {total_subscription_count} subscriptions.")

                # Display summary information (based on full filtered set, not the limited display set)
                self._display_summary(filtered_subscriptions, status=args.status, target_currency=args.currency)
                return 0
            finally:
                db_manager.close()

        except Exception as e:
            print(f"An error occurred: {e}")
            return 1

    def _build_subscription_hierarchy(self, subscriptions):
        """
        Build parent-child relationships between subscriptions.

        Args:
            subscriptions (list): List of subscription dictionaries

        Returns:
            list: Enhanced subscriptions with parent-child information
        """
        # Create a map of subscription ID to subscription
        sub_map = {sub['id']: sub for sub in subscriptions}

        # Add parent name and children list to each subscription
        for sub in subscriptions:
            # Initialize children list
            sub['children'] = []

            # Set parent name if subscription has a parent
            parent_id = sub.get('parent_subscription_id')
            if parent_id and parent_id in sub_map:
                sub['parent_name'] = sub_map[parent_id]['name']
            else:
                sub['parent_name'] = None
                sub['parent_subscription_id'] = None  # Clear invalid parent references

        # Populate children lists
        for sub in subscriptions:
            parent_id = sub.get('parent_subscription_id')
            if parent_id and parent_id in sub_map:
                parent = sub_map[parent_id]
                parent['children'].append(sub['id'])

        return subscriptions

    def _build_tree_structure(self, subscriptions):
        """
        Build a hierarchical tree structure for dependency tree display.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries

        Returns:
            dict: Tree structure with parent IDs as keys and lists of child subscriptions as values
            list: List of root subscriptions (no parent)
        """
        # Create a map of subscription ID to subscription
        sub_map = {sub['id']: sub for sub in subscriptions}

        # Create a tree structure where keys are parent IDs and values are lists of child subscriptions
        tree = {}
        # Find root subscriptions (those with no parent)
        roots = []

        for sub in subscriptions:
            parent_id = sub.get('parent_subscription_id')

            if parent_id is None:
                # This is a root subscription
                roots.append(sub)
            else:
                # This is a child subscription
                if parent_id not in tree:
                    tree[parent_id] = []
                tree[parent_id].append(sub)

        # Sort roots alphabetically by name
        roots.sort(key=lambda s: s['name'].lower())

        # Sort children in each branch alphabetically
        for parent_id in tree:
            tree[parent_id].sort(key=lambda s: s['name'].lower())

        return tree, roots

    def _convert_currency(self, amount, from_currency, to_currency):
        """
        Convert an amount from one currency to another using exchange rates.

        Args:
            amount (float): The amount to convert
            from_currency (str): Source currency code
            to_currency (str): Target currency code

        Returns:
            float: Converted amount

        Raises:
            ValueError: If currency codes are not supported
        """
        # If currencies are the same or no target currency, no conversion needed
        if from_currency == to_currency or not to_currency:
            return amount

        # Check if both currencies are supported
        if from_currency not in self.EXCHANGE_RATES:
            raise ValueError(f"Unsupported source currency: {from_currency}")
        if to_currency not in self.EXCHANGE_RATES:
            raise ValueError(f"Unsupported target currency: {to_currency}")

        # Convert to USD first (as base currency), then to target currency
        amount_in_usd = amount / self.EXCHANGE_RATES[from_currency]
        return amount_in_usd * self.EXCHANGE_RATES[to_currency]

    def _enhance_subscriptions(self, subscriptions, target_currency=None):
        """
        Enhance subscriptions with additional calculated fields.

        Args:
            subscriptions (list): List of subscription dictionaries
            target_currency (str, optional): Currency to convert costs to

        Returns:
            list: Enhanced subscription dictionaries
        """
        today = datetime.datetime.now().date()
        enhanced = []

        for sub in subscriptions:
            # Calculate days until renewal
            days = days_until_renewal(sub["renewal_date"])

            # Parse trial end date if exists
            trial_end_date_obj = None
            days_until_trial_end = None
            is_in_trial = False

            if sub.get("trial_end_date"):
                trial_end_date_obj = parse_date(sub["trial_end_date"]).date()
                days_until_trial_end = (trial_end_date_obj - today).days
                is_in_trial = days_until_trial_end >= 0  # Trial is active if end date is today or in future

            # Determine status for coloring
            if is_in_trial:
                status = "TRIAL"
            elif days < 0:
                status = "OVERDUE"
            elif days <= self.DUE_SOON_THRESHOLD:
                status = "DUE_SOON"
            else:
                status = "NORMAL"

            # Create enhanced subscription with additional fields
            enhanced_sub = {**sub}  # Create a copy
            enhanced_sub["days_until_renewal"] = days
            enhanced_sub["status"] = status
            enhanced_sub["is_in_trial"] = is_in_trial
            enhanced_sub["days_until_trial_end"] = days_until_trial_end

            # Handle currency conversion
            enhanced_sub["original_currency"] = sub["currency"]
            enhanced_sub["original_cost"] = sub["cost"]

            # Convert cost if target currency is specified
            if target_currency:
                try:
                    enhanced_sub["converted_cost"] = self._convert_currency(
                        sub["cost"], sub["currency"], target_currency
                    )
                    enhanced_sub["display_currency"] = target_currency
                    enhanced_sub["is_converted"] = (sub["currency"] != target_currency)
                except ValueError as e:
                    # If conversion fails, use original currency
                    enhanced_sub["converted_cost"] = sub["cost"]
                    enhanced_sub["display_currency"] = sub["currency"]
                    enhanced_sub["is_converted"] = False
                    print(f"Warning: {e}. Using original currency for {sub['name']}.")
            else:
                # Use original currency if no target specified
                enhanced_sub["converted_cost"] = sub["cost"]
                enhanced_sub["display_currency"] = sub["currency"]
                enhanced_sub["is_converted"] = False

            # Add parsed dates for easier handling
            enhanced_sub["start_date_obj"] = parse_date(sub["start_date"]).date()
            enhanced_sub["renewal_date_obj"] = parse_date(sub["renewal_date"]).date()

            if trial_end_date_obj:
                enhanced_sub["trial_end_date_obj"] = trial_end_date_obj

            # Ensure notes is a string (even if None)
            if enhanced_sub["notes"] is None:
                enhanced_sub["notes"] = ""

            # Ensure trial_end_date is a string (even if None)
            if "trial_end_date" not in enhanced_sub or enhanced_sub["trial_end_date"] is None:
                enhanced_sub["trial_end_date"] = ""

            # Set display name for indented view
            if enhanced_sub["parent_subscription_id"] is not None:
                enhanced_sub["display_name"] = f"{self.INDENT_SYMBOL}{enhanced_sub['name']}"
            else:
                enhanced_sub["display_name"] = enhanced_sub["name"]

            enhanced.append(enhanced_sub)

        return enhanced

    def _filter_by_status(self, subscriptions, status):
        """
        Filter subscriptions by specified status.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            status (str): One of 'all', 'upcoming', 'overdue', 'trial'

        Returns:
            list: Filtered subscription dictionaries
        """
        if status == 'all':
            return subscriptions

        today = datetime.datetime.now().date()
        thirty_days_from_now = today + datetime.timedelta(days=30)

        if status == 'upcoming':
            return [
                sub for sub in subscriptions
                if today <= sub["renewal_date_obj"] <= thirty_days_from_now
            ]

        if status == 'overdue':
            return [
                sub for sub in subscriptions
                if sub["renewal_date_obj"] < today
            ]

        if status == 'trial':
            return [
                sub for sub in subscriptions
                if sub["is_in_trial"]
            ]

        return subscriptions  # Fallback

    def _sort_subscriptions(self, subscriptions, sort_by, target_currency=None):
        """
        Sort subscriptions by the specified field.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            sort_by (str): Field to sort by
            target_currency (str, optional): Currency being used for display

        Returns:
            list: Sorted subscription dictionaries
        """
        if not sort_by:
            # Default sort by parent first, then name
            return sorted(
                subscriptions,
                key=lambda s: (
                    s.get("parent_subscription_id") is not None,  # Parents first
                    s.get("parent_subscription_id") or 0,  # Group by parent
                    s["name"].lower()  # Then by name
                )
            )

        # Map sort fields to their key functions
        sort_keys = {
            'name': lambda s: s["name"].lower(),
            'cost': lambda s: s["converted_cost"],
            'renewal_date': lambda s: s["renewal_date_obj"],
            'billing_cycle': lambda s: s["billing_cycle"],
            'days': lambda s: s["days_until_renewal"],
            'trial_end_date': lambda s: s.get("trial_end_date_obj") or datetime.date.max,
            'parent': lambda s: (s.get("parent_name") or "").lower()
        }

        key_function = sort_keys.get(sort_by, lambda s: s["name"].lower())
        return sorted(subscriptions, key=key_function)

    def _organize_hierarchical_display(self, subscriptions):
        """
        Organize subscriptions for hierarchical display.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries

        Returns:
            list: Reorganized subscriptions for display
        """
        # Create a map of subscription ID to subscription
        sub_map = {sub['id']: sub for sub in subscriptions}

        # Find all root subscriptions (no parent)
        root_subs = [sub for sub in subscriptions if sub['parent_subscription_id'] is None]

        # Create a display list with parents followed by their children
        display_list = []
        for parent in root_subs:
            # Add parent to display list
            display_list.append(parent)

            # Add all children
            for child_id in parent.get('children', []):
                if child_id in sub_map:
                    child = sub_map[child_id]
                    if child in subscriptions:  # Make sure child passed any filters
                        display_list.append(child)

        # Add any remaining subscriptions (in case of orphaned children due to filtering)
        remaining = [sub for sub in subscriptions if sub not in display_list]
        display_list.extend(remaining)

        return display_list

    def _display_dependency_tree(self, subscriptions, target_currency=None, limit=None):
        """
        Display subscriptions as a parent-child dependency tree.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            target_currency (str, optional): Currency to display costs in
            limit (int, optional): Maximum number of root subscriptions to show
        """
        if not subscriptions:
            return

        # Build tree structure
        tree, roots = self._build_tree_structure(subscriptions)

        # Create a map of subscription ID to subscription
        sub_map = {sub['id']: sub for sub in subscriptions}

        # Print message regarding currency conversion if applicable
        if target_currency:
            print(f"\nDisplaying costs in {target_currency} (converted values marked with *)")
            print()  # Empty line for better spacing
        else:
            print()  # Empty line for better spacing

        # Apply limit if specified
        display_roots = roots
        total_count = len(roots)
        if limit is not None and limit > 0 and limit < len(roots):
            display_roots = roots[:limit]

        # Print each root subscription and its children recursively
        for root in display_roots:
            self._print_tree_node(root, tree, sub_map, target_currency)

        # Show limit message if applicable
        if limit is not None and limit > 0 and limit < total_count:
            print(f"\nShowing first {len(display_roots)} of {total_count} root subscriptions.")

    def _format_cost_for_tree(self, sub, target_currency=None):
        """
        Format cost string for tree display.

        Args:
            sub (dict): Subscription dictionary
            target_currency (str, optional): Target currency for conversion

        Returns:
            str: Formatted cost string
        """
        cost = sub["converted_cost"]
        currency = sub["display_currency"]
        is_converted = sub.get("is_converted", False)

        # Format with currency code
        cost_str = f"{cost:.2f} {currency}"

        # Add marker if converted
        if is_converted:
            cost_str += "*"

        return cost_str

    def _print_tree_node(self, subscription, tree, sub_map, target_currency=None, level=0, prefix=""):
        """
        Print a node in the dependency tree and its children recursively.

        Args:
            subscription (dict): Current subscription dictionary
            tree (dict): Tree structure of parent ID to list of child subscriptions
            sub_map (dict): Map of subscription ID to subscription
            target_currency (str, optional): Currency to display costs in
            level (int): Current nesting level (0 for roots)
            prefix (str): Prefix string for indentation
        """
        # Get color for this subscription
        color = self.COLORS[subscription["status"]]

        # Format cost
        cost_str = self._format_cost_for_tree(subscription, target_currency)

        # Format status indicators
        status_indicators = []

        if subscription["is_in_trial"]:
            days = subscription["days_until_trial_end"]
            trial_indicator = f"[TRIAL: {days} day{'s' if days != 1 else ''} left]"
            status_indicators.append(self.COLORS["TRIAL"] + trial_indicator + self.COLORS["RESET"])

        if subscription["days_until_renewal"] < 0:
            days = abs(subscription["days_until_renewal"])
            overdue_indicator = f"[OVERDUE: {days} day{'s' if days != 1 else ''}]"
            status_indicators.append(self.COLORS["OVERDUE"] + overdue_indicator + self.COLORS["RESET"])
        elif subscription["days_until_renewal"] <= self.DUE_SOON_THRESHOLD:
            days = subscription["days_until_renewal"]
            due_soon_indicator = f"[DUE SOON: {days} day{'s' if days != 1 else ''}]"
            status_indicators.append(self.COLORS["DUE_SOON"] + due_soon_indicator + self.COLORS["RESET"])

        # Append any notes
        if subscription["notes"]:
            notes_indicator = f"[NOTE: {subscription['notes'][:30]}{'...' if len(subscription['notes']) > 30 else ''}]"
            status_indicators.append(self.COLORS["NOTES"] + notes_indicator + self.COLORS["RESET"])

        # Format status string
        status_str = " ".join(status_indicators)

        # Print the current subscription with appropriate indentation
        if level == 0:
            # Root level (no indentation or arrow)
            print(f"{color}{subscription['name']}{self.COLORS['RESET']} ({cost_str}) {status_str}")
        else:
            # Child level (indented with arrow)
            branch = self.COLORS["TREE_LINE"] + self.TREE_BRANCH + self.COLORS["RESET"]
            print(f"{prefix}{branch}{color}{subscription['name']}{self.COLORS['RESET']} ({cost_str}) {status_str}")

        # Find children of this subscription
        subscription_id = subscription["id"]
        if subscription_id in tree and tree[subscription_id]:
            # Calculate new prefix for children
            new_prefix = prefix + "  "

            # Print all children recursively
            for child in tree[subscription_id]:
                self._print_tree_node(child, tree, sub_map, target_currency, level + 1, new_prefix)

    def _get_terminal_width(self):
        """
        Get the terminal width for display formatting.

        Returns:
            int: Terminal width or default width
        """
        terminal_size = shutil.get_terminal_size((80, 20))  # Default to 80x20
        return terminal_size.columns

    def _truncate_text(self, text, max_width):
        """
        Truncate text to fit within max_width.

        Args:
            text (str): Text to truncate
            max_width (int): Maximum width

        Returns:
            str: Truncated text
        """
        if len(text) > max_width:
            return text[:max_width - 3] + "..."
        return text

    def _calculate_column_widths(self, subscriptions, target_currency=None, flat_view=False):
        """
        Calculate optimal column widths based on data and terminal width.

        Args:
            subscriptions (list): List of subscriptions
            target_currency (str, optional): Target currency for display
            flat_view (bool): Whether to use flat view (no indentation)

        Returns:
            dict: Column width configuration
        """
        # Get terminal width
        terminal_width = self._get_terminal_width()

        # Define minimum column widths
        min_widths = {
            "name": 10,
            "cost": 8,
            "currency": 3,
            "cycle": 6,
            "start_date": 10,
            "renewal_date": 10,
            "trial_end": 10,
            "parent": 10,
            "payment": 8,
            "days": 5,
            "notes": 8
        }

        # Calculate max content lengths
        # For name, consider indentation in hierarchical view
        name_field = "display_name" if not flat_view else "name"
        max_name_width = max([len(s[name_field]) for s in subscriptions])

        # For cost, consider the conversion format
        max_cost_width = max([
            len(f"{s['converted_cost']:.2f}") +
            (3 if s['is_converted'] else 0)  # Add space for * if converted
            for s in subscriptions
        ])

        max_widths = {
            "name": max(min_widths["name"], max_name_width),
            "cost": max(min_widths["cost"], max_cost_width),
            "currency": max(min_widths["currency"], max([len(s["display_currency"]) for s in subscriptions])),
            "cycle": max(min_widths["cycle"], max([len(s["billing_cycle"]) for s in subscriptions])),
            "start_date": min_widths["start_date"],  # Fixed width for dates
            "renewal_date": min_widths["renewal_date"],  # Fixed width for dates
            "trial_end": min_widths["trial_end"],  # Fixed width for dates
            "parent": max(min_widths["parent"], max([len(s.get("parent_name") or "—") for s in subscriptions])),
            "payment": max(min_widths["payment"], max([len(s["payment_method"] or "N/A") for s in subscriptions])),
            "days": min_widths["days"],  # Fixed width for days
            "notes": max(min_widths["notes"], min(15, max([len(s["notes"]) for s in subscriptions])))  # Cap at 15 chars
        }

        # Calculate total width needed
        spacers = len(min_widths) + 1  # +1 for edge
        total_width = sum(max_widths.values()) + spacers

        # Adjust widths if terminal is too narrow
        if total_width > terminal_width:
            # Define priorities for shrinking columns (higher = less important)
            priorities = {
                "name": 4,  # Name is important but can be shortened
                "payment": 2,
                "cost": 5,
                "cycle": 3,
                "currency": 3,
                "start_date": 4,
                "renewal_date": 4,
                "trial_end": 4,
                "parent": 3,
                "days": 6,
                "notes": 1  # Notes can be shrunk first
            }

            # Sort columns by priority
            columns_by_priority = sorted(max_widths.keys(), key=lambda k: priorities.get(k, 0))

            # Reduce widths until we fit
            excess_width = total_width - terminal_width
            for col in columns_by_priority:
                if excess_width <= 0:
                    break

                reducible = max(0, max_widths[col] - min_widths[col])
                reduction = min(reducible, excess_width)
                max_widths[col] -= reduction
                excess_width -= reduction

        return max_widths

    def _format_cost(self, subscription, width):
        """
        Format a cost value for display, handling currency conversion.

        Args:
            subscription (dict): Enhanced subscription with cost info
            width (int): Column width to fit

        Returns:
            str: Formatted cost string
        """
        cost = subscription["converted_cost"]
        currency = subscription["display_currency"]
        is_converted = subscription.get("is_converted", False)

        # Format the cost with 2 decimal places
        cost_str = f"{cost:.2f}"

        # Add an asterisk if the cost was converted
        if is_converted:
            cost_str = f"{cost_str}*"

        return cost_str

    def _display_subscriptions(self, subscriptions, target_currency=None, flat_view=False):
        """
        Display subscriptions in a nicely formatted table with color highlighting.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            target_currency (str, optional): Currency to display costs in
            flat_view (bool): Whether to use flat view (no indentation)
        """
        if not subscriptions:
            return

        # Calculate optimal column widths
        widths = self._calculate_column_widths(subscriptions, target_currency, flat_view)

        # Print header
        header = (
            f"{self.COLORS['HEADER']}{'NAME':<{widths['name']}} "
            f"{'COST':<{widths['cost']}} "
            f"{'CUR':<{widths['currency']}} "
            f"{'CYCLE':<{widths['cycle']}} "
            f"{'START':<{widths['start_date']}} "
            f"{'RENEWAL':<{widths['renewal_date']}} "
            f"{'TRIAL END':<{widths['trial_end']}} "
            f"{'PARENT':<{widths['parent']}} "
            f"{'PAYMENT':<{widths['payment']}} "
            f"{'DAYS':<{widths['days']}} "
            f"{'NOTES':<{widths['notes']}}{self.COLORS['RESET']}"
        )
        print("\n" + header)
        print("-" * len(header.replace(self.COLORS['HEADER'], '').replace(self.COLORS['RESET'], '')))

        # Print message regarding currency conversion if applicable
        if target_currency:
            print(f"Displaying costs in {target_currency} (converted values marked with *)")

        # Print each subscription
        for sub in subscriptions:
            # Get the appropriate color based on status
            color = self.COLORS[sub["status"]]

            # Get days string with sign for overdue
            days = sub["days_until_renewal"]
            if days < 0:
                days_str = f"{days}"  # Negative number for overdue
            else:
                days_str = f"{days}"

            # Format each field with truncation if needed
            # Use display_name for hierarchical view, regular name for flat view
            name_field = "display_name" if not flat_view else "name"
            name = self._truncate_text(sub[name_field], widths['name'])
            payment = self._truncate_text(sub['payment_method'] or 'N/A', widths['payment'])
            notes = self._truncate_text(sub['notes'] or '-', widths['notes'])
            trial_end = sub['trial_end_date'] or "—"  # Display dash if no trial end date
            cost_str = self._format_cost(sub, widths['cost'])
            parent = sub.get('parent_name') or "—"  # Display dash if no parent

            # Print the formatted row with color
            row = (
                f"{color}{name:<{widths['name']}} "
                f"{cost_str:<{widths['cost']}} "
                f"{sub['display_currency']:<{widths['currency']}} "
                f"{sub['billing_cycle']:<{widths['cycle']}} "
                f"{sub['start_date']:<{widths['start_date']}} "
                f"{sub['renewal_date']:<{widths['renewal_date']}} "
                f"{trial_end:<{widths['trial_end']}} "
                f"{self.COLORS['PARENT'] if parent != '—' else ''}{parent:<{widths['parent']}}{self.COLORS['RESET'] if parent != '—' else ''} "
                f"{payment:<{widths['payment']}} "
                f"{days_str:<{widths['days']}} "
                f"{self.COLORS['NOTES']}{notes}{self.COLORS['RESET']}"
            )
            print(row)

    def _display_summary(self, subscriptions, status='all', target_currency=None):
        """
        Display summary information about subscriptions.

        Args:
            subscriptions (list): List of enhanced subscription dictionaries
            status (str): Current status filter
            target_currency (str, optional): Currency to display totals in
        """
        # Count subscriptions
        total_count = len(subscriptions)

        # Count parent and child subscriptions
        parent_count = sum(1 for sub in subscriptions if sub['parent_subscription_id'] is None)
        child_count = sum(1 for sub in subscriptions if sub['parent_subscription_id'] is not None)

        # Calculate total monthly and yearly costs
        if target_currency:
            # When a target currency is specified, use the converted costs
            monthly_totals = {target_currency: 0}
            yearly_totals = {target_currency: 0}

            for sub in subscriptions:
                cost = sub["converted_cost"]  # Already converted

                if sub["billing_cycle"] == "monthly":
                    monthly_totals[target_currency] += cost
                    yearly_totals[target_currency] += cost * 12
                elif sub["billing_cycle"] == "yearly":
                    monthly_totals[target_currency] += cost / 12
                    yearly_totals[target_currency] += cost
        else:
            # Original behavior: group by original currency
            monthly_totals = {}
            yearly_totals = {}

            for sub in subscriptions:
                cost = sub["original_cost"]
                currency = sub["original_currency"]

                # Initialize totals for this currency if not exist
                if currency not in monthly_totals:
                    monthly_totals[currency] = 0
                    yearly_totals[currency] = 0

                if sub["billing_cycle"] == "monthly":
                    monthly_totals[currency] += cost
                    yearly_totals[currency] += cost * 12
                elif sub["billing_cycle"] == "yearly":
                    monthly_totals[currency] += cost / 12
                    yearly_totals[currency] += cost

        # Count status breakdown
        overdue_count = sum(1 for sub in subscriptions if sub["days_until_renewal"] < 0)
        due_soon_count = sum(1 for sub in subscriptions if 0 <= sub["days_until_renewal"] <= self.DUE_SOON_THRESHOLD)
        trial_count = sum(1 for sub in subscriptions if sub["is_in_trial"])

        # Count subscriptions with notes
        with_notes_count = sum(1 for sub in subscriptions if sub["notes"])

        # Print summary
        status_desc = {
            'all': 'All subscriptions',
            'upcoming': 'Upcoming renewals',
            'overdue': 'Overdue subscriptions',
            'trial': 'Trial subscriptions'
        }

        print(f"\n{self.COLORS['HEADER']}SUMMARY: {status_desc.get(status, 'Subscriptions')}{self.COLORS['RESET']}")
        print(f"Total subscriptions: {total_count}")
        print(f"{self.COLORS['PARENT']}Parent subscriptions: {parent_count}{self.COLORS['RESET']}")
        print(f"{self.COLORS['PARENT']}Child subscriptions: {child_count}{self.COLORS['RESET']}")

        # Show status breakdown only if showing all subscriptions
        if status == 'all':
            print(f"{self.COLORS['OVERDUE']}Overdue: {overdue_count}{self.COLORS['RESET']}")
            print(
                f"{self.COLORS['DUE_SOON']}Due within {self.DUE_SOON_THRESHOLD} days: {due_soon_count}{self.COLORS['RESET']}")
            print(f"{self.COLORS['TRIAL']}In trial period: {trial_count}{self.COLORS['RESET']}")

        # Show count of subscriptions with notes
        print(f"{self.COLORS['NOTES']}With notes: {with_notes_count}{self.COLORS['RESET']}")

        # Show cost totals
        # If a target currency is used, indicate that values are converted
        conversion_note = " (converted)" if target_currency else ""

        print(f"\nMonthly costs{conversion_note}:")
        for currency, total in monthly_totals.items():
            print(f"  {currency}: {total:.2f}")

        print(f"\nYearly costs{conversion_note}:")
        for currency, total in yearly_totals.items():
            print(f"  {currency}: {total:.2f}")

        # Show upcoming trials ending if there are any
        upcoming_trial_ends = [
            (sub["name"], sub["trial_end_date"], sub["days_until_trial_end"])
            for sub in subscriptions
            if sub["trial_end_date"] and -7 <= sub["days_until_trial_end"] <= 30
        ]

        if upcoming_trial_ends and (status == 'all' or status == 'trial'):
            print(f"\n{self.COLORS['TRIAL']}Trial end dates (next 30 days):{self.COLORS['RESET']}")
            for name, date, days in sorted(upcoming_trial_ends, key=lambda x: x[2]):
                if days < 0:
                    print(f"  {self.COLORS['TRIAL']}{name}: {date} (ended {abs(days)} days ago){self.COLORS['RESET']}")
                elif days == 0:
                    print(f"  {self.COLORS['TRIAL']}{name}: {date} (ends today){self.COLORS['RESET']}")
                else:
                    print(f"  {self.COLORS['TRIAL']}{name}: {date} (ends in {days} days){self.COLORS['RESET']}")

        # Show most imminent renewals if there are any
        upcoming_renewals = [
            (sub["name"], sub["renewal_date"], sub["days_until_renewal"], sub["is_in_trial"])
            for sub in subscriptions
            if -30 <= sub["days_until_renewal"] <= 30  # Show renewals within +/- 30 days
        ]

        if upcoming_renewals:
            print("\nRecent & upcoming renewals (±30 days):")
            for name, date, days, is_trial in sorted(upcoming_renewals, key=lambda x: x[2]):
                color = self.COLORS['TRIAL'] if is_trial else (
                    self.COLORS['OVERDUE'] if days < 0 else
                    self.COLORS['DUE_SOON'] if days <= self.DUE_SOON_THRESHOLD else
                    self.COLORS['NORMAL']
                )

                if days < 0:
                    print(f"  {color}{name}: {date} ({days} days ago - OVERDUE){self.COLORS['RESET']}")
                elif days == 0:
                    print(f"  {color}{name}: {date} (today){self.COLORS['RESET']}")
                else:
                    print(f"  {color}{name}: {date} (in {days} days){self.COLORS['RESET']}")