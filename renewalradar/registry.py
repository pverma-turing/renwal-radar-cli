# Registry of available commands


COMMANDS = {}

def register_command(command_class):
    """
    Register a command class in the global registry.

    Args:
        command_class: A subclass of Command to register

    Returns:
        The command class (to allow use as a decorator)
    """
    command_instance = command_class()
    COMMANDS[command_instance.name] = command_class
    return command_class
