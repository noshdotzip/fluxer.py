import fluxer
from fluxer.ext import commands


bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    allowed_mentions=fluxer.AllowedMentions.none(),
)


@bot.event
async def on_ready():
    print("ready as", bot.user)


@bot.command(help="Ping + wait_for demo")
async def ping(ctx: commands.Context):
    await ctx.send("pong - reply with `ok` in 10s")
    try:
        msg = await bot.wait_for(
            "message",
            timeout=10,
            check=lambda m: m.author.id == ctx.author.id and m.channel_id == ctx.channel_id,
        )
        await ctx.reply(f"got it: {msg.content}")
    except Exception:
        await ctx.reply("timeout")


bot.run("YOUR_TOKEN")
