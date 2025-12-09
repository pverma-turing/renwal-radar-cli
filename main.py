# run.py
#!/usr/bin/env python3
"""
Runner script for WordWise.
"""

from renewalradar.cli import main
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
if __name__ == "__main__":
    main()