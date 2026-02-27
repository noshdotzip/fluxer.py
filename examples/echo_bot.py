import os

import fluxer


TOKEN = os.environ.get("FLUXER_TOKEN", "")

client = fluxer.Client()


@client.event
async def on_ready():
    print("Fluxer bot connected")


@client.event
async def on_message(message: fluxer.Message):
    if message.author and message.author.bot:
        return

    if message.content == "!ping":
        await message.channel.send("pong")


@client.event
async def on_raw_event(event_name, data):
    # Useful for debugging unsupported events
    pass


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set FLUXER_TOKEN in the environment")
    client.run(TOKEN)
