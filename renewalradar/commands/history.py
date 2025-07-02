import csv
import json
import sqlite3
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
        parser.add_argument(
            "--name",
            type=str,
            help="Filter history by subscription name (exact match)"
        )
        parser.add_argument(
            "--action",
            type=str,
            choices=["add", "update", "delete"],
            help="Filter history by action type (add, update, or delete)"
        )
        parser.add_argument(
            "--since",
            type=str,
            help="Show only entries on or after this date (YYYY-MM-DD)"
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit the number of results shown"
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["csv"],
            help="Export results in the specified format (currently supported: csv)"
        )

    def execute(self, args):
        """
        Execute the history command with the provided arguments.

        Args:
            args: The parsed command line arguments

        Returns:
            int: 0 on success, non-zero on failure
        """
        # Validate action parameter
        if args.action and args.action not in ["add", "update", "delete"]:
            print(f"Invalid value for --action. Must be one of: add, update, delete")
            return 1

        # Validate limit parameter
        if args.limit is not None:
            if args.limit < 0:
                print(f"Limit must be a positive number")
                return 1
            elif args.limit == 0:
                print("No history records to display (limit set to 0)")
                return 0

        # Validate the since date format if provided
        since_date = None
        if args.since:
            try:
                since_date = datetime.strptime(args.since, '%Y-%m-%d')
                # Convert to ISO format date string (just the date part)
                since_date_str = since_date.strftime('%Y-%m-%d')
            except ValueError:
                print("Invalid date format for --since. Please use YYYY-MM-DD.")
                return 1

        conn = None
        try:
            db_manager = DatabaseManager()
            conn = db_manager.get_connection()

            # Build the query based on provided filters
            query = "SELECT timestamp, action, subscription_name, changed_fields FROM change_log"
            params = []
            conditions = []

            # Apply name filter if provided
            if args.name is not None and args.name.strip():
                conditions.append("subscription_name = ?")
                params.append(args.name.strip())

            # Apply action filter if provided - ensure case insensitive matching
            if args.action is not None:
                conditions.append("LOWER(action) = LOWER(?)")
                params.append(args.action.lower())

            # Apply since date filter if provided and valid
            # FIX: Use a more reliable approach for timestamp comparison in SQLite
            if since_date:
                # SQLite timestamp comparison - this ensures we're comparing the date portion correctly
                conditions.append("strftime('%Y-%m-%d', timestamp) >= ?")
                params.append(since_date_str)

            # Add WHERE clause if we have conditions
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            # Always order by timestamp descending
            query += " ORDER BY timestamp DESC"

            # Apply limit if specified
            if args.limit is not None and args.limit > 0:
                query += " LIMIT ?"
                params.append(args.limit)

            # Debug output to diagnose filter issues - can be removed in production
            # print(f"DEBUG: Executing query: {query}")
            # print(f"DEBUG: Parameters: {params}")

            # Execute the query with parameters
            cursor = conn.execute(query, params)

            # Get all rows first to check if results exist and get accurate count
            all_rows = cursor.fetchall()

            if not all_rows:
                # Determine the filter description for empty results
                filter_parts = []
                if args.name:
                    filter_parts.append(f"subscription '{args.name}'")
                if args.action:
                    filter_parts.append(f"action '{args.action.upper()}'")
                if since_date:
                    filter_parts.append(f"since {args.since}")

                filter_description = ""
                if filter_parts:
                    filter_description = " for " + ", ".join(filter_parts)

                print(f"No change history found{filter_description}.")
                return 0

            # Build filter description for output messages
            filter_parts = []
            if args.name:
                filter_parts.append(f"subscription '{args.name}'")
            if args.action:
                filter_parts.append(f"action '{args.action.upper()}'")
            if since_date:
                filter_parts.append(f"since {args.since}")

            filter_description = ""
            if filter_parts:
                filter_description = " for " + ", ".join(filter_parts)

            # Process output based on format
            if args.format == "csv":
                # CSV export - stream directly to file
                output_file = "history_export.csv"

                try:
                    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                        csv_writer = csv.writer(csvfile)

                        # Write header
                        csv_writer.writerow(["Timestamp", "Action", "Subscription", "Changed Fields"])

                        # Stream rows directly to CSV file
                        for row in all_rows:
                            timestamp_str, action, name, changed_fields_json = row

                            # Format timestamp
                            try:
                                timestamp = datetime.fromisoformat(timestamp_str)
                                formatted_timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                formatted_timestamp = timestamp_str

                            # Format changed fields
                            try:
                                changed_fields_dict = json.loads(changed_fields_json)
                                changed_fields_formatted = "\n".join(
                                    f"{key}: {value}" for key, value in changed_fields_dict.items()
                                )
                            except json.JSONDecodeError:
                                changed_fields_formatted = changed_fields_json

                            # Write the row
                            csv_writer.writerow([
                                formatted_timestamp,
                                action.upper(),
                                name,
                                changed_fields_formatted
                            ])

                    print(f"Successfully exported {len(all_rows)} history records to {output_file}")
                    return 0

                except IOError as e:
                    print(f"Error writing to file {output_file}: {e}")
                    return 1
            else:
                # Table output - process rows directly for tabulate
                formatted_rows = []

                for row in all_rows:
                    timestamp_str, action, name, changed_fields_json = row

                    # Format timestamp
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        formatted_timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        formatted_timestamp = timestamp_str

                    # Format changed fields
                    try:
                        changed_fields_dict = json.loads(changed_fields_json)
                        changed_fields_formatted = "\n".join(
                            f"{key}: {value}" for key, value in changed_fields_dict.items()
                        )
                    except json.JSONDecodeError:
                        changed_fields_formatted = changed_fields_json

                    # Add to formatted rows
                    formatted_rows.append([
                        formatted_timestamp,
                        action.upper(),
                        name,
                        changed_fields_formatted
                    ])

                # Generate and display the table
                table = tabulate(
                    formatted_rows,
                    headers=["Timestamp", "Action", "Subscription", "Changed Fields"],
                    tablefmt="pretty"
                )

                # Show limit message if applicable
                limit_message = ""
                if args.limit is not None and args.limit > 0 and len(all_rows) == args.limit:
                    limit_message = f" (limited to {args.limit})"

                print(f"\nSubscription Change History{filter_description}:\n")
                print(table)

                print(f"\nTotal entries shown: {len(all_rows)}{limit_message}")
                return 0

        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return 1
        except Exception as e:
            print(f"Error retrieving change history: {e}")
            return 1
        finally:
            if conn:
                conn.close()