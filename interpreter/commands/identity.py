"""
!identity command (alias of !me conceptually).
"""

from twitchio.ext import commands

class IdentityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="identity")
    async def identity(self, ctx: commands.Context):
        state = self.bot.state
        messages = self.bot.messages

        if not state.exists():
            await ctx.send(messages.format("state_missing"))
            return

        d = state.get_data()
        me = d.get("me", {})
        arch = d.get("archipelago", {})

        msg = messages.format(
            "identity",
            slot_name=me.get("slot_name", arch.get("slot_name", "")),
            player_number=me.get("player_number", -1),
            team_number=me.get("team_number", -1),
            game=me.get("game", arch.get("game", ""))
        )
        await ctx.send(msg)
