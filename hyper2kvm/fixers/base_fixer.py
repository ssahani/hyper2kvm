# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/fixers/base_fixer.py
from __future__ import annotations


class BaseFixer:
    def run(self) -> int:
        raise NotImplementedError
