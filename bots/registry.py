# bots/registry.py
from __future__ import annotations
from typing import Dict, Type

# Maps bot display name → Bot subclass
BOT_REGISTRY: Dict[str, Type] = {}
