# bots/willow_trees.py
from __future__ import annotations
from typing import Optional
from bots.woodcutter import WoodcutterBot
from config import BotConfig, ConfigManager

class WillowTreesBot(WoodcutterBot):
    """
    Willow Trees bot — specialized version of the Woodcutter bot.
    Inherits all color-based finding logic.
    """
    name = "Willow Trees"

    def __init__(self, config: Optional[BotPreset] = None) -> None:
        # We call the parent init, which handles standard setup.
        # If no config is passed, it uses the global ConfigManager.
        super().__init__(config=config)

WillowTreesBot.register()
