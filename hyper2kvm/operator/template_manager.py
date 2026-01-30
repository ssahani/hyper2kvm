"""
Job Template Manager.

Manages job templates, parameter substitution, and template instantiation.
"""

import logging
import re
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from kubernetes import client

logger = logging.getLogger(__name__)


class TemplateManager:
    """
    Manages job templates and instantiation.

    Handles:
    - Template parameter validation
    - Parameter substitution
    - Template instantiation
    - Template usage tracking
    """

    def __init__(self):
        """Initialize template manager."""
        self.custom_api = client.CustomObjectsApi()
        self.template_cache: Dict[str, Dict[str, Any]] = {}

    async def get_template(
        self,
        namespace: str,
        template_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a job template.

        Args:
            namespace: Kubernetes namespace
            template_name: Name of the template

        Returns:
            Template object or None if not found
        """
        # Check cache first
        cache_key = f"{namespace}/{template_name}"
        if cache_key in self.template_cache:
            return self.template_cache[cache_key]

        try:
            template = self.custom_api.get_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="jobtemplates",
                name=template_name
            )

            self.template_cache[cache_key] = template
            return template

        except client.rest.ApiException as e:
            if e.status == 404:
                return None
            raise

    def validate_parameters(
        self,
        template_params: List[Dict[str, Any]],
        provided_params: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate provided parameters against template definition.

        Args:
            template_params: Template parameter definitions
            provided_params: User-provided parameters

        Returns:
            Tuple of (is_valid, error_message)
        """
        for param_def in template_params:
            param_name = param_def['name']
            param_type = param_def['type']
            required = param_def.get('required', True)

            # Check required parameters
            if required and param_name not in provided_params:
                # Check for default value
                if 'default' not in param_def:
                    return False, f"Required parameter '{param_name}' not provided"

            # Validate parameter value if provided
            if param_name in provided_params:
                value = provided_params[param_name]

                # Type validation
                if param_type == 'integer':
                    if not isinstance(value, int):
                        try:
                            value = int(value)
                            provided_params[param_name] = value
                        except ValueError:
                            return False, f"Parameter '{param_name}' must be an integer"

                elif param_type == 'boolean':
                    if not isinstance(value, bool):
                        if isinstance(value, str):
                            value = value.lower() in ('true', '1', 'yes')
                            provided_params[param_name] = value
                        else:
                            return False, f"Parameter '{param_name}' must be a boolean"

                elif param_type == 'path':
                    if not isinstance(value, str) or not value.startswith('/'):
                        return False, f"Parameter '{param_name}' must be an absolute path"

                # Validation rules
                validation = param_def.get('validation', {})

                # Pattern validation
                if 'pattern' in validation:
                    pattern = validation['pattern']
                    if not re.match(pattern, str(value)):
                        return False, (
                            f"Parameter '{param_name}' does not match pattern: {pattern}"
                        )

                # Range validation (for integers)
                if param_type == 'integer':
                    if 'min' in validation and value < validation['min']:
                        return False, (
                            f"Parameter '{param_name}' must be >= {validation['min']}"
                        )
                    if 'max' in validation and value > validation['max']:
                        return False, (
                            f"Parameter '{param_name}' must be <= {validation['max']}"
                        )

        return True, None

    def substitute_parameters(
        self,
        template: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Substitute parameters in template.

        Args:
            template: Job template
            parameters: Parameter values

        Returns:
            Template with substituted values
        """
        import json
        import copy

        # Deep copy to avoid modifying original
        result = copy.deepcopy(template)

        # Convert to JSON string for easy substitution
        template_str = json.dumps(result)

        # Substitute each parameter
        for param_name, param_value in parameters.items():
            placeholder = f"{{{{.{param_name}}}}}"
            template_str = template_str.replace(placeholder, str(param_value))

        # Convert back to dict
        result = json.loads(template_str)

        return result

    async def instantiate_template(
        self,
        namespace: str,
        template_name: str,
        job_name: str,
        parameters: Dict[str, Any]
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Create a MigrationJob from a template.

        Args:
            namespace: Kubernetes namespace
            template_name: Name of the template
            job_name: Name for the new job
            parameters: Parameter values

        Returns:
            Tuple of (job_spec, error_message)
        """
        # Get template
        template = await self.get_template(namespace, template_name)
        if not template:
            return None, f"Template '{template_name}' not found"

        spec = template.get('spec', {})
        template_params = spec.get('parameters', [])

        # Fill in defaults
        for param_def in template_params:
            param_name = param_def['name']
            if param_name not in parameters and 'default' in param_def:
                parameters[param_name] = param_def['default']

        # Validate parameters
        is_valid, error = self.validate_parameters(template_params, parameters)
        if not is_valid:
            return None, error

        # Get job template
        job_template = spec.get('template', {})

        # Substitute parameters
        job_spec = self.substitute_parameters(job_template, parameters)

        # Apply defaults
        defaults = spec.get('defaults', {})
        for key, value in defaults.items():
            if key not in job_spec:
                job_spec[key] = value

        # Create full job object
        job = {
            'apiVersion': 'hyper2kvm.io/v1alpha1',
            'kind': 'MigrationJob',
            'metadata': {
                'name': job_name,
                'namespace': namespace,
                'labels': {
                    'hyper2kvm.io/template': template_name
                },
                'annotations': {
                    'hyper2kvm.io/template-parameters': str(parameters)
                }
            },
            'spec': job_spec
        }

        # Update template usage
        await self._update_template_usage(namespace, template_name)

        return job, None

    async def _update_template_usage(
        self,
        namespace: str,
        template_name: str
    ):
        """
        Update template usage statistics.

        Args:
            namespace: Kubernetes namespace
            template_name: Name of the template
        """
        try:
            template = await self.get_template(namespace, template_name)
            if not template:
                return

            status = template.get('status', {})
            usage_count = status.get('usageCount', 0) + 1

            status['usageCount'] = usage_count
            status['lastUsed'] = datetime.now(timezone.utc).isoformat()

            template['status'] = status

            self.custom_api.patch_namespaced_custom_object_status(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="jobtemplates",
                name=template_name,
                body=template
            )

            # Invalidate cache
            cache_key = f"{namespace}/{template_name}"
            if cache_key in self.template_cache:
                del self.template_cache[cache_key]

        except Exception as e:
            logger.warning(f"Could not update template usage: {e}")

    async def list_templates(
        self,
        namespace: str,
        operation_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List available templates.

        Args:
            namespace: Kubernetes namespace
            operation_filter: Optional operation type filter

        Returns:
            List of template summaries
        """
        try:
            templates = self.custom_api.list_namespaced_custom_object(
                group="hyper2kvm.io",
                version="v1alpha1",
                namespace=namespace,
                plural="jobtemplates"
            )

            result = []
            for template in templates.get('items', []):
                spec = template.get('spec', {})
                operation = spec.get('operation')

                if operation_filter and operation != operation_filter:
                    continue

                result.append({
                    'name': template['metadata']['name'],
                    'operation': operation,
                    'description': spec.get('description', ''),
                    'parameters': len(spec.get('parameters', [])),
                    'usage_count': template.get('status', {}).get('usageCount', 0)
                })

            return result

        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return []

    def validate_template_definition(
        self,
        template_spec: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate a template definition.

        Args:
            template_spec: Template specification

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        if 'operation' not in template_spec:
            return False, "Template must specify operation"

        if 'parameters' not in template_spec:
            return False, "Template must specify parameters"

        if 'template' not in template_spec:
            return False, "Template must specify job template"

        # Validate parameters
        params = template_spec['parameters']
        if not isinstance(params, list):
            return False, "Parameters must be a list"

        param_names = set()
        for param in params:
            if 'name' not in param:
                return False, "Each parameter must have a name"

            name = param['name']
            if name in param_names:
                return False, f"Duplicate parameter name: {name}"

            param_names.add(name)

            if 'type' not in param:
                return False, f"Parameter '{name}' must have a type"

        # Validate template contains all parameter placeholders
        import json
        template_str = json.dumps(template_spec['template'])

        for param in params:
            placeholder = f"{{{{.{param['name']}}}}}"
            if placeholder not in template_str:
                logger.warning(
                    f"Parameter '{param['name']}' not used in template"
                )

        return True, None
