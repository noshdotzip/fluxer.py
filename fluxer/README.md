fluxer.py (discord.py-compatible shim)

This is a compatibility layer that targets Fluxer REST + Gateway APIs and mimics a subset of discord.py usage:

- Client + event decorator
- commands.Bot-style prefix commands (checks, cooldowns, converters, cogs, help, groups, permissions, extensions)
- tasks loop utilities (`fluxer.ext.tasks`)
- Embeds (subset) for message send/edit
- Permissions, allowed mentions, colour helpers, and utility functions
- on_message, on_ready, on_command_error, and raw event hooks
- Message send/edit/delete, history, typing
- Dynamic REST API coverage via `client.api` (raw) and `client.rest` (typed models for both Discord-like and Fluxer-specific domains)

Full docs: `fluxer/DOCS.md`.

Generating the API map:

- Install `requests` (dev-only dependency).
- `python fluxer/scripts/generate_api.py` will fetch docs and write `fluxer/api_endpoints.json`.
- The runtime `API` class loads that file and exposes endpoints by group.

Example usage:

```python
import fluxer

client = fluxer.Client()

@client.event
async def on_message(message: fluxer.Message):
    if message.content == "!ping":
        await message.reply("pong")

# REST call from docs: https://docs.fluxer.app/api-reference/channels/fetch-a-channel
# await client.api.channels.fetch_a_channel(channel_id="123")
```

Commands usage:

```python
from fluxer.ext import commands

bot = commands.Bot(command_prefix="!", owner_ids={"123"})

@bot.command()
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def ping(ctx: commands.Context):
    await ctx.reply("pong")
```

Fluxer currently does not implement Discord interactions. Intents are supported for compatibility but are ignored by Fluxer gateway.
