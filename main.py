import json
import os
import random
import asyncio
import time
import typing as T

import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = os.getenv('DISCORD_GUILD')
GENERAL_CHANNEL = int(os.getenv('DISCORD_GENERAL_CHANNEL'))

intents = discord.Intents(messages=True, guilds=True, message_content=True)
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    channel = client.get_channel(GENERAL_CHANNEL)

    loop = asyncio.get_event_loop()
    global SHOW_COMMAND_PERIODIC
    SHOW_COMMAND_PERIODIC = Periodic(show_command, 600, 30, channel, [])
    loop.create_task(SHOW_COMMAND_PERIODIC.run())

    await channel.send("Dune RPG Helper is ready to help! type 'dune help' to see available commands")


class LocalCache:
    def __init__(self):
        self.cache_filepath = 'cache.json'
        self.cache = {}
        self.load_cache()

    def save_cache(self):
        with open(self.cache_filepath, 'w') as file_obj:
            json.dump(self.cache, file_obj)

    def load_cache(self):
        if not os.path.exists(self.cache_filepath):
            self.save_cache()

        with open(self.cache_filepath, 'r') as file_obj:
            self.cache = json.load(file_obj)

    def get(self, key, default=None):
        return self.cache.get(key, default)

    def set(self, key, value):
        self.cache[key] = value
        self.save_cache()


CACHE = LocalCache()


def d20_roll():
    return random.randint(1, 20)


async def show_command(channel, parts):
    scene = CACHE.get("scene")
    if scene:
        await channel.send(f"Current scene is: **{scene}**")

    try:
        keys = [parts[2]]
    except IndexError:
        keys = ['momentum', 'threat']

    for key in keys:
        if key not in ["momentum", "threat"]:
            print(f"Unknown key: {key}")
            continue

        await channel.send(f"{key} is {CACHE.get(key, 0)}")

    if SHOW_COMMAND_PERIODIC is not None:
        SHOW_COMMAND_PERIODIC.reset()


class Periodic:
    def __init__(self, coro_factory, reset_wait_time: int, message_wait_time: int, *args, **kwargs):
        self.coro_factory = coro_factory
        self.reset_wait_time = reset_wait_time
        self.message_wait_time = message_wait_time
        self.args = args
        self.kwargs = kwargs
        self.last_reset = None
        self.last_message = None

    async def run(self):
        self.reset()

        while True:
            await asyncio.sleep(self.message_wait_time)

            if self.last_reset is not None and self.last_message is not None:
                t = time.time()
                print(f"Last reset was {t - self.last_reset} seconds ago, trigger time is {self.reset_wait_time} seconds")
                print(f"Last message was {t - self.last_message} seconds ago, trigger time is {self.message_wait_time} seconds")

                reset_flag = t > self.last_reset + self.reset_wait_time
                message_flag = t > self.last_message + self.message_wait_time

                if reset_flag and message_flag:
                    await self.coro_factory(*self.args, **self.kwargs)
                    self.reset()

    def reset(self):
        self.last_reset = time.time()

    def got_message(self):
        self.last_message = time.time()


SHOW_COMMAND_PERIODIC: T.Optional[Periodic] = None


async def set_command(channel, parts):
    key = parts[2]

    if key not in ["momentum", "threat"]:
        print(f"Unknown key: {key}")
        return

    original_value = CACHE.get(key, 0)
    new_value = int(parts[3])

    if new_value < 0:
        new_value = 0

    if key == "momentum":
        if new_value > 6:
            new_value = 6

    CACHE.set(key, new_value)
    await channel.send(f"{key} is now {new_value} (was {original_value})")


async def add_or_use_command(channel, parts):
    command = parts[1]
    key = parts[2]

    try:
        count = int(parts[3])
    except IndexError:
        count = 1

    if count < 1:
        print("Count must be positive")
        return

    if command == "use":
        count = -count

    new_value = CACHE.get(key, 0) + count

    if new_value > 5:
        new_value = 5

    await set_command(channel, ["dune", "set", key, new_value])


async def start_scene(channel, parts):
    if CACHE.get("scene"):
        await end_scene(channel)

    name = ' '.join(parts[3:])
    CACHE.set("scene", name)
    await channel.send(f"Starting scene: **{name}**")


async def end_scene(channel):
    name = CACHE.get("scene")
    if name:
        CACHE.set("scene", None)
        await channel.send(f"Ending scene: **{name}**")
    await add_or_use_command(channel, ["dune", "use", "momentum", 1])


@client.event
async def on_message(message: discord.Message):
    print(f"Got message: {message.content}")

    if SHOW_COMMAND_PERIODIC:
        SHOW_COMMAND_PERIODIC.got_message()

    if message.channel.id != GENERAL_CHANNEL:
        print("Not a message in general channel")
        return

    parts = message.content.split(' ')

    if parts[0] != "dune":
        print("Not a dune message")
        return

    channel = message.channel

    command = parts[1]

    if command == "help":
        await channel.send(
            'Available commands:\n'
            'dune help - show this message\n'
            'dune roll <n: required> <threshold: optional> <difficulty: optional> - roll n d20\n'
            'dune show <momentum or threat: optional> - show current group values\n'
            'dune <add or use> <momentum or threat> <n: optional, default is 1> - increase/decrease momentum or threat\n'
            'dune set <momentum or threat> <n: required> - set momentum or threat to n\n'
            'dune scene start <name of the scene: required> - start a new scene\n'
            'dune scene end - end scene, lose one momentum\n'
        )
    elif command == "roll":
        count = int(parts[2])

        try:
            threshold = int(parts[3])
            if not 1 <= threshold <= 20:
                threshold = None
        except IndexError:
            threshold = None

        try:
            difficulty = int(parts[4])
            if not 0 <= difficulty <= 5:
                difficulty = None
        except IndexError:
            difficulty = None

        rolls = []
        total = 0

        for _ in range(count):
            roll = d20_roll()
            rolls.append(roll)
            total += roll

        name = message.author.nick
        if not name:
            name = message.author

        crit = False
        success_count = 0
        for roll in rolls:
            if threshold and roll == 1:
                # crit
                success_count += 2
                crit = True
            elif threshold and roll <= threshold:
                success_count += 1

        if threshold:
            formatted_rolls = ', '.join([f"**{roll}**" if roll <= threshold else str(roll) for roll in rolls])
        else:
            formatted_rolls = ', '.join([str(roll) for roll in rolls])

        await channel.send(f'{name} rolled {count}d20: [{formatted_rolls}] Total: {total}')

        if difficulty is not None:
            if success_count >= difficulty:
                if crit:
                    message = f":boom: **CRITICAL** ({success_count} successes >= difficulty {difficulty})"
                else:
                    message = f":white_check_mark: **SUCCESS** ({success_count} successes >= difficulty {difficulty})"
            else:
                if crit:
                    message = f":thinking: **CRIT?** ({success_count} successes < difficulty {difficulty})"
                else:
                    message = f":x: **FAILURE** ({success_count} successes < difficulty {difficulty})"
            await channel.send(message)

    elif command == "show":
        await show_command(channel, parts)
    elif command in ["add", "use"]:
        await add_or_use_command(channel, parts)
    elif command == "set":
        await set_command(channel, parts)
    elif command == "scene":
        cmd = parts[2]

        if cmd == "start":
            await start_scene(channel, parts)
        elif cmd == "end":
            await end_scene(channel)


if __name__ == "__main__":
    client.run(TOKEN)
