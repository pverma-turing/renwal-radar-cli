import json
import datetime


def log_change(action: str, name: str, changed_fields: dict = {}):
    """
    Logs a change to the subscription database for history tracking.

    Args:
        action (str): The type of action performed ('add', 'update', or 'delete')
        name (str): The name of the subscription that was affected
        changed_fields (dict, optional): Dictionary of fields that were changed and their values
                                        For 'add', this would be all fields
                                        For 'update', this would be only the changed fields
                                        For 'delete', this can be empty or contain deleted data
    """
    from ..database.manager import DatabaseManager
    db_manager =  DatabaseManager()
    # Generate current UTC timestamp in ISO format
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Serialize the changed_fields dictionary to a JSON string
    serialized_fields = json.dumps(changed_fields)

    # Insert the record into the change_log table
    conn = db_manager.get_connection()
    try:
        conn.execute(
            "INSERT INTO change_log (timestamp, action, subscription_name, changed_fields) VALUES (?, ?, ?, ?)",
            (timestamp, action, name, serialized_fields)
        )
        conn.commit()
    finally:
        conn.close()