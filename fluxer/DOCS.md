# Fluxer.py Docs

## Overview

`fluxer.py` is a compatibility layer that mirrors the **discord.py** programming model where Fluxer exposes equivalent API surfaces. It focuses on:

- Gateway + REST parity (message events, send/edit/delete, typing, basic models)
- Prefix commands (`commands.Bot`) with checks, cooldowns, converters, cogs, help, and groups
- Raw REST access for **all** documented Fluxer domains
- Optional high-level REST wrappers (`client.rest`) that return model objects or generic `Resource` objects

Limitations are driven by Fluxer’s current feature set (e.g., no interactions/slash commands).

## Quick Start

```python
from fluxer.ext import commands

bot = commands.Bot(command_prefix="!", owner_ids={"123"})

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.reply("pong")

bot.run("YOUR_TOKEN")
```

## Core Client

The client mirrors a large subset of `discord.Client` behavior:

- `await client.wait_for("message")`
- `await client.fetch_channel(...)`, `fetch_guild(...)`, `fetch_user(...)`, `fetch_member(...)`
- `await client.change_presence(...)`
- `client.allowed_mentions` default for all message sends
- Basic caches for channels/guilds (populated from gateway events)
- `client.listen()` decorator and `remove_listener()`

Example:

```python
client = fluxer.Client()

@client.event
async def on_ready():
    print("ready", client.user)

message = await client.wait_for("message", timeout=30)
```

## Commands System

### Bot and Command Decorators

```python
@bot.command(help="Say hello")
async def hello(ctx: commands.Context):
    await ctx.send("hello")
```

### Groups and Subcommands

```python
@bot.group(invoke_without_command=True)
async def admin(ctx: commands.Context):
    await ctx.send("admin group")

@admin.command()
async def prune(ctx: commands.Context, count: int = 10):
    await ctx.send(f"Pruning {count}")
```

### GroupMixin and Qualified Names

Groups expose qualified names and nested resolution:

```python
cmd = bot.get_command("admin prune")
print(cmd.qualified_name)  # "admin prune"
```

### Cogs

```python
class Moderation(commands.Cog):
    @commands.command()
    async def kick(self, ctx: commands.Context, user_id: int):
        await ctx.send(f"Kick {user_id}")

bot.add_cog(Moderation())
```

### Help Command

A default `help` command is installed. It displays nested groups with indentation and qualified names.

You can override it by passing a custom `HelpCommand` to `Bot(help_command=...)`.

## Checks and Permissions

### Built-in Checks

- `guild_only()`
- `dm_only()`
- `is_owner()`
- `has_permissions(...)`
- `bot_has_permissions(...)`
- `has_guild_permissions(...)`
- `bot_has_guild_permissions(...)`
- `is_admin()`
- `has_role(...)`
- `has_any_role(...)`
- `bot_has_role(...)`
- `bot_has_any_role(...)`
- `check_any(...)`

Example:

```python
@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
async def purge(ctx: commands.Context):
    await ctx.send("ok")
```

**Note**: Permission checks are based on the member permission bitfield available from Fluxer’s member payload. If Fluxer uses different permission field names, update `_permission_value` in `fluxer/ext/commands/__init__.py` and `PERMISSIONS` in `fluxer/permissions.py`.

### Role Checks

```python
@bot.command()
@commands.has_role("moderator")
async def mod_only(ctx: commands.Context):
    await ctx.send("ok")
```

## Cooldowns

```python
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.USER)
async def slow(ctx: commands.Context):
    await ctx.send("rate limited")
```

## Max Concurrency

```python
@bot.command()
@commands.max_concurrency(1, per=commands.BucketType.GUILD, wait=False)
async def exclusive(ctx: commands.Context):
    await ctx.send("one at a time")
```

## Before/After Invoke Hooks

```python
@bot.before_invoke
async def before(ctx: commands.Context):
    pass

@bot.after_invoke
async def after(ctx: commands.Context):
    pass

@some_command.before_invoke
async def before_cmd(ctx: commands.Context):
    pass
```

## Converters

Supported converters:

- `User`, `Member`, `Guild`, `TextChannel`, `Role`, `Message`
- Custom converter classes by subclassing `commands.Converter`

Example:

```python
@bot.command()
async def info(ctx: commands.Context, user: commands.UserConverter):
    await ctx.send(user.username)
```

Converters parse IDs from mentions or URLs when possible.

## Mentions as Prefix

Use `when_mentioned_or` to accept bot mentions as a prefix:

```python
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"))
```

## Error Handling

Errors are surfaced via `on_command_error` (bot-level), a per-command `.error` handler, or `cog_command_error` on a Cog.

Example:

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    await ctx.send(str(error))
```

## Extensions

`fluxer.ext.commands` supports module-based extensions similar to discord.py. Each extension must define `setup(bot)`.

```python
bot.load_extension("my_bot.extensions.moderation")
```

Optional `teardown(bot)` is called on unload.

## Tasks

Use `fluxer.ext.tasks.loop` for background tasks:

```python
from fluxer.ext import tasks

@tasks.loop(seconds=60)
async def heartbeat():
    print("tick")

heartbeat.start()
```

## Permissions and Overwrites

`fluxer.Permissions` and `fluxer.PermissionOverwrite` mirror discord.py’s bitfield helpers:

```python
perms = fluxer.Permissions(send_messages=True, manage_messages=True)
overwrite = fluxer.PermissionOverwrite(send_messages=False)
await channel.set_permissions(role, overwrite=overwrite)
```

## Allowed Mentions

Use `AllowedMentions` to control mention parsing globally or per send:

```python
client = fluxer.Client(allowed_mentions=fluxer.AllowedMentions.none())
await channel.send("hi", allowed_mentions=fluxer.AllowedMentions(users=True))
```

## Utilities

Common helpers live in `fluxer.utils`:

- `utils.get`, `utils.find`
- `utils.utcnow`, `utils.snowflake_time`, `utils.time_snowflake`
- `utils.oauth_url(...)`

Alias modules for discord.py parity:

- `fluxer.file.File`
- `fluxer.color.Color` / `fluxer.colour.Colour`
- `fluxer.mentions.AllowedMentions`

## Enums

Basic enums are included for parity:

- `fluxer.Status`
- `fluxer.ChannelType`

## Models and Messageables

High-level objects expose discord.py-like helpers:

- `User.send`, `User.create_dm`
- `Member.add_roles`, `Member.remove_roles`, `Member.ban`, `Member.kick`
- `Guild.fetch_channels`, `fetch_members`, `create_channel`, `create_role`, `ban`, `kick`
- `TextChannel.send`, `edit`, `delete`, `pins`, `bulk_delete`, `schedule_message`, `set_permissions`
- `Message.reply`, `edit`, `delete`, `add_reaction`, `remove_reaction`, `pin`
- `Webhook.send`, `Webhook.edit`, `Webhook.delete`

## Voice (Stub)

Fluxer exposes call/voice-related REST endpoints, but a full voice transport is not documented for bots. The `VoiceClient` and `VoiceChannel.connect()` APIs are present for parity but currently raise `NotImplementedError`.

## REST Models

High-level REST wrappers return typed models across Discord-like and Fluxer-specific domains.

Discord-like:

- `Invite`, `Webhook`, `Emoji`, `Sticker`, `Role`, `Message`, `TextChannel`, `Guild`, `Member`, `User`

Fluxer-specific:

- `AdminResource`, `AuthSession`, `OAuth2Application`, `OAuth2Token`, `InstanceDiscovery`, `BillingSession`
- `Connection`, `DiscoveryResource`, `DonationSession`, `GiftCode`, `KlipyGif`, `PackResource`
- `PremiumSubscription`, `ReportResource`, `SavedMediaItem`, `SearchResult`, `TenorGif`, `ThemeResource`
- `GatewayInfo`, `HealthStatus`

All Fluxer-specific models inherit from `DomainModel`, which exposes `raw`, `to_dict()`, and convenience `id`/`name` properties.

Use `client.rest` to receive these objects. Image endpoints remain generic.

## REST Usage

### Raw REST

`client.api.<group>.<endpoint>(...)` maps directly to Fluxer docs:

```python
await client.api.channels.send_a_message(
    channel_id="123",
    json={"content": "hi"}
)
```

### High-level REST

`client.rest` wraps common endpoints into model objects where possible:

```python
channel = await client.rest.channels.fetch_a_channel(channel_id="123")
message = await client.rest.channels.fetch_a_message(channel_id="123", message_id="456")
```

Example for Fluxer-specific domains:

```python
keys = await client.rest.admin.list_admin_api_keys()
info = await client.rest.instance.get_instance_discovery_document()
```

Some Fluxer domains include a hyphenated name (e.g. `read-states`, `saved-media`). These are exposed with underscore aliases:

- `client.api.read_states`
- `client.rest.saved_media`

## Limits vs discord.py

- No slash commands/interactions (Fluxer does not implement them)
- No voice streaming transport
- Some discord.py conveniences (UI components, advanced permission resolution) are not implemented yet
