import json
from datetime import datetime
from tabulate import tabulate
from .base import Command
from ..database.manager import DatabaseManager
from ..registry import register_command


@register_command
class HistoryCommand(Command):
    """
    Command that displays the history of changes to subscriptions.
    """
    name = "history"
    description = "Display the history of changes to subscriptions"

    @classmethod
    def register_arguments(self, parser):
        """
        Add history command specific arguments to the parser.

        Args:
            parser: The ArgumentParser object to add arguments to
        """
        pass  # No additional arguments for the basic implementation

    def execute(self, args):
        """
        Execute the history command with the provided arguments.

        Args:
            args: The parsed command line arguments

        Returns:
            int: 0 on success, non-zero on failure
        """
        db_manager = DatabaseManager()
        conn = db_manager.get_connection()
        try:
            # Query the change_log table in descending order of timestamp
            cursor = conn.execute(
                "SELECT timestamp, action, subscription_name, changed_fields FROM change_log ORDER BY timestamp DESC"
            )

            # Fetch all rows
            rows = cursor.fetchall()

            if not rows:
                print("No change history found.")
                return 0

            # Format data for tabulate
            formatted_rows = []
            for row in rows:
                timestamp_str, action, name, changed_fields_json = row

                # Parse the timestamp and format it for better readability
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    formatted_timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # Fallback if timestamp can't be parsed
                    formatted_timestamp = timestamp_str

                # Parse the JSON string to get a dictionary
                try:
                    changed_fields_dict = json.loads(changed_fields_json)
                    # Format the dictionary for display
                    changed_fields_formatted = "\n".join(
                        f"{key}: {value}" for key, value in changed_fields_dict.items()
                    )
                except json.JSONDecodeError:
                    # Fallback if JSON can't be parsed
                    changed_fields_formatted = changed_fields_json

                # Create a formatted row
                formatted_rows.append([
                    formatted_timestamp,
                    action.upper(),
                    name,
                    changed_fields_formatted
                ])

            # Use tabulate to create a nicely formatted table
            table = tabulate(
                formatted_rows,
                headers=["Timestamp", "Action", "Subscription", "Changed Fields"],
                tablefmt="pretty"
            )

            print(f"\nSubscription Change History:\n")
            print(table)

            print(f"\nTotal entries: {len(rows)}")
            return 0

        except Exception as e:
            print(f"Error retrieving change history: {e}")
            return 1
        finally:
            conn.close()