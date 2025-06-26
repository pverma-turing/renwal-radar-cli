"""
Database manager for RenewalRadar subscription manager.
Provides connection management and database operations.
"""

import sqlite3
import datetime
from pathlib import Path
from .schema import get_db_path, initialize_db
from ..models.subscription import Subscription


class DatabaseManager:
    """
    Manager class for database operations.
    Handles connection, transactions, and CRUD operations.
    """

    def __init__(self):
        """Initialize the database manager."""
        self.db_path = initialize_db()
        self.conn = None
        self.cursor = None

    def connect(self):
        """Connect to the SQLite database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Enable row access by column name
            self.cursor = self.conn.cursor()

            # Enable foreign key constraints
            self.cursor.execute("PRAGMA foreign_keys = ON")

        return self.conn, self.cursor

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None

    def add_subscription(self, subscription_data):
        """
        Add a new subscription to the database.

        Args:
            subscription_data (dict): Dictionary containing subscription details

        Returns:
            int: The ID of the newly created subscription
        """
        conn, cursor = self.connect()

        try:
            # Set created_at and updated_at timestamps
            now = datetime.datetime.now().isoformat()
            subscription_data['created_at'] = now
            subscription_data['updated_at'] = now

            # Prepare column names and placeholders for SQL query
            columns = ', '.join(subscription_data.keys())
            placeholders = ', '.join(['?'] * len(subscription_data))

            # Prepare values in the same order as columns
            values = list(subscription_data.values())

            # Insert the new subscription
            cursor.execute(
                f"INSERT INTO subscriptions ({columns}) VALUES ({placeholders})",
                values
            )
            conn.commit()

            # Return the ID of the new subscription
            return cursor.lastrowid

        except Exception as e:
            conn.rollback()
            raise e

    def get_all_subscriptions(self, sort_by=None):
        """
        Retrieve all subscriptions from the database.

        Args:
            sort_by (str, optional): The field to sort by

        Returns:
            list: List of subscription dictionaries
        """
        conn, cursor = self.connect()

        # Determine the ORDER BY clause based on sort_by parameter
        order_by = ""
        if sort_by:
            valid_fields = [
                'name', 'cost', 'billing_cycle', 'currency',
                'start_date', 'renewal_date', 'payment_method',
                'created_at', 'updated_at', 'status'
            ]

            if sort_by in valid_fields:
                order_by = f" ORDER BY {sort_by}"

        # Query the database
        cursor.execute(f"SELECT * FROM subscriptions{order_by}")
        rows = cursor.fetchall()

        # Convert to list of dictionaries
        subscriptions = []
        for row in rows:
            subscription = {key: row[key] for key in row.keys()}
            subscriptions.append(subscription)

        return subscriptions

    def get_subscription_by_id(self, subscription_id):
        """
        Retrieve a specific subscription by ID.

        Args:
            subscription_id (int): The ID of the subscription to retrieve

        Returns:
            dict or None: The subscription data or None if not found
        """
        conn, cursor = self.connect()

        cursor.execute(
            "SELECT * FROM subscriptions WHERE id = ?",
            (subscription_id,)
        )
        row = cursor.fetchone()

        if row:
            return {key: row[key] for key in row.keys()}
        return None

    def update_subscription(self, subscription_id, data):
        """
        Update an existing subscription.

        Args:
            subscription_id (int): The ID of the subscription to update
            data (dict): Updated subscription data

        Returns:
            bool: True if update was successful, False otherwise
        """
        conn, cursor = self.connect()

        try:
            # Set updated_at timestamp
            data['updated_at'] = datetime.datetime.now().isoformat()

            # Prepare SET clause for SQL update
            set_clause = ', '.join([f"{key} = ?" for key in data.keys()])
            values = list(data.values())
            values.append(subscription_id)

            # Execute the update
            cursor.execute(
                f"UPDATE subscriptions SET {set_clause} WHERE id = ?",
                values
            )
            conn.commit()

            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise e

    def get_filtered_subscriptions(self, filters=None, sort_by=None):
        """Get subscriptions with optional filtering and sorting."""
        conn, cursor = self.connect()

        # Start with basic query
        query = "SELECT * FROM subscriptions"
        params = []

        # Build WHERE clause if filters provided
        if filters:
            where_clauses = []

            # Filter by currency
            if "currency" in filters and filters["currency"]:
                where_clauses.append("currency = ?")
                params.append(filters["currency"])

            # Filter by status (can be multiple)
            if "status" in filters and filters["status"]:
                placeholders = ",".join(["?" for _ in filters["status"]])
                where_clauses.append(f"status IN ({placeholders})")
                params.extend(filters["status"])

            # Add any other filters here as needed

            # Combine all where clauses
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
        print
        # Add sorting
        if sort_by:
            query += f" ORDER BY {sort_by}"

        # Execute query
        print(query, params)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert rows to Subscription objects
        subscriptions = []
        for row in rows:
            sub_dict = {key: row[key] for key in row.keys()}
            subscriptions.append(Subscription.from_dict(sub_dict) )

        conn.close()
        return subscriptions

    def delete_subscription(self, subscription_id):
        """
        Delete a subscription from the database.

        Args:
            subscription_id (int): The ID of the subscription to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        conn, cursor = self.connect()

        try:
            cursor.execute(
                "DELETE FROM subscriptions WHERE id = ?",
                (subscription_id,)
            )
            conn.commit()

            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise e

    def get_subscription_by_name(self, name):
        """Get a subscription by name."""
        conn, cursor = self.connect()

        cursor.execute("SELECT * FROM subscriptions WHERE name = ?", (name,))
        row = cursor.fetchone()

        if row:
            sub_dict = {key: row[key] for key in row.keys()}
            subscription = Subscription.from_dict(sub_dict)
        else:
            subscription = None
        return subscription

    def update_subscription_status(self, subscription_id, new_status):
        """Update the status of a subscription."""
        conn, cursor = self.connect()
        cursor.execute(
            "UPDATE subscriptions SET status = ? WHERE id = ?",
            (new_status, int(subscription_id))
        )

        conn.commit()
        conn.close()