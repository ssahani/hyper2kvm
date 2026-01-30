"""
Unit tests for operator admission webhook.
"""

import pytest
import json
from hyper2kvm.operator.webhook import (
    MigrationJobValidator,
    MigrationJobMutator,
    handle_validation_webhook,
    handle_mutation_webhook,
    create_admission_review_response
)


class TestMigrationJobValidator:
    """Test MigrationJob validation logic."""

    def setup_method(self):
        """Setup test fixtures."""
        self.validator = MigrationJobValidator()

    def test_valid_spec(self):
        """Test validation of valid spec."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'priority': 50,
            'timeout': '2h'
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is True
        assert len(errors) == 0

    def test_missing_operation(self):
        """Test validation fails when operation is missing."""
        spec = {
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('operation is required' in err for err in errors)

    def test_invalid_operation(self):
        """Test validation fails for invalid operation."""
        spec = {
            'operation': 'invalid_op',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('operation must be one of' in err for err in errors)

    def test_missing_image_path(self):
        """Test validation fails when image path is missing."""
        spec = {
            'operation': 'convert',
            'image': {
                'format': 'vmdk'
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('image.path is required' in err for err in errors)

    def test_invalid_image_format(self):
        """Test validation fails for unsupported image format."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.unknown',
                'format': 'unknown'
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('image.format must be one of' in err for err in errors)

    def test_priority_out_of_range(self):
        """Test validation fails for priority out of range."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'priority': 150
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('priority must be between' in err for err in errors)

    def test_invalid_timeout_format(self):
        """Test validation fails for invalid timeout format."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'timeout': 'invalid'
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('timeout must be in format' in err for err in errors)

    def test_valid_timeout_formats(self):
        """Test validation passes for valid timeout formats."""
        valid_timeouts = ['30s', '30m', '2h', '1h']

        for timeout in valid_timeouts:
            spec = {
                'operation': 'convert',
                'image': {
                    'path': '/data/input/test.vmdk',
                    'format': 'vmdk'
                },
                'timeout': timeout
            }

            is_valid, errors = self.validator.validate(spec)
            assert is_valid is True, f"Timeout {timeout} should be valid"

    def test_timeout_exceeds_max(self):
        """Test validation fails when timeout exceeds maximum."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'timeout': '48h'  # Exceeds 24h max
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('timeout must be in format' in err for err in errors)

    def test_invalid_retry_policy(self):
        """Test validation fails for invalid retry policy."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'retryPolicy': {
                'maxRetries': 10,  # Exceeds max of 5
                'backoff': 'invalid'
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('maxRetries must be between' in err for err in errors)
        assert any('backoff must be one of' in err for err in errors)

    def test_valid_checksum(self):
        """Test validation passes for valid checksum."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk',
                'checksum': 'sha256:abc123def456'
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is True

    def test_invalid_checksum_format(self):
        """Test validation fails for invalid checksum format."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk',
                'checksum': 'md5:abc123'  # Not sha256
            }
        }

        is_valid, errors = self.validator.validate(spec)
        assert is_valid is False
        assert any('checksum must start with' in err for err in errors)


class TestMigrationJobMutator:
    """Test MigrationJob mutation logic."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mutator = MigrationJobMutator()

    def test_add_default_priority(self):
        """Test mutator adds default priority."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            }
        }
        metadata = {'name': 'test-job'}

        mutated = self.mutator.mutate(spec, metadata)

        assert 'priority' in mutated
        assert mutated['priority'] == 50

    def test_preserve_existing_priority(self):
        """Test mutator preserves existing priority."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'priority': 75
        }
        metadata = {'name': 'test-job'}

        mutated = self.mutator.mutate(spec, metadata)

        assert mutated['priority'] == 75

    def test_add_default_timeout(self):
        """Test mutator adds default timeout."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            }
        }
        metadata = {'name': 'test-job'}

        mutated = self.mutator.mutate(spec, metadata)

        assert 'timeout' in mutated
        assert mutated['timeout'] == '2h'

    def test_add_default_retry_policy(self):
        """Test mutator adds default retry policy."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            }
        }
        metadata = {'name': 'test-job'}

        mutated = self.mutator.mutate(spec, metadata)

        assert 'retryPolicy' in mutated
        assert mutated['retryPolicy']['maxRetries'] == 2
        assert mutated['retryPolicy']['backoff'] == 'exponential'

    def test_add_creation_timestamp_annotation(self):
        """Test mutator adds creation timestamp annotation."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            }
        }
        metadata = {'name': 'test-job'}

        self.mutator.mutate(spec, metadata)

        assert 'annotations' in metadata
        assert 'hyper2kvm.io/created-at' in metadata['annotations']
        assert 'hyper2kvm.io/webhook-version' in metadata['annotations']
        assert metadata['annotations']['hyper2kvm.io/webhook-version'] == 'v1.5.0'

    def test_add_default_output_format(self):
        """Test mutator adds default output format."""
        spec = {
            'operation': 'convert',
            'image': {
                'path': '/data/input/test.vmdk',
                'format': 'vmdk'
            },
            'artifacts': {}
        }
        metadata = {'name': 'test-job'}

        mutated = self.mutator.mutate(spec, metadata)

        assert mutated['artifacts']['output_format'] == 'qcow2'


class TestWebhookResponses:
    """Test webhook response generation."""

    def test_create_allowed_response(self):
        """Test creating allowed admission response."""
        response = create_admission_review_response(
            uid='test-uid-123',
            allowed=True
        )

        assert response['apiVersion'] == 'admission.k8s.io/v1'
        assert response['kind'] == 'AdmissionReview'
        assert response['response']['uid'] == 'test-uid-123'
        assert response['response']['allowed'] is True

    def test_create_denied_response(self):
        """Test creating denied admission response."""
        response = create_admission_review_response(
            uid='test-uid-456',
            allowed=False,
            message='Validation failed'
        )

        assert response['response']['allowed'] is False
        assert response['response']['status']['message'] == 'Validation failed'

    def test_create_response_with_patch(self):
        """Test creating response with JSON patch."""
        patch = [
            {
                'op': 'add',
                'path': '/spec/priority',
                'value': 50
            }
        ]

        response = create_admission_review_response(
            uid='test-uid-789',
            allowed=True,
            patch=patch
        )

        assert 'patch' in response['response']
        assert response['response']['patchType'] == 'JSONPatch'

        # Decode and verify patch
        import base64
        decoded_patch = json.loads(base64.b64decode(response['response']['patch']))
        assert decoded_patch == patch


class TestValidationWebhook:
    """Test validation webhook handler."""

    def test_handle_valid_job(self):
        """Test handling valid job creates allowed response."""
        admission_review = {
            'request': {
                'uid': 'test-123',
                'object': {
                    'metadata': {
                        'name': 'test-job',
                        'namespace': 'test'
                    },
                    'spec': {
                        'operation': 'convert',
                        'image': {
                            'path': '/data/input/test.vmdk',
                            'format': 'vmdk'
                        }
                    }
                }
            }
        }

        response = handle_validation_webhook(admission_review)

        assert response['response']['allowed'] is True

    def test_handle_invalid_job(self):
        """Test handling invalid job creates denied response."""
        admission_review = {
            'request': {
                'uid': 'test-456',
                'object': {
                    'metadata': {
                        'name': 'test-job',
                        'namespace': 'test'
                    },
                    'spec': {
                        'operation': 'invalid',
                        'image': {
                            'path': '/data/input/test.vmdk',
                            'format': 'unknown'
                        }
                    }
                }
            }
        }

        response = handle_validation_webhook(admission_review)

        assert response['response']['allowed'] is False
        assert 'Validation failed' in response['response']['status']['message']


class TestMutationWebhook:
    """Test mutation webhook handler."""

    def test_handle_mutation(self):
        """Test handling mutation adds defaults."""
        admission_review = {
            'request': {
                'uid': 'test-789',
                'object': {
                    'metadata': {
                        'name': 'test-job',
                        'namespace': 'test'
                    },
                    'spec': {
                        'operation': 'convert',
                        'image': {
                            'path': '/data/input/test.vmdk',
                            'format': 'vmdk'
                        }
                    }
                }
            }
        }

        response = handle_mutation_webhook(admission_review)

        assert response['response']['allowed'] is True
        assert 'patch' in response['response']

    def test_mutation_preserves_existing_values(self):
        """Test mutation doesn't override existing values."""
        admission_review = {
            'request': {
                'uid': 'test-101',
                'object': {
                    'metadata': {
                        'name': 'test-job',
                        'namespace': 'test'
                    },
                    'spec': {
                        'operation': 'convert',
                        'image': {
                            'path': '/data/input/test.vmdk',
                            'format': 'vmdk'
                        },
                        'priority': 75,
                        'timeout': '4h'
                    }
                }
            }
        }

        response = handle_mutation_webhook(admission_review)

        assert response['response']['allowed'] is True
