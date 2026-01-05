# SPDX-License-Identifier: GPL-2.0-or-later
class FakeLogger:
    def __init__(self):
        self.records = []

    def _log(self, level, msg):
        self.records.append((level, str(msg)))

    def info(self, msg, *a, **k): self._log("info", msg)
    def warning(self, msg, *a, **k): self._log("warning", msg)
    def error(self, msg, *a, **k): self._log("error", msg)
    def debug(self, msg, *a, **k): self._log("debug", msg)

    def isEnabledFor(self, _lvl):
        return False
