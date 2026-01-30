# SPDX-License-Identifier: LGPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Shared list manipulation utilities

Provides common helpers for list operations to avoid duplication across modules.
"""
from __future__ import annotations

from typing import List, TypeVar, Hashable


T = TypeVar('T', bound=Hashable)


def dedup_preserve_order(items: List[T]) -> List[T]:
    """Remove duplicates from a list while preserving order.

    Args:
        items: List of hashable items (may contain duplicates)

    Returns:
        New list with duplicates removed, first occurrence preserved

    Note:
        Time complexity: O(n)
        Space complexity: O(n)
        Only works with hashable types (str, int, tuple, etc.)

    Example:
        >>> dedup_preserve_order(['a', 'b', 'a', 'c', 'b'])
        ['a', 'b', 'c']
        >>> dedup_preserve_order([1, 2, 3, 2, 1])
        [1, 2, 3]
        >>> dedup_preserve_order([])
        []
    """
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def dedup_preserve_order_str(items: List[str]) -> List[str]:
    """Remove duplicates from a string list while preserving order.

    Args:
        items: List of strings (may contain duplicates)

    Returns:
        New list with duplicates removed, first occurrence preserved

    Note:
        Specialized version of dedup_preserve_order for strings.
        Slightly faster due to type specialization.

    Example:
        >>> dedup_preserve_order_str(['foo', 'bar', 'foo', 'baz'])
        ['foo', 'bar', 'baz']
    """
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


__all__ = [
    "dedup_preserve_order",
    "dedup_preserve_order_str",
]
