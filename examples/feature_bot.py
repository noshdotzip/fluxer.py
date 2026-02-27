import asyncio
import io
import json
import os
from typing import Any

import fluxer
from fluxer.ext import commands, tasks


def _load_env(path: str = ".env") -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    env: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            env[key] = value
    return env


ENV = _load_env()
TOKEN = ENV.get("FLUXER_TOKEN", "YOUR_TOKEN")
OWNER_IDS = {item.strip() for item in ENV.get("FLUXER_OWNER_IDS", "").split(",") if item.strip()}

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    allowed_mentions=fluxer.AllowedMentions.none(),
    owner_ids=OWNER_IDS or None,
)


def _pretty(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)[:1900]
    except Exception:
        return str(data)[:1900]


async def _safe(ctx: commands.Context, coro, *, label: str = "result"):
    try:
        result = await coro
        if result is None:
            await ctx.reply(f"{label}: ok")
            return
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        await ctx.reply(f"{label}: {_pretty(result)}")
    except Exception as exc:
        await ctx.reply(f"{label} error: {type(exc).__name__} {exc}")


def _confirm(value: str) -> bool:
    return value.lower() in {"y", "yes", "confirm", "true"}


async def _get_channel(ctx: commands.Context, channel_id: str | None):
    if channel_id:
        return await bot.fetch_channel(channel_id)
    return ctx.channel


def _require_guild(ctx: commands.Context):
    if not ctx.guild_id:
        raise commands.NoPrivateMessage()
    return ctx.guild_id


@bot.event
async def on_ready():
    print("ready as", bot.user)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    await ctx.reply(f"error: {error}")


@bot.before_invoke
async def _before(ctx: commands.Context):
    # Basic hook example
    return None


@bot.after_invoke
async def _after(ctx: commands.Context):
    return None


@tasks.loop(seconds=60)
async def heartbeat():
    print("heartbeat")


class DemoCog(commands.Cog):
    @commands.command()
    async def cogping(self, ctx: commands.Context):
        await ctx.reply("cog pong")

    @commands.Cog.listener()
    async def on_message(self, message: fluxer.Message):
        # Example listener
        if message.content == "!coglisten":
            await message.reply("heard you")


bot.add_cog(DemoCog())


@bot.command(help="Basic response")
async def ping(ctx: commands.Context):
    await ctx.reply("pong")


@bot.command(help="Embed demo")
async def embed(ctx: commands.Context):
    emb = fluxer.Embed(title="Fluxer", description="Embed demo", color=fluxer.Colour.random())
    await ctx.send(embed=emb)


@bot.command(help="Colour helper demo")
async def colour(ctx: commands.Context):
    c = fluxer.Colour.random()
    await ctx.reply(f"colour: {int(c)} rgb={c.to_rgb()}")


@bot.command(help="File upload demo")
async def file(ctx: commands.Context):
    data = io.BytesIO(b"fluxer.py demo file")
    f = fluxer.File(fp=data, filename="demo.txt", content_type="text/plain")
    await ctx.send("file attached", file=f)


@bot.command(help="Edit message demo")
async def edit(ctx: commands.Context):
    msg = await ctx.send("editing in 1s")
    await asyncio.sleep(1)
    await msg.edit(content="edited")


@bot.command(help="Delete message by id")
async def delete(ctx: commands.Context, message_id: str):
    msg = await ctx.channel.fetch_message(message_id)
    await msg.delete()
    await ctx.reply("deleted")


@bot.command(help="Typing indicator demo")
async def typing(ctx: commands.Context):
    await ctx.typing()
    await asyncio.sleep(1)
    await ctx.reply("typed")


@bot.command(help="Change presence demo")
async def presence(ctx: commands.Context, status: str = "online"):
    await _safe(ctx, bot.change_presence(status=status), label="presence")


@bot.command(help="History demo")
async def history(ctx: commands.Context, limit: int = 5):
    msgs = await ctx.channel.history(limit=limit)
    lines = [f"{m.author}: {m.content}" for m in msgs]
    await ctx.reply("\n".join(lines) or "no messages")


@bot.command(help="Add reaction")
async def react(ctx: commands.Context, message_id: str, emoji: str = "👍"):
    msg = await ctx.channel.fetch_message(message_id)
    await msg.add_reaction(emoji)
    await ctx.reply("reacted")


@bot.command(help="Remove reaction")
async def unreact(ctx: commands.Context, message_id: str, emoji: str = "👍"):
    msg = await ctx.channel.fetch_message(message_id)
    await msg.remove_reaction(emoji)
    await ctx.reply("unreacted")


@bot.command(help="Pin message")
async def pin(ctx: commands.Context, message_id: str):
    msg = await ctx.channel.fetch_message(message_id)
    await msg.pin()
    await ctx.reply("pinned")


@bot.command(help="Unpin message")
async def unpin(ctx: commands.Context, message_id: str):
    msg = await ctx.channel.fetch_message(message_id)
    await msg.unpin()
    await ctx.reply("unpinned")


@bot.command(help="List pins")
async def pins(ctx: commands.Context):
    items = await ctx.channel.pins()
    await ctx.reply(f"pins: {len(items)}")


@bot.command(help="Bulk delete last N messages")
@commands.has_permissions(manage_messages=True)
async def bulk(ctx: commands.Context, count: int = 3):
    msgs = await ctx.channel.history(limit=count)
    await ctx.channel.bulk_delete(msgs)
    await ctx.reply("bulk deleted")


@bot.command(help="Set channel permissions (requires manage_channels)")
@commands.has_permissions(manage_channels=True)
async def setperm(ctx: commands.Context, target_id: str, allow_send: str = "false"):
    overwrite = fluxer.PermissionOverwrite(send_messages=_confirm(allow_send))
    await ctx.channel.set_permissions(target_id, overwrite=overwrite)
    await ctx.reply("permissions updated")


@bot.command(help="Schedule a message (timestamp + content)")
async def schedule(ctx: commands.Context, timestamp: str, *, content: str):
    await _safe(
        ctx,
        ctx.channel.schedule_message(content, scheduled_for=timestamp),
        label="schedule",
    )


@bot.command(help="Call status for channel")
async def call_status(ctx: commands.Context, channel_id: str | None = None):
    channel = await _get_channel(ctx, channel_id)
    await _safe(ctx, channel.call_status(), label="call status")


@bot.command(help="Ring call recipients")
async def call_ring(ctx: commands.Context, channel_id: str | None = None):
    channel = await _get_channel(ctx, channel_id)
    await _safe(ctx, channel.ring_call(), label="call ring")


@bot.command(help="Stop ringing")
async def call_stop(ctx: commands.Context, channel_id: str | None = None):
    channel = await _get_channel(ctx, channel_id)
    await _safe(ctx, channel.stop_ringing(), label="call stop")


@bot.command(help="End call")
async def call_end(ctx: commands.Context, channel_id: str | None = None):
    channel = await _get_channel(ctx, channel_id)
    await _safe(ctx, channel.end_call(), label="call end")


@bot.command(help="List RTC regions")
async def rtc_regions(ctx: commands.Context, channel_id: str | None = None):
    channel = await _get_channel(ctx, channel_id)
    await _safe(ctx, channel.list_rtc_regions(), label="rtc regions")


@bot.command(help="Update call region")
async def call_region(ctx: commands.Context, region: str, channel_id: str | None = None):
    channel = await _get_channel(ctx, channel_id)
    await _safe(ctx, channel.update_call_region(region=region), label="call region")


@bot.command(help="Voice connect (stub)")
async def voice_connect(ctx: commands.Context, channel_id: str):
    channel = await bot.fetch_channel(channel_id)
    if not isinstance(channel, fluxer.VoiceChannel):
        await ctx.reply("not a voice channel")
        return
    await _safe(ctx, channel.connect(), label="voice connect")


@bot.command(help="Edit channel name (manage_channels)")
@commands.has_permissions(manage_channels=True)
async def channel_edit(ctx: commands.Context, *, name: str):
    updated = await ctx.channel.edit(name=name)
    await ctx.reply(f"renamed: {updated.name}")


@bot.command(help="Delete channel (confirm yes)")
@commands.has_permissions(manage_channels=True)
async def channel_delete(ctx: commands.Context, confirm: str = "no"):
    if not _confirm(confirm):
        await ctx.reply("confirmation required: yes")
        return
    await ctx.channel.delete()


@bot.command(help="Allowed mentions demo")
async def mentions(ctx: commands.Context):
    await ctx.send("@everyone @here", allowed_mentions=fluxer.AllowedMentions.none())


@bot.command(help="Create DM and send")
async def dm(ctx: commands.Context, user_id: str, *, content: str = "hello"):
    user = await bot.fetch_user(user_id)
    await user.send(content)
    await ctx.reply("dm sent")


@bot.command(help="Create invite")
async def invite(ctx: commands.Context):
    inv = await ctx.channel.create_invite()
    await ctx.reply(f"invite: {inv.code}")


@bot.command(help="Fetch guild info")
@commands.guild_only()
async def guild_info(ctx: commands.Context):
    guild = await bot.fetch_guild(_require_guild(ctx))
    await ctx.reply(f"guild: {guild.id} {guild.name}")


@bot.command(help="List guild channels")
@commands.guild_only()
async def guild_channels(ctx: commands.Context):
    guild = await bot.fetch_guild(_require_guild(ctx))
    channels = await guild.fetch_channels()
    names = [c.name or c.id for c in channels]
    await ctx.reply(", ".join(names[:20]) or "none")


@bot.command(help="Fetch guild member")
@commands.guild_only()
async def guild_member(ctx: commands.Context, user_id: str):
    guild = await bot.fetch_guild(_require_guild(ctx))
    member = await guild.fetch_member(user_id)
    await ctx.reply(f"member: {member.user.id} {member.user.username}")


@bot.command(help="Create role (confirm yes)")
@commands.has_permissions(manage_roles=True)
async def role_create(ctx: commands.Context, name: str, confirm: str = "no"):
    if not _confirm(confirm):
        await ctx.reply("confirmation required: yes")
        return
    guild = await bot.fetch_guild(_require_guild(ctx))
    role = await guild.create_role(name=name)
    await ctx.reply(f"role: {role.id}")


@bot.command(help="Create channel (confirm yes)")
@commands.has_permissions(manage_channels=True)
async def channel_create(ctx: commands.Context, name: str, confirm: str = "no"):
    if not _confirm(confirm):
        await ctx.reply("confirmation required: yes")
        return
    guild = await bot.fetch_guild(_require_guild(ctx))
    ch = await guild.create_channel(name=name, type=0)
    await ctx.reply(f"channel: {ch.id}")


@bot.command(help="Kick member (confirm yes)")
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, user_id: str, confirm: str = "no"):
    if not _confirm(confirm):
        await ctx.reply("confirmation required: yes")
        return
    guild = await bot.fetch_guild(_require_guild(ctx))
    await guild.kick(user_id)
    await ctx.reply("kicked")


@bot.command(help="Ban member (confirm yes)")
@commands.has_permissions(ban_members=True)
async def ban(ctx: commands.Context, user_id: str, confirm: str = "no"):
    if not _confirm(confirm):
        await ctx.reply("confirmation required: yes")
        return
    guild = await bot.fetch_guild(_require_guild(ctx))
    await guild.ban(user_id)
    await ctx.reply("banned")


@bot.command(help="Member add role")
@commands.has_permissions(manage_roles=True)
async def member_add_role(ctx: commands.Context, user_id: str, role_id: str):
    member = await bot.fetch_member(_require_guild(ctx), user_id)
    await member.add_roles(role_id)
    await ctx.reply("role added")


@bot.command(help="Member remove role")
@commands.has_permissions(manage_roles=True)
async def member_remove_role(ctx: commands.Context, user_id: str, role_id: str):
    member = await bot.fetch_member(_require_guild(ctx), user_id)
    await member.remove_roles(role_id)
    await ctx.reply("role removed")


@bot.command(help="Role edit (uses converter)")
@commands.has_permissions(manage_roles=True)
async def role_edit(ctx: commands.Context, role: fluxer.Role, *, name: str):
    updated = await role.edit(name=name)
    await ctx.reply(f"role renamed: {updated.name}")


@bot.command(help="Wait for next message from author")
async def waitfor(ctx: commands.Context, timeout: int = 10):
    try:
        msg = await bot.wait_for(
            "message",
            timeout=timeout,
            check=lambda m: m.author.id == ctx.author.id and m.channel_id == ctx.channel_id,
        )
        await ctx.reply(f"got: {msg.content}")
    except Exception:
        await ctx.reply("timeout")


@bot.command(help="Show snowflake time")
async def snowflake(ctx: commands.Context, snowflake_id: str):
    dt = fluxer.utils.snowflake_time(snowflake_id)
    await ctx.reply(str(dt))


@bot.command(help="OAuth URL helper")
async def oauthurl(ctx: commands.Context, client_id: str):
    url = fluxer.utils.oauth_url(client_id, scopes=["bot"])
    await ctx.reply(url)


@bot.command(help="Permissions bitfield demo")
async def perms(ctx: commands.Context):
    p = fluxer.Permissions(send_messages=True, manage_messages=True)
    await ctx.reply(f"permissions: {int(p.value)}")


@bot.command(help="Object demo")
async def obj(ctx: commands.Context, object_id: str):
    o = fluxer.Object(id=object_id)
    await ctx.reply(repr(o))


@bot.command(help="Permission overwrite demo")
async def overwrite(ctx: commands.Context):
    ow = fluxer.PermissionOverwrite(send_messages=False)
    await ctx.reply(_pretty(ow.to_dict()))


@bot.command(help="REST raw example: gateway info")
async def raw_gateway(ctx: commands.Context):
    await _safe(ctx, bot.api.gateway.get_gateway_information(), label="gateway")


@bot.command(help="REST typed example: instance discovery")
async def instance(ctx: commands.Context):
    await _safe(ctx, bot.rest.instance.get_instance_discovery_document(), label="instance")


@bot.command(help="REST typed: list OAuth apps (user tokens only)")
async def oauth_apps(ctx: commands.Context):
    await _safe(ctx, bot.rest.oauth2.list_current_user_applications(), label="oauth apps")


@bot.command(help="REST typed: admin keys (admin only)")
async def admin_keys(ctx: commands.Context):
    await _safe(ctx, bot.rest.admin.list_admin_api_keys(), label="admin keys")


@bot.command(help="REST typed: list connections (user token)")
async def connections(ctx: commands.Context):
    await _safe(ctx, bot.rest.connections.list_user_connections(), label="connections")


@bot.command(help="REST typed: list packs (user token)")
async def packs(ctx: commands.Context):
    await _safe(ctx, bot.rest.packs.list_user_packs(), label="packs")


@bot.command(help="REST typed: search messages")
async def search(ctx: commands.Context, *, query: str):
    await _safe(ctx, bot.rest.search.search_messages(query=query), label="search")


@bot.command(help="Read states (user token)")
async def readstate(ctx: commands.Context, channel_id: str):
    await _safe(
        ctx,
        bot.rest.read_states.mark_channels_as_read(channel_ids=[channel_id]),
        label="read states",
    )


@bot.command(help="Webhook demo (requires manage_webhooks)")
@commands.has_permissions(manage_webhooks=True)
async def webhook(ctx: commands.Context):
    hook = await bot.rest.webhooks.create_webhook(
        channel_id=ctx.channel_id,
        name="fluxer-demo",
    )
    await hook.send("hello from webhook")
    await hook.delete()
    await ctx.reply("webhook ok")


@bot.command(help="Start heartbeat task")
async def task_start(ctx: commands.Context):
    if heartbeat.is_running():
        await ctx.reply("already running")
        return
    heartbeat.start()
    await ctx.reply("started")


@bot.command(help="Stop heartbeat task")
async def task_stop(ctx: commands.Context):
    if not heartbeat.is_running():
        await ctx.reply("not running")
        return
    heartbeat.stop()
    await ctx.reply("stopped")


@bot.command(help="Load demo extension")
async def ext_load(ctx: commands.Context):
    bot.load_extension("examples.extensions.demo_ext")
    await ctx.reply("loaded")


@bot.command(help="Unload demo extension")
async def ext_unload(ctx: commands.Context):
    bot.unload_extension("examples.extensions.demo_ext")
    await ctx.reply("unloaded")


@bot.command(help="Help passthrough")
async def helpme(ctx: commands.Context, *, cmd: str | None = None):
    await ctx.send_help(cmd)


@bot.group(invoke_without_command=True)
async def group(ctx: commands.Context):
    await ctx.reply("group root")

@group.command(name="sub")
async def group_sub(ctx: commands.Context):
    await ctx.reply("group sub")


@bot.command(help="Owner only")
@commands.is_owner()
async def owner(ctx: commands.Context):
    await ctx.reply("owner ok")


@bot.command(help="Guild only")
@commands.guild_only()
async def guildonly(ctx: commands.Context):
    await ctx.reply("guild ok")


@bot.command(help="DM only")
@commands.dm_only()
async def dmonly(ctx: commands.Context):
    await ctx.reply("dm ok")


@bot.command(help="Permissions check")
@commands.has_permissions(manage_messages=True)
async def permcheck(ctx: commands.Context):
    await ctx.reply("perm ok")


@bot.command(help="Bot permissions check")
@commands.bot_has_permissions(send_messages=True)
async def botperm(ctx: commands.Context):
    await ctx.reply("bot perm ok")


@bot.command(help="Role check")
@commands.has_role("moderator")
async def rolecheck(ctx: commands.Context):
    await ctx.reply("role ok")


@bot.command(help="Any role check")
@commands.has_any_role("moderator", "admin")
async def anyrole(ctx: commands.Context):
    await ctx.reply("any role ok")


@bot.command(help="Bot has role check")
@commands.bot_has_role("bot")
async def botrole(ctx: commands.Context):
    await ctx.reply("bot role ok")


@bot.command(help="Bot has any role check")
@commands.bot_has_any_role("bot", "admin")
async def botanyrole(ctx: commands.Context):
    await ctx.reply("bot any role ok")


@bot.command(help="Check any: owner or admin")
@commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))
async def anycheck(ctx: commands.Context):
    await ctx.reply("anycheck ok")


@bot.command(help="Cooldown example")
@commands.cooldown(1, 10, commands.BucketType.USER)
async def cooldown(ctx: commands.Context):
    await ctx.reply("cooldown ok")


@bot.command(help="Max concurrency example")
@commands.max_concurrency(1, per=commands.BucketType.CHANNEL, wait=False)
async def mutex(ctx: commands.Context):
    await ctx.reply("mutex ok")


@bot.command(help="Converter demo")
async def userinfo(ctx: commands.Context, user: fluxer.User):
    await ctx.reply(f"user: {user.id} {user.username}")


@bot.command(help="Member converter demo")
async def memberinfo(ctx: commands.Context, member: fluxer.Member):
    await ctx.reply(f"member: {member.user.id} {member.user.username}")


@bot.command(help="Channel converter demo")
async def channelinfo(ctx: commands.Context, channel: fluxer.TextChannel):
    await ctx.reply(f"channel: {channel.id} {channel.name}")


if __name__ == "__main__":
    bot.run(TOKEN)
