# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/__main__.py
from __future__ import annotations

import sys

from .cli.argument_parser import parse_args_with_config
from .core.exceptions import Fatal
from .orchestrator.orchestrator import Orchestrator


def main() -> None:
    args, _conf, logger = parse_args_with_config()

    # Check for manifest-driven workflow
    if hasattr(args, 'manifest') and args.manifest:
        # Use manifest-driven pipeline
        from .manifest.orchestrator import ManifestOrchestrator
        try:
            orchestrator = ManifestOrchestrator(args.manifest, logger)
            orchestrator.run()
            rc = 0
        except Exception as e:
            logger.error(f"Manifest pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            rc = 1
    else:
        # Use traditional workflow
        try:
            Orchestrator(logger, args).run()
            rc = 0
        except Fatal as e:
            logger.error(str(e))
            rc = e.code

    sys.exit(int(rc))


if __name__ == "__main__":
    main()
