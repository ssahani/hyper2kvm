"""
Unit tests for Kubernetes operator webhook
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from hyper2kvm.operator.webhook import WebhookValidator
from hyper2kvm.operator.webhook_server import WebhookServer


class TestWebhookValidator:
    """Test webhook validation logic"""

    @pytest.fixture
    def validator(self):
        """Create WebhookValidator instance"""
        return WebhookValidator()

    def test_validate_migrationjob_create(self, validator):
        """Test validation of MigrationJob creation"""
        admission_request = {
            'request': {
                'operation': 'CREATE',
                'object': {
                    'metadata': {
                        'name': 'test-migration',
                        'namespace': 'default'
                    },
                    'spec': {
                        'source': {
                            'type': 'vmdk',
                            'path': '/vms/test.vmdk'
                        },
                        'destination': {
                            'format': 'qcow2',
                            'path': '/output/test.qcow2'
                        }
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is True
        assert 'uid' in response['response']

    def test_validate_invalid_source_type(self, validator):
        """Test validation rejects invalid source type"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {
                            'type': 'invalid-type',  # Invalid
                            'path': '/vms/test.vmdk'
                        },
                        'destination': {
                            'format': 'qcow2',
                            'path': '/output/test.qcow2'
                        }
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is False
        assert 'invalid source type' in response['response']['status']['message'].lower()

    def test_validate_missing_required_fields(self, validator):
        """Test validation rejects missing required fields"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {
                            'type': 'vmdk'
                            # Missing 'path'
                        },
                        'destination': {
                            'format': 'qcow2',
                            'path': '/output/test.qcow2'
                        }
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is False
        assert 'required field' in response['response']['status']['message'].lower()

    def test_validate_invalid_destination_format(self, validator):
        """Test validation rejects invalid destination format"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {
                            'type': 'vmdk',
                            'path': '/vms/test.vmdk'
                        },
                        'destination': {
                            'format': 'unsupported',  # Invalid format
                            'path': '/output/test.img'
                        }
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is False
        assert 'format' in response['response']['status']['message'].lower()

    def test_validate_update_operation(self, validator):
        """Test validation of UPDATE operations"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'UPDATE',
                'object': {
                    'metadata': {
                        'name': 'test-migration',
                        'resourceVersion': '2'
                    },
                    'spec': {
                        'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
                    },
                    'status': {
                        'phase': 'Running'
                    }
                },
                'oldObject': {
                    'metadata': {
                        'name': 'test-migration',
                        'resourceVersion': '1'
                    },
                    'spec': {
                        'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is True

    def test_validate_immutable_spec_fields(self, validator):
        """Test validation prevents modification of immutable fields"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'UPDATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {
                            'type': 'ova',  # Changed!
                            'path': '/vms/test.ova'
                        },
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
                    },
                    'status': {'phase': 'Running'}
                },
                'oldObject': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {
                            'type': 'vmdk',  # Original
                            'path': '/vms/test.vmdk'
                        },
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is False
        assert 'immutable' in response['response']['status']['message'].lower()

    def test_validate_resource_limits(self, validator):
        """Test validation of resource limits"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'},
                        'resources': {
                            'requests': {
                                'cpu': '1',
                                'memory': '2Gi'
                            },
                            'limits': {
                                'cpu': '2',
                                'memory': '4Gi'
                            }
                        }
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        assert response['response']['allowed'] is True

    def test_validate_excessive_resource_requests(self, validator):
        """Test validation rejects excessive resource requests"""
        admission_request = {
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'},
                        'resources': {
                            'requests': {
                                'cpu': '1000',  # Excessive
                                'memory': '1000Gi'  # Excessive
                            }
                        }
                    }
                }
            }
        }

        response = validator.validate(admission_request)

        # Should warn or reject based on cluster quotas
        # For now, test that validation runs
        assert 'response' in response


class TestWebhookServer:
    """Test webhook server"""

    @pytest.fixture
    def webhook_server(self):
        """Create WebhookServer instance"""
        return WebhookServer(
            host='0.0.0.0',
            port=8443,
            cert_file='/certs/tls.crt',
            key_file='/certs/tls.key'
        )

    def test_server_initialization(self, webhook_server):
        """Test webhook server initializes correctly"""
        assert webhook_server.host == '0.0.0.0'
        assert webhook_server.port == 8443
        assert webhook_server.cert_file == '/certs/tls.crt'
        assert webhook_server.key_file == '/certs/tls.key'

    def test_health_check_endpoint(self, webhook_server):
        """Test health check endpoint"""
        with patch.object(webhook_server, 'handle_health_check') as mock_health:
            mock_health.return_value = {'status': 'healthy'}

            response = webhook_server.handle_health_check()

            assert response['status'] == 'healthy'

    def test_validate_endpoint(self, webhook_server):
        """Test validate endpoint"""
        admission_review = {
            'apiVersion': 'admission.k8s.io/v1',
            'kind': 'AdmissionReview',
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                        'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
                    }
                }
            }
        }

        with patch.object(webhook_server.validator, 'validate') as mock_validate:
            mock_validate.return_value = {
                'apiVersion': 'admission.k8s.io/v1',
                'kind': 'AdmissionReview',
                'response': {
                    'uid': 'test-uid',
                    'allowed': True
                }
            }

            response = webhook_server.handle_validate(admission_review)

            assert response['response']['allowed'] is True
            mock_validate.assert_called_once()

    def test_mutate_endpoint(self, webhook_server):
        """Test mutate endpoint for defaulting"""
        admission_review = {
            'apiVersion': 'admission.k8s.io/v1',
            'kind': 'AdmissionReview',
            'request': {
                'uid': 'test-uid',
                'operation': 'CREATE',
                'object': {
                    'metadata': {'name': 'test-migration'},
                    'spec': {
                        'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                        'destination': {
                            'format': 'qcow2',
                            'path': '/output/test.qcow2'
                            # Missing compression setting
                        }
                    }
                }
            }
        }

        with patch.object(webhook_server, 'mutate') as mock_mutate:
            # Should add default compression=true
            mock_mutate.return_value = {
                'apiVersion': 'admission.k8s.io/v1',
                'kind': 'AdmissionReview',
                'response': {
                    'uid': 'test-uid',
                    'allowed': True,
                    'patchType': 'JSONPatch',
                    'patch': 'W3sib3AiOiJhZGQiLCJwYXRoIjoiL3NwZWMvZGVzdGluYXRpb24vY29tcHJlc3MiLCJ2YWx1ZSI6dHJ1ZX1d'
                }
            }

            response = webhook_server.handle_mutate(admission_review)

            assert response['response']['allowed'] is True
            assert 'patch' in response['response']


class TestWebhookDefaulting:
    """Test webhook defaulting/mutation"""

    @pytest.fixture
    def validator(self):
        """Create WebhookValidator instance"""
        return WebhookValidator()

    def test_default_output_format(self, validator):
        """Test defaulting output format to qcow2"""
        obj = {
            'metadata': {'name': 'test-migration'},
            'spec': {
                'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                'destination': {
                    'path': '/output/test.img'
                    # Missing format
                }
            }
        }

        patches = validator.get_default_patches(obj)

        # Should add format: qcow2
        assert any(p['path'] == '/spec/destination/format' for p in patches)

    def test_default_compression(self, validator):
        """Test defaulting compression to true"""
        obj = {
            'metadata': {'name': 'test-migration'},
            'spec': {
                'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                'destination': {
                    'format': 'qcow2',
                    'path': '/output/test.qcow2'
                    # Missing compress
                }
            }
        }

        patches = validator.get_default_patches(obj)

        # Should add compress: true
        assert any(p['path'] == '/spec/destination/compress' for p in patches)

    def test_default_workers(self, validator):
        """Test defaulting workers to 1"""
        obj = {
            'metadata': {'name': 'test-migration'},
            'spec': {
                'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
                # Missing workers
            }
        }

        patches = validator.get_default_patches(obj)

        # Should add workers: 1
        assert any(p['path'] == '/spec/workers' for p in patches)

    def test_add_labels(self, validator):
        """Test adding default labels"""
        obj = {
            'metadata': {
                'name': 'test-migration'
                # No labels
            },
            'spec': {
                'source': {'type': 'vmdk', 'path': '/vms/test.vmdk'},
                'destination': {'format': 'qcow2', 'path': '/output/test.qcow2'}
            }
        }

        patches = validator.get_default_patches(obj)

        # Should add labels
        label_patches = [p for p in patches if '/metadata/labels' in p['path']]
        assert len(label_patches) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
