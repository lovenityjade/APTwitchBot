"""
!help command
"""

from twitchio.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context):
        messages = self.bot.messages
        msg = messages.format("help")
        await ctx.send(msg)
