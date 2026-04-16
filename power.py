import aiohttp
import discord
from discord.ext import commands
import json
import os
import time
from datetime import datetime, timezone

POWER_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "power.json")
TENOR_API = "https://api.tenor.com/v1/gifs?ids={id}&key=LIVDSRZULELA&media_filter=minimal"

# GIF IDs for each power tier
# To change a GIF: Get the ID from the Tenor URL
# Example: https://tenor.com/view/cool-anime-gif-12345678 -> ID is "12345678"
GIF_IDS = {
    "base": "26908876",      # Mugen/Jin Samurai Champloo
    "soldier": "21087599",   # TODO: Replace with your preferred GIF ID
    "warrior": "21087599",   # hsoxb
    "jisamurai": "26908876", # TODO: Replace with your preferred GIF ID
    "samurai": "26908876",   # TODO: Replace with your preferred GIF ID
}

# Role multipliers
ROLE_MULTIPLIERS = {
    "Soldier": 2,
    "Warrior": 5,
    "Ji-Samurai": 8,
    "Samurai": 10,
}

XP_PER_MESSAGE = 20
COOLDOWN_SECONDS = 15


class Power(commands.Cog):
    """Power level system based on message activity."""

    def __init__(self, bot):
        self.bot = bot
        self.power_data = self._load()
        self._gif_cache = {}

    def _load(self):
        """Load power data from JSON file."""
        try:
            if os.path.exists(POWER_FILE):
                with open(POWER_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[Power] Failed to load power data: {e}")
        return {}

    def _save(self):
        """Save power data to JSON file."""
        try:
            os.makedirs(os.path.dirname(POWER_FILE), exist_ok=True)
            with open(POWER_FILE, "w") as f:
                json.dump(self.power_data, f, indent=2)
        except Exception as e:
            print(f"[Power] Failed to save power data: {e}")

    def _get_user_data(self, guild_id, user_id):
        """Get user's power data."""
        guild_id = str(guild_id)
        user_id = str(user_id)
        
        if guild_id not in self.power_data:
            self.power_data[guild_id] = {}
        
        if user_id not in self.power_data[guild_id]:
            self.power_data[guild_id][user_id] = {
                "xp": 0,
                "last_message": 0
            }
        
        return self.power_data[guild_id][user_id]

    def _add_xp(self, guild_id, user_id, amount):
        """Add XP to a user."""
        user_data = self._get_user_data(guild_id, user_id)
        user_data["xp"] += amount
        user_data["last_message"] = time.time()
        self._save()
        return user_data["xp"]

    async def _get_gif_url(self, gif_id: str) -> str | None:
        """Fetch and cache the direct GIF URL from Tenor's API."""
        if gif_id in self._gif_cache:
            return self._gif_cache[gif_id]
        
        try:
            async with aiohttp.ClientSession() as session:
                api = TENOR_API.format(id=gif_id)
                async with session.get(api) as resp:
                    data = await resp.json()
                media = data["results"][0]["media"][0]
                gif_url = (
                    media.get("gif", {}).get("url")
                    or media.get("tinygif", {}).get("url")
                )
                self._gif_cache[gif_id] = gif_url
                return gif_url
        except Exception as e:
            print(f"[Power] Tenor API error for GIF {gif_id}: {e}")
            return None

    def _has_role(self, member: discord.Member, role_name: str) -> bool:
        """Check if member has a specific role."""
        return any(role.name == role_name for role in member.roles)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Award XP for messages (with cooldown)."""
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return
        
        # Ignore command messages
        if message.content.startswith("."):
            return
        
        user_data = self._get_user_data(message.guild.id, message.author.id)
        current_time = time.time()
        
        # Check cooldown
        if current_time - user_data["last_message"] >= COOLDOWN_SECONDS:
            self._add_xp(message.guild.id, message.author.id, XP_PER_MESSAGE)

    @commands.command()
    async def pbase(self, ctx):
        """Show your base power level."""
        user_data = self._get_user_data(ctx.guild.id, ctx.author.id)
        power_level = user_data["xp"]
        
        async with ctx.typing():
            gif_url = await self._get_gif_url(GIF_IDS["base"])
        
        embed = discord.Embed(
            description=f"Your power level in **base** is: **{power_level:,}**",
            color=discord.Color.blue()
        )
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url
        )
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"{XP_PER_MESSAGE} XP per message • {COOLDOWN_SECONDS}s cooldown")
        await ctx.send(embed=embed)

    @commands.command()
    async def psoldier(self, ctx):
        """Show your power level as a Soldier (2x multiplier)."""
        if not self._has_role(ctx.author, "Soldier"):
            return await ctx.send("❌ You need the **Soldier** role to use this command!")
        
        user_data = self._get_user_data(ctx.guild.id, ctx.author.id)
        base_power = user_data["xp"]
        power_level = base_power * ROLE_MULTIPLIERS["Soldier"]
        
        async with ctx.typing():
            gif_url = await self._get_gif_url(GIF_IDS["soldier"])
        
        embed = discord.Embed(
            description=f"Your power level as a **Soldier** is: **{power_level:,}**",
            color=discord.Color.green()
        )
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url
        )
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"Base: {base_power:,} × {ROLE_MULTIPLIERS['Soldier']} (Soldier)")
        await ctx.send(embed=embed)

    @commands.command()
    async def pwarrior(self, ctx):
        """Show your power level as a Warrior (5x multiplier)."""
        if not self._has_role(ctx.author, "Warrior"):
            return await ctx.send("❌ You need the **Warrior** role to use this command!")
        
        user_data = self._get_user_data(ctx.guild.id, ctx.author.id)
        base_power = user_data["xp"]
        power_level = base_power * ROLE_MULTIPLIERS["Warrior"]
        
        async with ctx.typing():
            gif_url = await self._get_gif_url(GIF_IDS["warrior"])
        
        embed = discord.Embed(
            description=f"Your power level as a **Warrior** is: **{power_level:,}**",
            color=discord.Color.gold()
        )
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url
        )
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"Base: {base_power:,} × {ROLE_MULTIPLIERS['Warrior']} (Warrior)")
        await ctx.send(embed=embed)

    @commands.command()
    async def pjisamurai(self, ctx):
        """Show your power level as a Ji-Samurai (8x multiplier)."""
        if not self._has_role(ctx.author, "Ji-Samurai"):
            return await ctx.send("❌ You need the **Ji-Samurai** role to use this command!")
        
        user_data = self._get_user_data(ctx.guild.id, ctx.author.id)
        base_power = user_data["xp"]
        power_level = base_power * ROLE_MULTIPLIERS["Ji-Samurai"]
        
        async with ctx.typing():
            gif_url = await self._get_gif_url(GIF_IDS["jisamurai"])
        
        embed = discord.Embed(
            description=f"Your power level as a **Ji-Samurai** is: **{power_level:,}**",
            color=discord.Color.red()
        )
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url
        )
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"Base: {base_power:,} × {ROLE_MULTIPLIERS['Ji-Samurai']} (Ji-Samurai)")
        await ctx.send(embed=embed)

    @commands.command()
    async def psamurai(self, ctx):
        """Show your power level as a Samurai (10x multiplier)."""
        if not self._has_role(ctx.author, "Samurai"):
            return await ctx.send("❌ You need the **Samurai** role to use this command!")
        
        user_data = self._get_user_data(ctx.guild.id, ctx.author.id)
        base_power = user_data["xp"]
        power_level = base_power * ROLE_MULTIPLIERS["Samurai"]
        
        async with ctx.typing():
            gif_url = await self._get_gif_url(GIF_IDS["samurai"])
        
        embed = discord.Embed(
            description=f"Your power level as a **Samurai** is: **{power_level:,}**",
            color=discord.Color.purple()
        )
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url
        )
        
        if gif_url:
            embed.set_image(url=gif_url)
        
        embed.set_footer(text=f"Base: {base_power:,} × {ROLE_MULTIPLIERS['Samurai']} (Samurai)")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Power(bot))


