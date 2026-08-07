"""Single source of truth for the default model configuration.

Both the repositories layer and the insight stores import these constants so
the provider/model never drift between fingerprinting, persistence defaults,
AI analysis and the agent adapters. ``AI_PROVIDER`` / ``AI_MODEL`` environment
variables still override at runtime via ``load_ai_config``.
"""

from __future__ import annotations

DEFAULT_AI_PROVIDER = "deepseek"
DEFAULT_AI_MODEL = "deepseek-v4-flash"
