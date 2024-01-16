from diskcache import Index
from pathlib import Path
import discord
import hashlib
import json
import os
import re
import yaml

client = discord.Client(intents=discord.Intents.default())
command_tree = discord.app_commands.tree.CommandTree(client)

# Persistent store for miscellaneous data
misc_store = Index("data/misc/")

foods = yaml.full_load(Path("foods.yaml").read_text())


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


def canonicalize_food_name(food_name: str) -> str:
    """
    Convert a food name to a standarized form
    """
    food_name = food_name.lower()
    food_name = re.sub(r"\(.+\)", "", food_name)  # Strip e.g. "(1 slice)"
    food_name = food_name.strip()
    return food_name


def find_food(food_name: str) -> dict | None:
    """
    Find the food item corresponding to the name

    To improve the success of finding the item, we do not require the entire string to match, we instead
    select the result where the highest number of words match
    """
    food_name = canonicalize_food_name(food_name)
    food_name = set(food_name.split())
    result = None
    best_match = 0

    for food in foods:
        candidate = canonicalize_food_name(food["name"])
        candidate = set(candidate.split())

        matching = len(candidate & food_name)
        if matching > best_match:
            best_match = matching
            result = food

    return result


@command_tree.command(name="eat", description="Eat food")
@discord.app_commands.rename(food_name="food")
@discord.app_commands.describe(food_name="Food to eat")
async def eat_command(interaction: discord.Interaction, food_name: str):
    food = find_food(food_name)
    if not food:
        await interaction.response.send_message(f"Could not find {food_name} in my food database")
        return

    embed = discord.Embed(title=f"You had a {food['name']}!")
    embed.set_author(name=f"+ {food['calories']} calories!", icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="", value=f"{interaction.user.display_name} just had a {food['name']}!", inline=False)
    embed.add_field(name="", value="Ready for more in 0 seconds.", inline=False)
    embed.set_footer(text=f"Food sent by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


token = os.environ["DISCORD_TOKEN"]
client.run(token)
