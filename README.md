# fluxer.py

A **discord.py-compatible** shim for the Fluxer API.

`fluxer.py` aims to feel like a drop-in replacement for large parts of **discord.py**, while targeting Fluxer’s REST + Gateway APIs. It exposes the same mental model (client/events/commands) and provides typed wrappers for both Discord-like and Fluxer-specific domains.

## Status

- Works today for message bots, commands, and REST.
- Not affiliated with Fluxer or discord.py.
- Designed to stay as close to discord.py’s public API as Fluxer allows.

## Highlights

- `Client` + gateway event system with `wait_for`, `listen`, and caching.
- `commands.Bot` prefix commands with checks, cooldowns, groups, cogs, help, and extensions.
- Rich message helpers: send/edit/delete, reactions, pins, typing.
- Embeds, files, allowed mentions, permissions, and utility helpers.
- Full REST coverage for **all documented Fluxer endpoints** via `client.api`.
- Typed REST models for both Discord-like and Fluxer-specific domains via `client.rest`.

## What’s Implemented

- Core client and events (`on_message`, `on_ready`, raw events).
- Commands framework (`commands.Bot`, checks, cooldowns, help, converters, cogs, extensions).
- REST wrappers and typed models:
  - Discord-like models: `Message`, `TextChannel`, `Guild`, `Member`, `Role`, `Webhook`, `Invite`, `Emoji`, `Sticker`.
  - Fluxer models: `AuthSession`, `OAuth2Application`, `GiftCode`, `ReportResource`, `InstanceDiscovery`, and more.
- Permissions and overwrites (`Permissions`, `PermissionOverwrite`).
- Allowed mentions (`AllowedMentions`).
- Utility helpers (`utils.get`, `utils.find`, `utils.oauth_url`).
- Voice stubs to preserve discord.py API shape.

## What’s Missing (By Fluxer Capability)

- Slash commands / interactions.
- UI components (buttons, selects, modals).
- Voice transport and audio streaming.
- Advanced permission resolution and guild state cache parity.

## Quick Start

```python
from fluxer.ext import commands

bot = commands.Bot(command_prefix='!')

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.reply('pong')

bot.run('YOUR_TOKEN')
```

## REST Usage

Raw REST (all endpoints):

```python
await client.api.channels.send_a_message(
    channel_id='123',
    json={'content': 'hi'}
)
```

Typed REST models:

```python
channel = await client.rest.channels.fetch_a_channel(channel_id='123')
message = await client.rest.channels.fetch_a_message(channel_id='123', message_id='456')
```

Fluxer-specific typed results:

```python
apps = await client.rest.oauth2.list_current_user_applications()
instance = await client.rest.instance.get_instance_discovery_document()
```

## Documentation

- Full docs: `fluxer/DOCS.md`

## Install (From Source)

```bash
git clone <your-repo>
cd fluxer.py
pip install -e .
```

## Contributing

See `CONTRIBUTING.md`.

## License

MIT License. See `LICENSE`.
