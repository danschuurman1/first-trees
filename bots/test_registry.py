# bots/test_registry.py
from __future__ import annotations
from typing import Dict, Type

# Maps test script display name → Bot subclass (kept separate from BOT_REGISTRY)
TEST_REGISTRY: Dict[str, Type] = {}
