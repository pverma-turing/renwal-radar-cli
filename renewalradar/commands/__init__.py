"""
Command registry for RenewalRadar subscription manager.
Handles command registration and discovery.
"""
from renewalradar.commands.view import ViewCommand
from renewalradar.commands.add import AddCommand
from renewalradar.commands.update_status import UpdateStatusCommand
from renewalradar.commands.summary import SummaryCommand
from renewalradar.commands.list_usage import ListUsageCommand

