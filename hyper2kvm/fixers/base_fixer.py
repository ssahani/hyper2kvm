# SPDX-License-Identifier: LGPL-3.0-or-later
from __future__ import annotations

class BaseFixer:
    def run(self) -> int:
        raise NotImplementedError
