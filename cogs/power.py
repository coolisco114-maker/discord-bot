import aiohttp
import discord
from discord.ext import commands
import json
import os
import time
from datetime import datetime, timezone

from pymongo import MongoClient

client = MongoClient(os.getenv("MONGO_URI"))
db = client["discord_bot"]
collection = db["power"]


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
    def __init__(self, bot):
        self.bot = bot
        self.power_data = None
        self._gif_cache = {}

    def _get_user_data(self, guild_id, user_id):
        data = collection.find_one({
            "guild_id": str(guild_id),
            "user_id": str(user_id)
        })
        
        if not data:
            data = {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "xp": 0,
                "last_message": 0
            }
            collection.insert_one(data)
        
        return data

    def _add_xp(self, guild_id, user_id, amount):
        user = self._get_user_data(guild_id, user_id)
        
        new_xp = user["xp"] + amount
        
        collection.update_one(
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id)
            },
            {
                "$set": {
                    "xp": new_xp,
                    "last_message": time.time()
                }
            }
        )
        
        return new_xp

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
        
        user_data = self._get_user_data(message.guild.id, message.author.id)
        current_time = time.time()
        
        # Check cooldown
        if current_time - user_data["last_message"] >= COOLDOWN_SECONDS:
            self._add_xp(message.guild.id, message.author.id, XP_PER_MESSAGE)

        await self.bot.process_commands(message)

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

    @commands.command(name="power")
    @commands.has_permissions(manage_messages=True)
    async def power_manage(self, ctx, action: str = None, member: discord.Member = None, value: int = None):
        """Manage user power levels (Admin only).
        
        Usage:
        .power add @user <amount> - Add power to a user
        .power set @user <amount> - Set user's power to a specific value
        .power remove @user <amount> - Remove power from a user
        .power reset @user - Reset user's power to 0
        """
        if not action:
            embed = discord.Embed(
                title="⚡ Power Management",
                description="Admin commands for managing user power levels.",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="Commands",
                value=(
    "`.power add @user <amount>` — Add power\n"
    "`.power set @user <amount>` — Set power\n"
    "`.power remove @user <amount>` — Remove power\n"
    "`.power reset @user` — Reset to 0"
),
                inline=False
            )
            return await ctx.send(embed=embed)
        
        action = action.lower()
        
        if action == "reset":
            if not member:
                return await ctx.send("❌ Please mention a user! Usage: `.power reset @user`")
            
            user_data = self._get_user_data(ctx.guild.id, member.id)
            old_power = user_data["xp"]
            user_data["xp"] = 0
            
            embed = discord.Embed(
                description=f"✅ Reset **{member.display_name}**'s power level!",
                color=discord.Color.green()
            )
            embed.add_field(name="Previous Power", value=f"{old_power:,}")
            embed.add_field(name="New Power", value="0")
            embed.set_footer(text=f"Reset by {ctx.author.display_name}")
            return await ctx.send(embed=embed)
        
        if not member:
            return await ctx.send(f"❌ Please mention a user! Usage: `.power {action} @user <amount>`")
        
        if value is None:
            return await ctx.send(f"❌ Please provide an amount! Usage: `.power {action} @user <amount>`")
        
        if value < 0:
            return await ctx.send("❌ Amount must be positive!")
        
        user_data = self._get_user_data(ctx.guild.id, member.id)
        old_power = user_data["xp"]
        
        if action == "add":
            user_data["xp"] += value
            action_text = "Added"
            change = f"+{value:,}"
        elif action == "set":
            user_data["xp"] = value
            action_text = "Set"
            change = f"={value:,}"
        elif action == "remove":
            user_data["xp"] = max(0, user_data["xp"] - value)
            action_text = "Removed"
            change = f"-{value:,}"
        else:
            return await ctx.send(f"❌ Invalid action! Use: `add`, `set`, `remove`, or `reset`")
        
        new_power = user_data["xp"]
        
        embed = discord.Embed(
            description=f"✅ {action_text} power for **{member.display_name}**!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Previous Power", value=f"{old_power:,}")
        embed.add_field(name="Change", value=change)
        embed.add_field(name="New Power", value=f"{new_power:,}")
        embed.set_footer(text=f"Modified by {ctx.author.display_name}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Power(bot))


