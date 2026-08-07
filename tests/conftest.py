"""Shared pytest fixtures.

The Windows ``os.environ`` implementation refuses values longer than 32767
characters. WorkBuddy/IDE sessions may inject such oversized variables (for
example ``ACC_PRODUCT_CONFIG_V3``), which makes ``unittest.mock.patch.dict``
crash while restoring ``os.environ``. This autouse fixture temporarily removes
oversized variables for the duration of the test run.
"""

from __future__ import annotations

import os

import pytest

# Windows hard limit for a single environment variable value.
_ENV_VALUE_LIMIT = 32_767


@pytest.fixture(autouse=True)
def _tolerate_oversized_env_vars():
    oversized = [
        key for key, value in os.environ.items() if len(value) > _ENV_VALUE_LIMIT
    ]
    if oversized:
        for key in oversized:
            os.environ.pop(key, None)
    yield
    # Oversized values cannot be restored through os.environ on Windows, and
    # no test depends on them; leave them unset for the rest of the run.
