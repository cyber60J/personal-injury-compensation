#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容旧导入；唯一裁判提示实现位于 ``personal_injury.domain.guidance``。"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_layout() -> None:
    src_dir = Path(__file__).resolve().parent / "src"
    if src_dir.is_dir() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_ensure_src_layout()

from personal_injury.domain.guidance import (  # noqa: E402
    CLAIM_RULES,
    EVIDENCE_ALIASES,
    SOURCE_REFERENCES,
    ClaimReview,
    ClaimRule,
    apply_liability_ratio,
    normalize_evidence,
    review_compensation_claims,
)

__all__ = [
    "CLAIM_RULES",
    "EVIDENCE_ALIASES",
    "SOURCE_REFERENCES",
    "ClaimReview",
    "ClaimRule",
    "apply_liability_ratio",
    "normalize_evidence",
    "review_compensation_claims",
]
