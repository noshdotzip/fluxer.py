from fluxer.ext import commands


class DemoExtension(commands.Cog):
    @commands.command()
    async def extping(self, ctx: commands.Context):
        await ctx.reply("ext pong")


def setup(bot: commands.Bot):
    bot.add_cog(DemoExtension())


def teardown(bot: commands.Bot):
    bot.remove_cog("DemoExtension")
