# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/azure/cleanup.py

from __future__ import annotations


def make_tags(*, enable: bool, run_tag: str, vm_name: str) -> dict[str, str]:
    """
    Create resource tags for Azure resources created during migration.

    Args:
        enable: Whether to create tags
        run_tag: Unique identifier for this migration run
        vm_name: Name of the VM being migrated

    Returns:
        Dictionary of tags to apply to Azure resources
    """
    if not enable:
        return {}

    return {
        "hyper2kvm": "true",
        "hyper2kvm-run": run_tag,
        "hyper2kvm-vm": vm_name,
        "hyper2kvm-managed": "true",
    }
