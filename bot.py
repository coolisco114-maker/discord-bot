import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s)")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="Everborne | .help"
    ))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument. Use `.help` for usage.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I don't have the required permissions to do that.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found. Please mention a valid user.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"An error occurred: {error}")
        print(f"Error: {error}")

async def main():
    async with bot:
        await bot.load_extension("cogs.moderation")
        await bot.load_extension("cogs.custom")
        await bot.load_extension("cogs.quote")
        await bot.load_extension("cogs.power")
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN environment variable not set.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
