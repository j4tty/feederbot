from datetime import datetime, timezone
from diskcache import Index
from pathlib import Path
import discord
import hashlib
import json
import os
import random
import re
import yaml

client = discord.Client(intents=discord.Intents.default())
command_tree = discord.app_commands.tree.CommandTree(client)

# Persistent store for miscellaneous data
misc_store = Index("data/misc/")
user_store = Index("data/users/")

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
    select the result where the highest number of words match. If there are multiple, return one randomly.
    """

    food_name = canonicalize_food_name(food_name)
    if food_name == "random":
        return random.choice(foods)

    food_name = set(food_name.split())
    result = []
    best_match = 0

    for food in foods:
        candidate = canonicalize_food_name(food["name"])
        candidate = set(candidate.split())

        matching = len(candidate & food_name)

        if matching > best_match:
            best_match = matching
            result = [food]
        elif matching == best_match and matching > 0:
            result.append(food)

    if not result:
        return None

    return random.choice(result)


async def feed(feeder: discord.Member, feedee: discord.Member, food_name: str, interaction: discord.Interaction):
    food = find_food(food_name)
    if not food:
        await interaction.response.send_message(f"Could not find {food_name} in my food database")
        return

    user = user_store.get(feedee.id)
    if not user:
        user = {
            "created": datetime.now(timezone.utc),
            "calories": 0,
            "eaten": []
        }
    user["calories"] += food["calories"]
    user["eaten"].append(food["name"])
    user_store[feedee.id] = user

    if feedee == feeder:
        title_text = f"You had a {food['name']}!"
        sub_text = f"{feedee.display_name} just had a {food['name']}!"
    else:
        title_text = f"You were given a {food['name']}!"
        sub_text = f"{feedee.display_name} was given a {food['name']} by {feeder.display_name}!"

    embed = discord.Embed(title=title_text)
    embed.set_author(name=f"+ {food['calories']} calories!", icon_url=feedee.display_avatar.url)
    embed.add_field(name="", value=f"{sub_text}\nReady for more in 0 seconds")
    embed.set_footer(text=f"Food sent by {interaction.user.display_name}", icon_url=feeder.display_avatar.url)
    await interaction.response.send_message(embed=embed)


async def show_stats(user: discord.Member, interaction: discord.Interaction):
    user_data = user_store.get(user.id)
    if not user_data:
        await interaction.response.send_message(f"Could not find {user.display_name} in my user database")
        return

    embed = discord.Embed(title="User statistics")
    embed.set_author(name=f"{user.display_name}", icon_url=user.display_avatar.url)
    embed.add_field(name="Total calories", value=f"{user_data['calories']}")
    user_age = datetime.now(timezone.utc) - user_data['created']
    embed.add_field(name="Days since joining", value=f"{user_age.days}")
    embed.set_footer(text=f"Info requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@command_tree.command(name="stats", description="Show your stats")
@discord.app_commands.describe(user="User to check")
async def stats_command(interaction: discord.Interaction, user: discord.Member | None):
    await show_stats(user or interaction.user, interaction)


@command_tree.command(name="eat", description="Eat food")
@discord.app_commands.rename(food_name="food")
@discord.app_commands.describe(food_name="The food to eat")
async def eat_command(interaction: discord.Interaction, food_name: str):
    await feed(interaction.user, interaction.user, food_name, interaction)


@command_tree.command(name="feed", description="Give food to a user")
@discord.app_commands.rename(food_name="food")
@discord.app_commands.describe(user="The user to receive the food")
@discord.app_commands.describe(food_name="The food to eat")
async def feed_command(interaction: discord.Interaction, user: discord.Member, food_name: str):
    await feed(interaction.user, interaction.user, food_name, interaction)


token = os.environ["DISCORD_TOKEN"]
client.run(token)
