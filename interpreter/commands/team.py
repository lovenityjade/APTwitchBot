"""
!team command
Currently a simple solo/multi placeholder.
"""

from twitchio.ext import commands

class TeamCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="team")
    async def team(self, ctx: commands.Context):
        state = self.bot.state
        messages = self.bot.messages

        if not state.exists():
            await ctx.send(messages.format("state_missing"))
            return

        d = state.get_data()
        me = d.get("me", {})
        team_number = me.get("team_number", -1)

        # For now we assume solo, but leave hook for future multi-team support.
        if team_number in (-1, 0):
            await ctx.send(messages.format("team_solo"))
        else:
            # Future: once we have team composition in state, list players
            await ctx.send(messages.format("team_multi_header", team_number=team_number, list="(TODO)"))
