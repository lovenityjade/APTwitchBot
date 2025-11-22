"""
!keyitems command
For now, treat items with flags != 0 as 'key items' (heuristic).
"""

from twitchio.ext import commands

class KeyItemsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="keyitems")
    async def keyitems(self, ctx: commands.Context):
        state = self.bot.state
        messages = self.bot.messages

        if not state.exists():
            await ctx.send(messages.format("state_missing"))
            return

        items = state.get_items()
        key_items = [it for it in items if it.get("flags", 0) != 0]

        if not key_items:
            await ctx.send(messages.format("keyitems_empty"))
            return

        # Currently we only print numeric IDs; you can plug data_package later.
        ids = sorted({it.get("item") for it in key_items})
        id_str = ", ".join(str(i) for i in ids)
        msg = messages.format("keyitems_header", list=id_str)
        await ctx.send(msg)
