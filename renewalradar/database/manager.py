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

    def add_subscription(self, subscription):
        """Add a new subscription to the database."""
        conn, cursor = self.connect()

        cursor.execute('''
        INSERT INTO subscriptions (name, cost, billing_cycle, currency, start_date, renewal_date, 
                                  payment_method, status, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            subscription.name,
            subscription.cost,
            subscription.billing_cycle,
            subscription.currency,
            subscription.start_date,
            subscription.renewal_date,
            subscription.payment_method,
            subscription.status,
            subscription.tags_string
        ))

        last_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return last_id

    def get_all_subscriptions(self, sort_by=None):
        """Get all subscriptions from the database."""
        return self.get_filtered_subscriptions(filters=None, sort_by=sort_by)

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

            # Filter by tag (partial match in comma-separated list)
            if "tag" in filters and filters["tag"]:
                tag_clauses = []
                for tag in filters["tag"]:
                    tag_clauses.append("tags LIKE ?")
                    params.append(f"%{tag}%")
                if tag_clauses:
                    where_clauses.append(f"({' OR '.join(tag_clauses)})")

            # Filter by payment method (can be multiple)
            if "payment_methods" in filters and filters["payment_methods"]:
                placeholders = ",".join(["?" for _ in filters["payment_methods"]])
                where_clauses.append(f"payment_method IN ({placeholders})")
                params.extend(filters["payment_methods"])
            elif "payment_method" in filters and filters["payment_method"]:
                # For backwards compatibility
                where_clauses.append("payment_method = ?")
                params.append(filters["payment_method"])

            # Combine all where clauses
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

        # Add sorting
        if sort_by:
            query += f" ORDER BY {sort_by}"

        # Execute query
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert rows to Subscription objects
        subscriptions = []
        for row in rows:
            sub_dict = {key: row[key] for key in row.keys()}
            subscriptions.append(Subscription.from_dict(sub_dict))

        conn.close()
        return subscriptions

    def get_distinct_values(self, column):
        """Get a list of distinct values from a specific column."""
        conn, cursor = self.connect()

        query = f"SELECT DISTINCT {column} FROM subscriptions WHERE {column} IS NOT NULL AND {column} != ''"
        cursor.execute(query)

        result = [row[0] for row in cursor.fetchall()]
        conn.close()

        return result

    def get_all_tags(self):
        """Get a list of all unique tags across all subscriptions."""
        conn, cursor = self.connect()

        query = "SELECT tags FROM subscriptions WHERE tags IS NOT NULL AND tags != ''"
        cursor.execute(query)

        all_tag_strings = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Process all tag strings and create a unique set
        unique_tags = set()
        for tag_string in all_tag_strings:
            tags = [tag.strip() for tag in tag_string.split(',')]
            unique_tags.update(tags)

        return sorted(list(unique_tags))

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

    def update_subscription(self, subscription):
        """Update an existing subscription in the database."""
        conn, cursor = self.connect()

        cursor.execute('''
        UPDATE subscriptions
        SET name = ?, cost = ?, billing_cycle = ?, currency = ?, 
            start_date = ?, renewal_date = ?, payment_method = ?, 
            status = ?, tags = ?
        WHERE id = ?
        ''', (
            subscription.name,
            subscription.cost,
            subscription.billing_cycle,
            subscription.currency,
            subscription.start_date,
            subscription.renewal_date,
            subscription.payment_method,
            subscription.status,
            subscription.tags_string,
            subscription.id
        ))

        conn.commit()
        conn.close()

        return cursor.rowcount > 0  # Return True if a row was updated

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