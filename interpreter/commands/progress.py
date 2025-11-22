"""
!progress command
"""

from __future__ import annotations

import json
from pathlib import Path

from twitchio.ext import commands

from ..ap_messages import messages
from ..ap_state import get_state  # APState global


# Base du projet : .../ap-bridge
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


def _load_config() -> dict:
    """Charge config/config.json, ou {} en cas de problème."""
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class Progress(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="progress")
    async def progress(self, ctx):
        state = get_state()

        # Nombre de checks effectués
        try:
            checked_locations = state.get_checked_locations()
            checked = len(checked_locations)
        except Exception:
            checked = 0

        # On lit l'état brut pour voir room.location_count
        raw_state = state.load_state()
        room = raw_state.get("room") or {}

        total = 0

        # 1) Si le fetcher a un location_count > 0, on l'utilise
        try:
            loc_count = room.get("location_count", 0)
            if isinstance(loc_count, int) and loc_count > 0:
                total = loc_count
        except Exception:
            pass

        # 2) Sinon, on regarde l'override config.archipelago.total_locations_override
        if not total:
            cfg = _load_config()
            arch_cfg = cfg.get("archipelago", {})
            override = arch_cfg.get("total_locations_override")
            if isinstance(override, int) and override > 0:
                total = override

        # 3) Calcul du pourcentage et du restant
        if total > 0:
            percent = (checked / total) * 100.0
            remaining = total - checked
        else:
            percent = 0.0
            remaining = 0

        msg = messages.format_message(
            "progress.line",
            a=checked,
            b=total,
            c=f"{percent:.1f}",
            d=remaining,
        )
        await ctx.send(msg)
