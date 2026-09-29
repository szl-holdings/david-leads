"""Run both pytest functions and unittest classes; skips cannot pass a required gate."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RequiredResults:
    def __init__(self):
        self.executed = 0
        self.skipped = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.executed += 1
        if report.skipped:
            self.skipped += 1

    def pytest_sessionfinish(self, session, exitstatus):
        if self.executed == 0 or self.skipped:
            session.exitstatus = 1
            reporter = session.config.pluginmanager.get_plugin("terminalreporter")
            if reporter:
                reporter.write_sep("!", f"Required suite held: {self.executed} executed, {self.skipped} skipped")


if __name__ == "__main__":
    sys.exit(pytest.main(["-q", *(sys.argv[1:] or ["tests"])], plugins=[RequiredResults()]))
