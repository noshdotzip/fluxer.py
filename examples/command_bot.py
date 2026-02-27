import os

from fluxer.ext import commands


TOKEN = os.environ.get("FLUXER_TOKEN", "")

bot = commands.Bot(command_prefix="!")


@bot.event
async def on_ready():
    print("Fluxer command bot connected")


@bot.command()
async def ping(ctx: commands.Context):
    await ctx.reply("pong")


@bot.command(aliases=["say"])  # !echo hello
async def echo(ctx: commands.Context, *args):
    await ctx.send(" ".join(args) if args else "")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set FLUXER_TOKEN in the environment")
    bot.run(TOKEN)
