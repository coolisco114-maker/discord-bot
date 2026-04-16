import aiohttp
import discord
from discord.ext import commands
import platform
import time

START_TIME = time.time()

HUGS_GIF_ID = "20730031"
TENOR_API = "https://api.tenor.com/v1/gifs?ids={id}&key=LIVDSRZULELA&media_filter=minimal"


class Custom(commands.Cog):
    """Custom utility commands."""

    def __init__(self, bot):
        self.bot = bot
        self._hugs_url: str | None = None

    async def _get_hugs_url(self) -> str | None:
        """Fetch and cache the direct gif URL from Tenor's API."""
        if self._hugs_url:
            return self._hugs_url
        try:
            async with aiohttp.ClientSession() as session:
                api = TENOR_API.format(id=HUGS_GIF_ID)
                async with session.get(api) as resp:
                    data = await resp.json()
                media = data["results"][0]["media"][0]
                self._hugs_url = (
                    media.get("gif", {}).get("url")
                    or media.get("tinygif", {}).get("url")
                )
            return self._hugs_url
        except Exception as e:
            print(f"[Hugs] Tenor API error: {e}")
            return None

    @commands.command()
    async def ping(self, ctx):
        """Check the bot's latency."""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: **{latency}ms**",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def serverinfo(self, ctx):
        """Display information about the server."""
        guild = ctx.guild
        embed = discord.Embed(
            title=guild.name,
            description=guild.description or None,
            color=discord.Color.blurple()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            owner = await self.bot.fetch_user(guild.owner_id)
            owner_value = owner.mention
        except Exception:
            owner_value = f"<@{guild.owner_id}>"
        embed.add_field(name="Owner", value=owner_value)
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Channels", value=len(guild.channels))
        embed.add_field(name="Roles", value=len(guild.roles))
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"))
        embed.add_field(name="Server ID", value=guild.id)
        await ctx.send(embed=embed)

    @commands.command()
    async def userinfo(self, ctx, member: discord.Member = None):
        """Display information about a user."""
        member = member or ctx.author
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed = discord.Embed(
            title=str(member),
            color=member.color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Display Name", value=member.display_name)
        embed.add_field(name="User ID", value=member.id)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown")
        embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"))
        embed.add_field(name="Bot", value="Yes" if member.bot else "No")
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def avatar(self, ctx, member: discord.Member = None):
        """Get a user's avatar."""
        member = member or ctx.author
        embed = discord.Embed(
            title=f"{member.display_name}'s Avatar",
            color=discord.Color.blurple()
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def uptime(self, ctx):
        """Show how long the bot has been running."""
        elapsed = int(time.time() - START_TIME)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        embed = discord.Embed(
            title="⏱ Bot Uptime",
            description=f"{hours}h {minutes}m {seconds}s",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def poll(self, ctx, question: str, *options):
        """Create a poll. Usage: !poll "Question" "Option1" "Option2" ..."""
        if len(options) < 2:
            return await ctx.send("Please provide at least 2 options. Use quotes around each option.")
        if len(options) > 10:
            return await ctx.send("Maximum 10 options allowed.")

        emoji_numbers = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        description = "\n".join(f"{emoji_numbers[i]} {opt}" for i, opt in enumerate(options))

        embed = discord.Embed(
            title=f"📊 {question}",
            description=description,
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Poll by {ctx.author.display_name}")
        msg = await ctx.send(embed=embed)

        for i in range(len(options)):
            await msg.add_reaction(emoji_numbers[i])

    @commands.command()
    async def hugs(self, ctx, member: discord.Member = None):
        """Send a hug gif to someone."""
        if not member:
            return await ctx.send("Please mention someone to hug! Usage: `.hugs @user`")
        async with ctx.typing():
            gif_url = await self._get_hugs_url()
        embed = discord.Embed(
            description=f"**{ctx.author.display_name}** hugs **{member.display_name}** 🤗",
            color=discord.Color.pink(),
        )
        if gif_url:
            embed.set_image(url=gif_url)
        await ctx.send(embed=embed)

    @commands.command()
    async def say(self, ctx, *, message: str):
        """Make the bot say something."""
        if not ctx.author.guild_permissions.manage_messages:
            return await ctx.send("You need the Manage Messages permission to use this.")
        await ctx.message.delete()
        await ctx.send(message)

    @commands.command()
    async def help(self, ctx):
        """Show all available commands."""
        embed = discord.Embed(
            title="📖 Command List",
            description="All available commands with the `.` prefix.",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🛡️ Moderation",
            value=(
                "`.kick <user> [reason]` — Kick a member\n"
                "`.ban <user> [reason]` — Ban a member\n"
                "`.unban <user_id>` — Unban by user ID\n"
                "`.mute <user> [minutes] [reason]` — Timeout a member\n"
                "`.unmute <user>` — Remove a timeout\n"
                "`.purge <amount>` — Delete messages (1-100)\n"
                "`.slowmode [seconds]` — Set channel slowmode\n"
                "`.nick <user> [nickname]` — Change nickname"
            ),
            inline=False
        )

        embed.add_field(
            name="⚠️ Warns & Notes",
            value=(
                "`.warn <user> [reason]` — Warn a member (creates a case)\n"
                "`.warnings <user>` — View all warnings for a member\n"
                "`.note <user> <note>` — Add a private note (not sent to user)\n"
                "`.notes <user>` — View all notes for a member\n"
                "`.reason <case#> <reason>` — Edit a case reason\n"
                "`.delwarn <case#>` — Delete a specific case\n"
                "`.clearwarns <user>` — Clear all cases for a member"
            ),
            inline=False

            )
        
        embed.add_field(
            name="🔧 Utility",
            value=(
                "`.ping` — Check bot latency\n"
                "`.serverinfo` — Server information\n"
                "`.userinfo [user]` — User information\n"
                "`.avatar [user]` — Get a user's avatar\n"
                "`.uptime` — Bot uptime\n"
                "`.poll \"Question\" \"Opt1\" \"Opt2\"` — Create a poll\n"
                "`.say <message>` — Make the bot speak\n"
                "`.quote [text]` — Turn a message into a quote card\n"
                "`.hugs <@user>` — Send a hug gif to someone"
            ),
            inline=False
        )

        embed.add_field(
            name="⚡ Power System",
            value=(
                "`.pbase` — Show your base power level\n"
                "`.psoldier` — Soldier power (2x, requires role)\n"
                "`.pwarrior` — Warrior power (5x, requires role)\n"
                "`.pjisamurai` — Ji-Samurai power (8x, requires role)\n"
                "`.psamurai` — Samurai power (10x, requires role)\n"
                "*Gain 20 XP per message (15s cooldown)*"
            ),
            inline=False
        )

        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Custom(bot))
