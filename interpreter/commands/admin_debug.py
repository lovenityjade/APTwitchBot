"""
Admin/debug commands:
- !apreload
- !aplog <lines>
- !apraw <section>
- !apstatus
"""

import os
import json
from twitchio.ext import commands
from ..ap_permissions import is_admin
from ..ap_utils import send_long_message

class AdminDebugCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="apreload")
    async def apreload(self, ctx: commands.Context):
        if not is_admin(ctx, self.bot.config):
            await ctx.send(self.bot.messages.format("admin_only"))
            return

        changed = self.bot.state.reload()
        if changed:
            await ctx.send("state.json reloaded.")
        else:
            await ctx.send("state.json unchanged (no reload needed).")

    @commands.command(name="aplog")
    async def aplog(self, ctx: commands.Context, lines: str = "10"):
        if not is_admin(ctx, self.bot.config):
            await ctx.send(self.bot.messages.format("admin_only"))
            return

        try:
            n = int(lines)
        except ValueError:
            n = 10

        log_path = self.bot.config.get("paths", {}).get("fetcher_log", "logs/fetcher.log")
        if not os.path.exists(log_path):
            await ctx.send("fetcher.log introuvable.")
            return

        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        tail = "".join(all_lines[-n:])
        header = self.bot.messages.format("aplog_tail_header", lines=n)
        await send_long_message(ctx, header + "\n" + tail)

    @commands.command(name="apraw")
    async def apraw(self, ctx: commands.Context, section: str = "room"):
        if not is_admin(ctx, self.bot.config):
            await ctx.send(self.bot.messages.format("admin_only"))
            return

        d = self.bot.state.get_data()
        value = d.get(section, {})
        json_str = json.dumps(value, indent=2, ensure_ascii=False)
        msg = self.bot.messages.format("apraw_section", section=section, json=json_str)
        await send_long_message(ctx, msg)

    @commands.command(name="apstatus")
    async def apstatus(self, ctx: commands.Context):
        if not is_admin(ctx, self.bot.config):
            await ctx.send(self.bot.messages.format("admin_only"))
            return

        state_path = self.bot.config.get("paths", {}).get("state_file", "data/state.json")
        exists = os.path.exists(state_path)
        if exists:
            mtime = os.path.getmtime(state_path)
            items = len(self.bot.state.get_items())
            checked = len(self.bot.state.get_data().get("checked_locations", []) or [])
            await ctx.send(f"state.json OK (items={items}, checks={checked}, mtime={mtime})")
        else:
            await ctx.send("state.json introuvable.")
