#!/usr/bin/env python3
"""
CLI entrypoint for Hyper2KVM Kubernetes Operator.

Usage:
    python -m hyper2kvm.operator.cli
"""

import sys
import logging
import kopf

# Import controllers to register kopf handlers
from hyper2kvm.operator import migrationjob_controller  # noqa: F401
from hyper2kvm.operator import offlinefixjob_controller  # noqa: F401

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main operator entrypoint."""
    logger.info("Starting Hyper2KVM Kubernetes Operator v1.4.0")

    try:
        # Run Kopf operator
        kopf.run(
            standalone=True,
            clusterwide=True,  # Watch all namespaces cluster-wide
            liveness_endpoint='http://0.0.0.0:8080/healthz',
        )
    except KeyboardInterrupt:
        logger.info("Operator stopped by user")
    except Exception as e:
        logger.error(f"Operator error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
