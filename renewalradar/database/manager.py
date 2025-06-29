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

    def get_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Enable row access by column name
        return self.conn

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

        # conn.close()
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

    def get_tag_usage(self, filters=None):
        """Get usage counts for all tags in the database.

        Args:
            filters (dict, optional): Filters to apply before counting

        Returns:
            dict: Dictionary mapping tag names to their usage count
        """
        # First get all subscriptions that match our filters
        subscriptions = self.get_filtered_subscriptions(filters)

        # Count tag usage
        tag_counts = {}
        for sub in subscriptions:
            for tag in sub.tags:
                if tag in tag_counts:
                    tag_counts[tag] += 1
                else:
                    tag_counts[tag] = 1

        return tag_counts

    def get_payment_method_usage(self, filters=None):
        """Get usage counts for all payment methods in the database.

        Args:
            filters (dict, optional): Filters to apply before counting

        Returns:
            dict: Dictionary mapping payment method names to their usage count
        """
        # First get all subscriptions that match our filters
        subscriptions = self.get_filtered_subscriptions(filters)

        # Count payment method usage
        payment_counts = {}
        for sub in subscriptions:
            method = sub.payment_method
            if method:  # Skip None/empty payment methods
                if method in payment_counts:
                    payment_counts[method] += 1
                else:
                    payment_counts[method] = 1

        return payment_counts

    def set_budget(self, year, month, currency, amount):
        """Set a budget for a specific month, year, and currency."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Validate amount (must be positive)
            if amount <= 0:
                raise ValueError("Budget amount must be positive")

            # Check if budget already exists
            cursor.execute(
                "SELECT id FROM budgets WHERE year = ? AND month = ? AND currency = ?",
                (year, month, currency)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing budget
                cursor.execute(
                    """UPDATE budgets 
                       SET amount = ?, updated_at = CURRENT_TIMESTAMP 
                       WHERE year = ? AND month = ? AND currency = ?""",
                    (amount, year, month, currency)
                )
                return False  # Not a new budget
            else:
                # Insert new budget
                cursor.execute(
                    """INSERT INTO budgets (year, month, currency, amount)
                       VALUES (?, ?, ?, ?)""",
                    (year, month, currency, amount)
                )
                return True  # New budget

    def get_budgets(self, year=None, month=None, currency=None):
        """Get all budgets, optionally filtered by year, month, or currency."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT year, month, currency, amount FROM budgets"
            params = []
            conditions = []

            if year is not None:
                conditions.append("year = ?")
                params.append(year)

            if month is not None:
                conditions.append("month = ?")
                params.append(month)

            if currency is not None:
                conditions.append("currency = ?")
                params.append(currency)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY year DESC, month DESC, currency ASC"

            cursor.execute(query, params)
            return cursor.fetchall()

    def get_subscription_costs_by_budget_period(self, year, month, currency=None, tag=None, payment_method=None):
        """
        Get total subscription costs for a specific budget period.

        Calculates the sum of subscription costs that are active in the given month/year,
        excluding cancelled subscriptions and considering renewal/start dates.

        Args:
            year: Year for the budget period
            month: Month for the budget period (1-12)
            currency: Currency code to filter by (or None for all currencies)
            tag: Filter by subscription tag
            payment_method: Filter by payment method
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create date range for the given month
            import calendar
            import datetime

            # Get the first and last day of the month
            first_day = datetime.date(year, month, 1)
            last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

            # Format dates for SQLite (YYYY-MM-DD)
            first_day_str = first_day.strftime('%Y-%m-%d')
            last_day_str = last_day.strftime('%Y-%m-%d')

            # Build the query to find active subscriptions in the month
            query = """
                       SELECT 
                           s.currency, s.cost, s.name
                       FROM 
                           subscriptions s
                       WHERE 
                           s.currency = IFNULL(?, s.currency)
                           AND (s.status IS NULL OR s.status != 'cancelled')
                           AND (
                               /* Case 1: Subscription starts before or during this month */
                               (s.start_date IS NULL OR s.start_date <= ?)
                               AND
                               /* Case 2: Either has no renewal date, or renews after or during this month */
                               (
                                   s.renewal_date IS NULL 
                                   OR 
                                   (
                                       /* Subscription that renews during this month is active */
                                       (s.renewal_date >= ? AND s.renewal_date <= ?)
                                       OR
                                       /* Subscription that renewed before this month but has next renewal after month */
                                       (
                                           s.start_date <= ? 
                                           AND 
                                           (
                                               /* Handle different billing cycles to calculate next renewal */
                                               (s.billing_cycle = 'monthly' AND DATE(s.renewal_date, '+1 month') >= ?)
                                               OR (s.billing_cycle = 'quarterly' AND DATE(s.renewal_date, '+3 month') >= ?)
                                               OR (s.billing_cycle = 'annually' AND DATE(s.renewal_date, '+12 month') >= ?)
                                               OR (s.billing_cycle = 'semi-annually' AND DATE(s.renewal_date, '+6 month') >= ?)
                                               OR (s.billing_cycle IS NULL)
                                           )
                                       )
                                   )
                               )
                           )
                       """

            # Add tag filter if provided
            if tag is not None:
                query += " AND s.tags LIKE ? "

            # Add payment method filter if provided
            if payment_method is not None:
                query += " AND s.payment_method = ? "

            # Build the parameters list
            params = [
                currency,
                last_day_str,  # For start_date check
                first_day_str, last_day_str,  # For renewal during month
                last_day_str,  # For start before month end
                first_day_str,  # Monthly
                first_day_str,  # Quarterly
                first_day_str,  # Annually
                first_day_str  # Semi-annually
            ]

            # Add tag parameter if provided
            if tag is not None:
                params.append(f"%{tag}%")  # Using LIKE for partial tag matching

            # Add payment method parameter if provided
            if payment_method is not None:
                params.append(payment_method)


            cursor.execute(query, tuple(params))
            subscriptions = cursor.fetchall()

            # Calculate monthly costs per currency
            costs_by_currency = {}
            counts_by_currency = {}

            # Debug information
            subscription_details = {}

            for sub in subscriptions:
                # Parse all the fields we're returning
                sub_currency = sub[0]
                cost = sub[1]
                name = sub[2] if len(sub) > 2 else "Unknown"

                # For now, we assume monthly billing as requested
                # No prorating based on billing cycle yet
                monthly_cost = cost

                # Add to the total for this currency
                if sub_currency not in costs_by_currency:
                    costs_by_currency[sub_currency] = 0
                    counts_by_currency[sub_currency] = 0
                    subscription_details[sub_currency] = []

                costs_by_currency[sub_currency] += monthly_cost
                counts_by_currency[sub_currency] += 1

                # Keep track of which subscriptions are included for debugging
                if len(sub) > 2:  # If we have the name
                    subscription_details[sub_currency].append(name)

            # Add the counts and details to the result dictionary
            for currency, count in counts_by_currency.items():
                costs_by_currency[f"{currency}_count"] = count
                costs_by_currency[f"{currency}_details"] = subscription_details.get(currency, [])

            return costs_by_currency
