#!/usr/bin/env python3
"""
Webhook Server for MigrationJob admission control.

Runs an HTTPS server that handles validation and mutation webhooks.
"""

import sys
import logging
import json
from flask import Flask, request, jsonify

from hyper2kvm.operator.webhook import (
    handle_validation_webhook,
    handle_mutation_webhook
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route('/validate', methods=['POST'])
def validate():
    """
    Validation webhook endpoint.

    Receives AdmissionReview requests and validates MigrationJob specs.
    """
    try:
        admission_review = request.get_json()
        logger.debug(f"Received validation request: {json.dumps(admission_review, indent=2)}")

        response = handle_validation_webhook(admission_review)

        logger.debug(f"Sending validation response: {json.dumps(response, indent=2)}")
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error handling validation webhook: {e}", exc_info=True)
        # Return error response
        return jsonify({
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "uid": request.get_json().get('request', {}).get('uid', 'unknown'),
                "allowed": False,
                "status": {
                    "message": f"Internal webhook error: {str(e)}"
                }
            }
        }), 200


@app.route('/mutate', methods=['POST'])
def mutate():
    """
    Mutation webhook endpoint.

    Receives AdmissionReview requests and applies defaults to MigrationJob specs.
    """
    try:
        admission_review = request.get_json()
        logger.debug(f"Received mutation request: {json.dumps(admission_review, indent=2)}")

        response = handle_mutation_webhook(admission_review)

        logger.debug(f"Sending mutation response: {json.dumps(response, indent=2)}")
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error handling mutation webhook: {e}", exc_info=True)
        # Return error response (allow without mutations)
        return jsonify({
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "uid": request.get_json().get('request', {}).get('uid', 'unknown'),
                "allowed": True,
                "status": {
                    "message": f"Mutation skipped due to error: {str(e)}"
                }
            }
        }), 200


def main():
    """Run webhook server."""
    import argparse

    parser = argparse.ArgumentParser(description='MigrationJob Admission Webhook Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8443, help='Port to bind to')
    parser.add_argument('--cert', default='/certs/tls.crt', help='TLS certificate file')
    parser.add_argument('--key', default='/certs/tls.key', help='TLS key file')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        app.logger.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Starting webhook server on {args.host}:{args.port}")
    logger.info(f"TLS cert: {args.cert}")
    logger.info(f"TLS key: {args.key}")

    # Run with TLS
    try:
        app.run(
            host=args.host,
            port=args.port,
            ssl_context=(args.cert, args.key),
            debug=args.debug
        )
    except FileNotFoundError as e:
        logger.error(f"TLS certificate not found: {e}")
        logger.error("Generate certificates using: scripts/generate-webhook-certs.sh")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start webhook server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
