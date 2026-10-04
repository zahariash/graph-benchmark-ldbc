"""Shared helpers for the per-engine correctness tests (`<engine>/correctness_query.py`)."""

from collections import Counter
from collections.abc import Callable

import pytest

from correctness.checks import CHECKS, Check
from correctness.oracle import Data, Rows

_data = Data()


def expected(check: Check, oracle: Callable[[Data], Rows] | None = None) -> Rows:
    return (oracle or check.expected)(_data)


def assert_rows(got: Rows, want: Rows, ordered: bool) -> None:
    if ordered:
        assert got == want
        return
    missing = list((Counter(want) - Counter(got)).elements())
    extra = list((Counter(got) - Counter(want)).elements())
    assert not missing and not extra, (
        f"expected {len(want)} rows, got {len(got)}; "
        f"missing {len(missing)} e.g. {missing[:3]}; extra {len(extra)} e.g. {extra[:3]}"
    )


def check_params(known_failures: dict[str, tuple[str, type[Exception]]]):
    """One pytest param per check; a known failure must keep failing with the given exception."""
    unknown = set(known_failures) - {check.name for check in CHECKS}
    assert not unknown, f"unknown checks in KNOWN_FAILURES: {sorted(unknown)}"
    params = []
    for check in CHECKS:
        marks = []
        if check.name in known_failures:
            reason, raises = known_failures[check.name]
            marks.append(pytest.mark.xfail(strict=True, reason=reason, raises=raises))
        params.append(pytest.param(check, id=check.name, marks=marks))
    return params
