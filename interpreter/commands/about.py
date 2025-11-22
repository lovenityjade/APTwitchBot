"""
!about command
"""

# AVANT (exemple)
from twitchio.ext import commands
from ..ap_messages import messages
from ..ap_config import config

class About(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="about")
    async def about(self, ctx):
        meta = config.get("meta", {})

        msg = messages.format_message(
            "about.text",
            author=meta.get("author", "Unknown"),
            repo=meta.get("repo", "https://github.com/"),
        )
        await ctx.send(msg)
