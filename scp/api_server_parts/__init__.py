"""api_server parts — extracted from api_server.py (Task 19-A).

The package composition boundary wraps the historical /ask implementation
with the GPT-5.6 Sol V104/V105 multimodal port while leaving the large
extracted implementation byte-identical to main.
"""
from __future__ import annotations

import types

from scp.api_server_parts import _ask_impl as _base_ask_impl
from scp.api_server_parts.multimodal_adapter import build_multimodal_ask_wrapper

_wrapper_module = types.SimpleNamespace(
    _ask_impl=build_multimodal_ask_wrapper(_base_ask_impl._ask_impl)
)
_ask_impl = _wrapper_module
