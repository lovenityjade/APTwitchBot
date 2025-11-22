"""
!seedinfo command
"""

from twitchio.ext import commands

class SeedInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="seedinfo")
    async def seedinfo(self, ctx: commands.Context):
        state = self.bot.state
        messages = self.bot.messages

        if not state.exists():
            await ctx.send(messages.format("state_missing"))
            return

        seed, game, server_version = state.get_seedinfo()
        msg = messages.format("seedinfo", seed=seed, game=game, server_version=server_version)
        await ctx.send(msg)
