"""Smoke test of the package."""

import typeoke_core


def test_package_exposes_version() -> None:
    assert typeoke_core.__version__.count(".") == 2
