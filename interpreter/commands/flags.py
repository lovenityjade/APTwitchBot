"""
!flags command
Simple statistics about item flags.
"""

from twitchio.ext import commands

class FlagsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="flags")
    async def flags(self, ctx: commands.Context):
        state = self.bot.state
        messages = self.bot.messages

        if not state.exists():
            await ctx.send(messages.format("state_missing"))
            return

        items = state.get_items()
        total = len(items)
        # Heuristic: flags != 0 considered "advancement-ish"
        adv = sum(1 for it in items if it.get("flags", 0) != 0)
        junk = total - adv

        msg = messages.format("flags", total=total, adv=adv, junk=junk)
        await ctx.send(msg)
