#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容旧入口；唯一计算实现位于 ``personal_injury.domain.calculator``。"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_layout() -> None:
    """Allow ``python compensation_calculator.py`` before editable installation."""
    src_dir = Path(__file__).resolve().parent / "src"
    if src_dir.is_dir() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_ensure_src_layout()

from personal_injury.domain.calculator import CompensationCalculator, main  # noqa: E402

__all__ = ["CompensationCalculator", "main"]


if __name__ == "__main__":
    main()
