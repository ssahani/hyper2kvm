# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
# hyper2kvm/azure/exceptions.py

from __future__ import annotations


class AzureError(Exception):
    """Base exception for Azure operations."""
    pass


class AzureCLIError(AzureError):
    """Azure CLI command failed."""
    pass


class AzureAuthError(AzureError):
    """Azure authentication error."""
    pass


class AzureDownloadError(AzureError):
    """Azure download operation failed."""
    pass
