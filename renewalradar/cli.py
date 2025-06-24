"""
Main CLI entry point for RenewalRadar subscription manager.
"""

import argparse
import sys
import os
from . import __version__
from renewalradar.config import COMMANDS


def get_all_commands():
    """
    Get all registered commands.

    Returns:
        dict: Dictionary mapping command names to command classes
    """
    return COMMANDS.copy()


def setup_parsers(subparsers):
    """
    Set up command parsers for all registered commands.

    Args:
        subparsers: Subparsers object from the main parser
    """
    for command_name, command_class in get_all_commands().items():
        command = command_class()
        command.setup_parser(subparsers)

def main():
    # Check for version flag at the beginning
    if len(sys.argv) > 1 and sys.argv[1] == '--version':
        print(f"RenewalRadar CLI v{__version__}")
        return 0

    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RenewalRadar - A subscription manager CLI",
        epilog="Use 'renewalradar <command> --help' for more information about a command."
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f"RenewalRadar CLI v{__version__}"
    )

    # Initialize subparsers for commands
    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        help="Command to run"
    )

    # Set up parsers for all registered commands
    setup_parsers(subparsers)

    # Parse arguments
    args = parser.parse_args()

    # If no command is specified, show help
    if args.command is None:
        parser.print_help()
        return 0

    # Get the command class
    command_class = COMMANDS.get(args.command)
    if command_class is None:
        print(f"Error: Unknown command '{args.command}'")
        return 1

    # Create and execute the command
    command = command_class()
    return command.execute(args)


if __name__ == "__main__":
    sys.exit(main())