"""Entry point so the CLI is `python -m oneground.pod <subcommand>`."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
