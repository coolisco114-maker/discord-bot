import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

CASES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cases.json")

def live_ts(timestamp):
    return f"<t:{int(timestamp.timestamp())}:R>"

def _serialize(cases):
    """Convert cases dict to JSON-safe format (stringify keys, serialize datetimes)."""
    result = {}
    for guild_id, gc in cases.items():
        result[str(guild_id)] = {
            "count": gc["count"],
            "data": {
                str(case_num): {
                    **c,
                    "timestamp": c["timestamp"].isoformat()
                }
                for case_num, c in gc["data"].items()
            }
        }
    return result

def _deserialize(raw):
    """Restore cases dict from JSON (restore int keys, parse datetimes)."""
    result = {}
    for guild_id, gc in raw.items():
        result[int(guild_id)] = {
            "count": gc["count"],
            "data": {
                int(case_num): {
                    **c,
                    "timestamp": datetime.fromisoformat(c["timestamp"]).replace(tzinfo=timezone.utc)
                }
                for case_num, c in gc["data"].items()
            }
        }
    return result

# ── UI Helpers ────────────────────────────────────────────────────────────────

def build_cases_embed(member, cases_dict, case_type):
    """Build the warnings or notes embed for a member."""
    if case_type == "warning":
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description=f"**{len(cases_dict)}** warning(s) on record.",
            color=discord.Color.yellow()
        )
    else:
        embed = discord.Embed(
            title=f"Notes for {member.display_name}",
            description=f"**{len(cases_dict)}** note(s) on record.",
            color=discord.Color.blurple()
        )
    embed.set_thumbnail(url=member.display_avatar.url)
    field_label = "Reason" if case_type == "warning" else "Note"
    for _, c in sorted(cases_dict.items()):
        embed.add_field(
            name=live_ts(c["timestamp"]),
            value=f"**{field_label}:** {c['reason']}\n**Moderator:** {c['moderator']}",
            inline=False
        )
    embed.set_footer(text=f"User ID: {member.id}")
    return embed


class ConfirmDeleteView(discord.ui.View):
    """Ephemeral confirm/cancel shown after selecting a case from the dropdown."""

    def __init__(self, case_num, cog, member, original_msg, case_type):
        super().__init__(timeout=120)
        self.case_num = case_num
        self.cog = cog
        self.member = member
        self.original_msg = original_msg
        self.case_type = case_type

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        gc = self.cog._guild_cases(interaction.guild.id)
        if self.case_num in gc["data"]:
            del gc["data"][self.case_num]
            self.cog._save()

        await interaction.response.edit_message(content="✅ Entry deleted.", view=None)

        # Refresh the original public embed
        remaining = self.cog._user_cases(interaction.guild.id, self.member.id, self.case_type)
        if not remaining:
            plural = "warnings" if self.case_type == "warning" else "notes"
            await self.original_msg.edit(
                content=f"**{self.member}** has no {plural}.",
                embed=None,
                view=None
            )
        else:
            new_embed = build_cases_embed(self.member, remaining, self.case_type)
            new_view = CasesView(remaining, self.member, self.cog, self.case_type, interaction.user.id)
            await self.original_msg.edit(embed=new_embed, view=new_view)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class CaseSelectMenu(discord.ui.Select):
    """Ephemeral dropdown listing all cases for the member."""

    def __init__(self, cases_dict, cog, member, original_msg, case_type):
        self.cog = cog
        self.member = member
        self.original_msg = original_msg
        self.case_type = case_type

        entry_label = "warning" if case_type == "warning" else "note"
        options = []
        for i, (case_num, c) in enumerate(sorted(cases_dict.items()), 1):
            reason = c["reason"]
            short_reason = reason[:97] + "..." if len(reason) > 100 else reason
            options.append(discord.SelectOption(
                label=f"#{i} — {short_reason[:50]}",
                description=f"By {c['moderator'][:50]}",
                value=str(case_num)
            ))

        super().__init__(
            placeholder=f"Choose a {entry_label} to delete...",
            options=options[:25],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        case_num = int(self.values[0])
        gc = self.cog._guild_cases(interaction.guild.id)
        case = gc["data"].get(case_num)

        if not case:
            return await interaction.response.edit_message(
                content="This case has already been deleted.", view=None
            )

        entry_label = "warning" if self.case_type == "warning" else "note"
        confirm_view = ConfirmDeleteView(case_num, self.cog, self.member, self.original_msg, self.case_type)
        await interaction.response.edit_message(
            content=(
                f"Delete this {entry_label}?\n"
                f"**Reason:** {case['reason']}\n"
                f"**Moderator:** {case['moderator']}"
            ),
            view=confirm_view
        )


class SelectDeleteView(discord.ui.View):
    """Ephemeral view containing the case select menu."""

    def __init__(self, cases_dict, cog, member, original_msg, case_type, requester_id):
        super().__init__(timeout=120)
        self.requester_id = requester_id
        self.add_item(CaseSelectMenu(cases_dict, cog, member, original_msg, case_type))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the mod who opened this menu can use it.", ephemeral=True
            )
            return False
        return True


class CasesView(discord.ui.View):
    """Public view attached to the warnings/notes embed. Has a single delete button."""

    def __init__(self, cases_dict, member, cog, case_type, requester_id):
        super().__init__(timeout=120)
        self.cases_dict = cases_dict
        self.member = member
        self.cog = cog
        self.case_type = case_type
        self.requester_id = requester_id
        # Dynamically set the button label based on type
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.label = "Delete a Warning" if case_type == "warning" else "Delete a Note"

    @discord.ui.button(label="Delete a Warning", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_warning(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                "You don't have permission to delete cases.", ephemeral=True
            )
        # Fetch fresh cases in case some were already deleted
        fresh = self.cog._user_cases(interaction.guild.id, self.member.id, self.case_type)
        if not fresh:
            return await interaction.response.send_message("No cases left to delete.", ephemeral=True)

        select_view = SelectDeleteView(
            fresh, self.cog, self.member, interaction.message, self.case_type, interaction.user.id
        )
        entry_label = "warning" if self.case_type == "warning" else "note"
        await interaction.response.send_message(
            f"Select a {entry_label} to delete:",
            view=select_view,
            ephemeral=True
        )


# ── Moderation Cog ────────────────────────────────────────────────────────────

class Moderation(commands.Cog):
    """Moderation commands for managing the server."""

    def __init__(self, bot):
        self.bot = bot
        self.cases = self._load()

    def _load(self):
        try:
            if os.path.exists(CASES_FILE):
                with open(CASES_FILE, "r") as f:
                    return _deserialize(json.load(f))
        except Exception as e:
            print(f"[Moderation] Failed to load cases: {e}")
        return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(CASES_FILE), exist_ok=True)
            with open(CASES_FILE, "w") as f:
                json.dump(_serialize(self.cases), f, indent=2)
        except Exception as e:
            print(f"[Moderation] Failed to save cases: {e}")

    def _guild_cases(self, guild_id):
        if guild_id not in self.cases:
            self.cases[guild_id] = {"count": 0, "data": {}}
        return self.cases[guild_id]

    def _add_case(self, guild_id, case_type, user, moderator, reason):
        gc = self._guild_cases(guild_id)
        gc["count"] += 1
        case_num = gc["count"]
        gc["data"][case_num] = {
            "type": case_type,
            "user_id": user.id,
            "user": str(user),
            "moderator_id": moderator.id,
            "moderator": str(moderator),
            "reason": reason,
            "timestamp": discord.utils.utcnow()
        }
        self._save()
        return case_num

    def _user_cases(self, guild_id, user_id, case_type=None):
        gc = self._guild_cases(guild_id)
        return {
            num: c for num, c in gc["data"].items()
            if c["user_id"] == user_id and (case_type is None or c["type"] == case_type)
        }

    async def _check_escalation(self, channel: discord.TextChannel, guild: discord.Guild, member: discord.Member):
        """Apply automatic escalation rules after any warn or note is issued."""

        # ── 1. Convert every pair of notes into 1 warning ────────────────────
        while True:
            notes = self._user_cases(guild.id, member.id, "note")
            if len(notes) < 2:
                break

            oldest_two = sorted(notes.items())[:2]
            note_reasons = [c["reason"] for _, c in oldest_two]
            gc = self._guild_cases(guild.id)
            for case_num, _ in oldest_two:
                del gc["data"][case_num]
            self._save()

            combined_reason = f"Note 1: {note_reasons[0]} | Note 2: {note_reasons[1]}"
            self._add_case(guild.id, "warning", member, guild.me, combined_reason)
            total_warns = len(self._user_cases(guild.id, member.id, "warning"))

            embed = discord.Embed(
                description=f"⚠️ **{member.mention}** received an automatic warning — 2 notes converted to 1 warning.",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Total Warnings", value=str(total_warns))
            embed.set_footer(text="Automatic escalation")
            await channel.send(embed=embed)

            try:
                dm = discord.Embed(
                    title=f"⚠️ You've been warned in {guild.name}",
                    description="Your 2 notes have been converted into 1 warning.",
                    color=discord.Color.yellow()
                )
                dm.add_field(name="Reason", value=combined_reason)
                dm.add_field(name="Total Warnings", value=str(total_warns))
                await member.send(embed=dm)
            except discord.Forbidden:
                pass

        # ── 2. Check warning thresholds ───────────────────────────────────────
        total_warns = len(self._user_cases(guild.id, member.id, "warning"))

        if total_warns == 2:
            duration = timedelta(hours=1)
            label = "1 hour"
            reason = "Automatic: reached 2 warnings"
        elif total_warns == 4:
            duration = timedelta(hours=24)
            label = "24 hours"
            reason = "Automatic: reached 4 warnings"
        elif total_warns == 6:
            duration = timedelta(hours=24)
            label = "24 hours"
            reason = "Automatic: reached 6 warnings"
        elif total_warns >= 8:
            try:
                try:
                    dm = discord.Embed(
                        title=f"🔨 You have been banned from {guild.name}",
                        description="You have accumulated 8 warnings.",
                        color=discord.Color.red()
                    )
                    await member.send(embed=dm)
                except discord.Forbidden:
                    pass
                await member.ban(reason="Automatic: reached 8 warnings")
                embed = discord.Embed(
                    description=f"🔨 **{member}** has been automatically **banned** for accumulating 8 warnings.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Automatic escalation")
                await channel.send(embed=embed)
            except discord.Forbidden:
                await channel.send("⚠️ I don't have permission to ban this member.")
            return
        else:
            return

        # ── Apply mute ────────────────────────────────────────────────────────
        try:
            until = discord.utils.utcnow() + duration
            await member.timeout(until, reason=reason)
            embed = discord.Embed(
                description=f"🔇 **{member.mention}** has been automatically muted for **{label}**.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Total Warnings", value=str(total_warns))
            embed.set_footer(text="Automatic escalation")
            await channel.send(embed=embed)
            try:
                dm = discord.Embed(
                    title=f"🔇 You've been muted in {guild.name}",
                    description=f"Duration: **{label}**\nReason: {reason}",
                    color=discord.Color.orange()
                )
                await member.send(embed=dm)
            except discord.Forbidden:
                pass
        except discord.Forbidden:
            await channel.send("⚠️ I don't have permission to mute this member.")

    # ── Kick ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Kick a member from the server."""
        if member == ctx.author:
            return await ctx.send("You can't kick yourself.")
        if member.top_role >= ctx.author.top_role:
            return await ctx.send("You can't kick someone with an equal or higher role.")
        try:
            await member.send(f"You have been **kicked** from **{ctx.guild.name}**.\nReason: {reason}")
        except discord.Forbidden:
            pass
        await member.kick(reason=reason)
        embed = discord.Embed(description=f"✅ **{member}** has been kicked.", color=discord.Color.orange())
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)

    # ── Ban ──────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Ban a member from the server."""
        if member == ctx.author:
            return await ctx.send("You can't ban yourself.")
        if member.top_role >= ctx.author.top_role:
            return await ctx.send("You can't ban someone with an equal or higher role.")
        try:
            await member.send(f"You have been **banned** from **{ctx.guild.name}**.\nReason: {reason}")
        except discord.Forbidden:
            pass
        await member.ban(reason=reason)
        embed = discord.Embed(description=f"✅ **{member}** has been banned.", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)

    # ── Unban ────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_id: int):
        """Unban a user by their ID."""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user)
            embed = discord.Embed(description=f"✅ **{user}** has been unbanned.", color=discord.Color.green())
            embed.add_field(name="Moderator", value=ctx.author.mention)
            await ctx.send(embed=embed)
        except discord.NotFound:
            await ctx.send("That user is not banned or doesn't exist.")

    # ── Mute ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: int = 10, *, reason="No reason provided"):
        """Timeout a member (duration in minutes, default 10)."""
        if member == ctx.author:
            return await ctx.send("You can't mute yourself.")
        if member.top_role >= ctx.author.top_role:
            return await ctx.send("You can't mute someone with an equal or higher role.")
        until = discord.utils.utcnow() + timedelta(minutes=duration)
        await member.timeout(until, reason=reason)
        embed = discord.Embed(
            description=f"✅ **{member}** has been muted for **{duration} minute(s)**.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)

    # ── Unmute ───────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        """Remove a timeout from a member."""
        await member.timeout(None)
        embed = discord.Embed(description=f"✅ **{member}** has been unmuted.", color=discord.Color.green())
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)

    # ── Warn ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Warn a member. Creates a case entry."""
        if member == ctx.author:
            return await ctx.send("You can't warn yourself.")
        if member.bot:
            return await ctx.send("You can't warn a bot.")

        case_num = self._add_case(ctx.guild.id, "warning", member, ctx.author, reason)
        total = len(self._user_cases(ctx.guild.id, member.id, "warning"))

        try:
            dm_embed = discord.Embed(
                title=f"⚠️ You've been warned in {ctx.guild.name}",
                color=discord.Color.yellow()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=True)
            dm_embed.add_field(name="Total Warnings", value=str(total), inline=True)
            dm_embed.set_footer(text=f"Case #{case_num}")
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        embed = discord.Embed(
            description=f"⚠️ **{member}** has been warned.",
            color=discord.Color.yellow()
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Total Warnings", value=str(total), inline=True)
        await ctx.send(embed=embed)

        await self._check_escalation(ctx.channel, ctx.guild, member)

    # ── Note ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def note(self, ctx, member: discord.Member, *, content: str):
        """Add a private note about a member (not sent to user)."""
        if member.bot:
            return await ctx.send("You can't add notes to a bot.")

        case_num = self._add_case(ctx.guild.id, "note", member, ctx.author, content)

        embed = discord.Embed(
            description=f"📝 Note added for **{member}**.",
            color=discord.Color.blurple()
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Note", value=content, inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.set_footer(text="This note is not visible to the user.")
        await ctx.send(embed=embed)

        await self._check_escalation(ctx.channel, ctx.guild, member)

    # ── Warnings ─────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        """View all warnings for a member."""
        user_warns = self._user_cases(ctx.guild.id, member.id, "warning")
        if not user_warns:
            return await ctx.send(f"**{member}** has no warnings.")
        embed = build_cases_embed(member, user_warns, "warning")
        view = CasesView(user_warns, member, self, "warning", ctx.author.id)
        await ctx.send(embed=embed, view=view)

    # ── Notes ────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def notes(self, ctx, member: discord.Member):
        """View all notes for a member."""
        user_notes = self._user_cases(ctx.guild.id, member.id, "note")
        if not user_notes:
            return await ctx.send(f"**{member}** has no notes.")
        embed = build_cases_embed(member, user_notes, "note")
        view = CasesView(user_notes, member, self, "note", ctx.author.id)
        await ctx.send(embed=embed, view=view)

    # ── Delete Case ───────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def delwarn(self, ctx, case_num: int):
        """Delete a specific case by its number."""
        gc = self._guild_cases(ctx.guild.id)
        case = gc["data"].get(case_num)

        if not case:
            return await ctx.send(f"Case #{case_num} not found.")

        del gc["data"][case_num]
        self._save()

        embed = discord.Embed(
            description=f"🗑️ Case #{case_num} has been deleted.",
            color=discord.Color.green()
        )
        embed.add_field(name="Type", value=case["type"].capitalize(), inline=True)
        embed.add_field(name="User", value=case["user"], inline=True)
        embed.add_field(name="Original Reason", value=case["reason"], inline=False)
        embed.set_footer(text=f"Deleted by {ctx.author}")
        await ctx.send(embed=embed)

    # ── Edit Reason ───────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def reason(self, ctx, case_num: int, *, new_reason: str):
        """Edit the reason for an existing case."""
        gc = self._guild_cases(ctx.guild.id)
        case = gc["data"].get(case_num)

        if not case:
            return await ctx.send(f"Case #{case_num} not found.")

        old_reason = case["reason"]
        case["reason"] = new_reason
        self._save()

        embed = discord.Embed(
            description=f"✏️ Case #{case_num} reason updated.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Before", value=old_reason, inline=False)
        embed.add_field(name="After", value=new_reason, inline=False)
        embed.set_footer(text=f"Edited by {ctx.author}")
        await ctx.send(embed=embed)

    # ── Clear All Warns ───────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clearwarns(self, ctx, member: discord.Member):
        """Clear all warnings and notes for a member."""
        gc = self._guild_cases(ctx.guild.id)
        removed = [n for n, c in gc["data"].items() if c["user_id"] == member.id]
        for n in removed:
            del gc["data"][n]
        self._save()
        await ctx.send(f"✅ Cleared **{len(removed)}** case(s) for **{member}**.")

    # ── Purge ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """Delete a number of messages (1-100)."""
        if amount < 1 or amount > 100:
            return await ctx.send("Please specify a number between 1 and 100.")
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"🗑️ Deleted **{len(deleted) - 1}** message(s).")
        await asyncio.sleep(3)
        await msg.delete()

    # ── Slowmode ──────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int = 0):
        """Set slowmode for the current channel (0 to disable)."""
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send("✅ Slowmode disabled.")
        else:
            await ctx.send(f"✅ Slowmode set to **{seconds} second(s)**.")

    # ── Nick ──────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member, *, nickname: str = None):
        """Change a member's nickname (leave blank to reset)."""
        await member.edit(nick=nickname)
        if nickname:
            await ctx.send(f"✅ Changed **{member}**'s nickname to **{nickname}**.")
        else:
            await ctx.send(f"✅ Reset **{member}**'s nickname.")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
