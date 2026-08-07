"""Single source of truth for the default model configuration.

Both the repositories layer and the insight stores import these constants so
the provider/model never drift between fingerprinting, persistence defaults,
AI analysis and the agent adapters. ``AI_PROVIDER`` / ``AI_MODEL`` environment
variables still override at runtime via ``load_ai_config``.

URL contract (two distinct concepts, never conflated):

- ``DEFAULT_DEEPSEEK_API_BASE`` -> LangChain ``ChatDeepSeek(base_url=...)``.
  LangChain appends the operation path itself, so this must be the API base
  (``https://api.deepseek.com/v1``), NOT a full ``/chat/completions`` URL.
- ``DEFAULT_DEEPSEEK_CHAT_URL`` -> raw ``requests.post(...)`` calls in the
  Direct path, which need the full chat-completions endpoint.
"""

from __future__ import annotations

DEFAULT_AI_PROVIDER = "deepseek"
DEFAULT_AI_MODEL = "deepseek-v4-flash"

DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEFAULT_DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
