# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Adapter registry. Every source the vertical knows about, with its honest state."""
from __future__ import annotations

from .demo import DemoAdapter
from .licensed import (
    CapeAnalyticsAdapter,
    LexisNexisRiskAdapter,
    VeriskAdapter,
    ZestyAIAdapter,
)
from .public import EPAEchoAdapter, SECEdgarAdapter, USAspendingAdapter

ALL_ADAPTERS = [
    DemoAdapter(),
    USAspendingAdapter(),
    SECEdgarAdapter(),
    EPAEchoAdapter(),
    VeriskAdapter(),
    LexisNexisRiskAdapter(),
    ZestyAIAdapter(),
    CapeAnalyticsAdapter(),
]

_BY_NAME = {a.name: a for a in ALL_ADAPTERS}


def get(name: str):
    return _BY_NAME.get(name)
