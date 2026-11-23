"""Bounded runtime preflight statement admission control (propose-only).

Doctrine (leader-study card r1): cap admitted statement counts below the
database operational limit (PgBouncer-style admission control), reject
work BEFORE admission with a receipted reason, enforce per-query
timeouts, and fail closed on overflow instead of queueing unbounded.

Honest limitation, disclosed: a blocking callable cannot be killed in
pure Python, so the timeout is enforced BY INSPECTION - the callable is
allowed to return, and if elapsed time exceeded the limit its result is
discarded and the query fails closed with timed_out=True.

The module never contacts a database: queries run against injected
callables so bounds and timeout contracts are testable without
PostgreSQL. PROPOSAL_ONLY, unsigned; merges are owned by the estate
signature wall. No status claims are made about any other pull request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional


class PreflightError(ValueError):
    """A preflight query or controller bound is malformed."""


@dataclass
class PreflightQuery:
    """A bounded preflight statement, executed via injected callable."""

    name: str
    statement: str               # SQL text or fingerprint; never executed here
    timeout_s: float
    execute: Optional[Callable[[], object]] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise PreflightError("query name must be a non-empty string")
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise PreflightError("statement fingerprint required")
        if not self.timeout_s or self.timeout_s <= 0:
            raise PreflightError("timeout_s must be positive")


@dataclass
class ExecutionRecord:
    query_name: str
    executed: bool
    timed_out: bool
    elapsed_s: float
    result: object = None
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "query_name": self.query_name,
            "executed": self.executed,
            "timed_out": self.timed_out,
            "elapsed_s": self.elapsed_s,
            "result": self.result if isinstance(self.result, (int, float, str, bool, type(None))) else "<opaque>",
            "error": self.error,
        }


class AdmissionController:
    """Bounds admitted preflight statements; rejects before admission."""

    def __init__(self, max_statements: int, clock: Callable[[], float] = time.monotonic):
        if max_statements < 0:
            raise PreflightError("max_statements must be >= 0")
        self.max_statements = max_statements
        self.clock = clock
        self._in_flight: List[str] = []

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)

    def submit(self, query: PreflightQuery):
        """Admission decision; rejection happens BEFORE any execution."""
        if self.in_flight >= self.max_statements:
            return (False, "admission bound exceeded: %d/%d in flight" %
                    (self.in_flight, self.max_statements))
        self._in_flight.append(query.name)
        return (True, "admitted: %d/%d in flight" % (self.in_flight, self.max_statements))

    def release(self, query: PreflightQuery):
        if query.name in self._in_flight:
            self._in_flight.remove(query.name)

    def execute(self, query: PreflightQuery) -> ExecutionRecord:
        admitted, reason = self.submit(query)
        if not admitted:
            return ExecutionRecord(query_name=query.name, executed=False, timed_out=False,
                                   elapsed_s=0.0, error=reason)
        started = self.clock()
        error = None
        result = None
        try:
            if query.execute is not None:
                result = query.execute()
        except Exception as exc:  # a failing preflight query is data, not a crash
            error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            elapsed = self.clock() - started
            self.release(query)
        if elapsed > query.timeout_s:
            return ExecutionRecord(query_name=query.name, executed=True, timed_out=True,
                                   elapsed_s=elapsed, result=None,
                                   error="timeout after %.3fs (limit %.3fs): result discarded" %
                                         (elapsed, query.timeout_s))
        return ExecutionRecord(query_name=query.name, executed=True, timed_out=False,
                               elapsed_s=elapsed, result=result, error=error)
