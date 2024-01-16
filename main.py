from diskcache import Index
import discord
import hashlib
import json
import os

client = discord.Client(intents=discord.Intents.default())
command_tree = discord.app_commands.tree.CommandTree(client)

# Persistent store for miscellaneous data
misc_store = Index("data/misc/")


async def sync_commands():
    """
    Synchronize the current command tree

    This is an expensive operation that discord heavily rate-limits, which might be an issue during
    development if we were to perform it every time. For that reason we compute a hash of the current
    commands configuration and only sync if it has changed or if the bot has been added to a new guild.
    """
    current_commands = [command.to_dict() for command in command_tree.get_commands()]
    current_commands.sort(key=lambda command: command["name"])
    current_commands = hashlib.sha256(json.dumps(current_commands, sort_keys=True).encode()).hexdigest()

    last_synced_commands = misc_store.get("synced_commands", {})
    synced_commands = {}
    sync_required = False

    for guild in client.guilds:
        if last_synced_commands.get(guild.id) != current_commands:
            command_tree.copy_global_to(guild=guild)
            sync_required = True
        synced_commands[guild.id] = current_commands

    if sync_required:
        print(f"Syncing commands {current_commands}")
        await command_tree.sync()
        misc_store["synced_commands"] = synced_commands
    else:
        print("Commands are already up to date")


@client.event
async def on_ready():
    print("Ready!")
    await sync_commands()


token = os.environ["DISCORD_TOKEN"]
client.run(token)
