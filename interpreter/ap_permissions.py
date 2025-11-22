"""
APTwitchInterpreter
Created by Jade (TheLovenityJade) - 2025

Permission helpers for admin/mod-only commands.
"""

from twitchio import Message

def is_admin(ctx, config: dict) -> bool:
    """Return True if the user is allowed to run admin commands.

    Rules:
    - If ctx.author.name (lowercase) is in config['bot_settings']['admins'], allow.
    - If allow_mods_as_admin is True and user is mod or broadcaster, allow.
    """
    name = ctx.author.name.lower()
    admins = [a.lower() for a in config.get("bot_settings", {}).get("admins", [])]
    if name in admins:
        return True

    allow_mods = config.get("bot_settings", {}).get("allow_mods_as_admin", True)
    if allow_mods and (ctx.author.is_mod or getattr(ctx.author, "is_broadcaster", False)):
        return True

    return False
