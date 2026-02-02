# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/__main__.py
from __future__ import annotations

import sys

from .cli.argument_parser import parse_args_with_config
from .core.exceptions import Fatal
from .orchestrator.orchestrator import Orchestrator


def main() -> None:
    """
    Main entry point for hyper2kvm CLI.

    Parses command-line arguments, configures logging, and orchestrates the
    VM migration workflow. Supports both traditional workflow and manifest-driven
    batch migrations.

    Exit codes:
        0: Success
        1: General failure
        2+: Specific error codes from Fatal exceptions

    Raises:
        Fatal: For critical errors that should terminate execution

    Examples:
        $ h2kvmctl --config migration.yaml
        $ h2kvmctl --manifest batch-migration.json
    """
    try:
        args, _conf, logger = parse_args_with_config()

        # Check for manifest-driven workflow
        if hasattr(args, 'manifest') and args.manifest:
            # Use manifest-driven pipeline
            from .manifest.orchestrator import ManifestOrchestrator
            try:
                orchestrator = ManifestOrchestrator(args.manifest, logger)
                orchestrator.run()
                rc = 0
            except Fatal as e:
                logger.error(str(e))
                rc = e.code
            except Exception as e:
                logger.error(f"Manifest pipeline failed: {e}")
                rc = 1
        else:
            # Use traditional workflow
            try:
                Orchestrator(logger, args).run()
                rc = 0
            except Fatal as e:
                logger.error(str(e))
                rc = e.code
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                rc = 1

        sys.exit(int(rc))

    except Fatal as e:
        # Fatal exception during config loading or other early init
        # Already logged by the code that raised it, just exit cleanly
        sys.exit(e.code)


if __name__ == "__main__":
    main()
