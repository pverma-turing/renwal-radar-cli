"""
Command base class for RenewalRadar subscription manager.
Defines the interface that all commands should implement.
"""

import argparse
from abc import ABC, abstractmethod


class Command(ABC):
    """
    Abstract base class for all CLI commands.
    All command implementations should inherit from this class.
    """

    def __init__(self):
        """Initialize the command."""
        pass

    @classmethod
    @property
    @abstractmethod
    def name(cls):
        """
        The name of the command used in CLI.
        This should be overridden in each command class.

        Returns:
            str: The command name
        """
        pass

    @classmethod
    @property
    @abstractmethod
    def description(cls):
        """
        A short description of what the command does.
        This should be overridden in each command class.

        Returns:
            str: Command description
        """
        pass

    @classmethod
    @abstractmethod
    def register_arguments(cls, parser):
        """
        Register command-specific arguments.
        This should be overridden in each command class.

        Args:
            parser (argparse.ArgumentParser): The argument parser to add arguments to
        """
        pass

    @abstractmethod
    def execute(self, args):
        """
        Execute the command with the provided arguments.
        This should be overridden in each command class.

        Args:
            args (argparse.Namespace): Parsed command-line arguments

        Returns:
            int: Exit code (0 for success, non-zero for errors)
        """
        pass

    def setup_parser(self, subparsers):
        """
        Set up the command's argument parser.

        Args:
            subparsers: Subparsers object from the main parser

        Returns:
            argparse.ArgumentParser: The command's parser
        """
        parser = subparsers.add_parser(
            self.name,
            description=self.description,
            help=self.description
        )

        # Let the command subclass register its specific arguments
        self.register_arguments(parser)

        return parser