import discord
import time
import asyncio

from RemindMe.validate_event import count_reminders
from RemindMe.format_time import format_time
from RemindMe.globalvars import reminders
from RemindMe.Reminder import Reminder

from globalvars import restrictions

from get_patrons import get_patrons

async def set_reminder(message, client):
    if isinstance(message.channel, discord.DMChannel):
        await message.channel.send('Please use this in a server for now. Functionality will be ported in the future, but for now use your mention as the reminder\'s destination')
        return

    args = message.content.split(' ')
    args.pop(0) # remove the command item

    if len(args) < 2:
        await message.channel.send(embed=discord.Embed(title='remind', description='**Usage** ```$remind [channel mention or user mention] <time to or time at> <message>```\n\n**Example** ```$remind #general 10s Hello world``` ```$remind 10:30 It\'s now 10:30```'))
        return

    scope = message.channel.id
    pref = '#'

    if args[0].startswith('<'): # if a scope is provided
        if args[0][2:-1][0] == '!':
            tag = int(args[0][3:-1])

        else:
            try:
                tag = int(args[0][2:-1])
            except ValueError:
                await message.channel.send(embed=discord.Embed(description='Please ensure your tag links directly to a user or channel, not a role.'))
                return

        if args[0][1] == '@': # if the scope is a user
            pref = '@'
            scope = message.guild.get_member(tag)

        else:
            pref = '#'
            scope = message.guild.get_channel(tag)

        if scope == None:
            await message.channel.send(embed=discord.Embed(description='Couldn\'t find a location by your tag present.'))
            return

        else:
            scope = scope.id

        args.pop(0)

    msg_time = format_time(args[0], message.guild.id)

    if msg_time == None:
        await message.channel.send(embed=discord.Embed(description='Make sure the time you have provided is in the format of [num][s/m/h/d][num][s/m/h/d] etc. or `day`/`month`/`year`-`hour`:`minute`:`second`.'))
        return

    args.pop(0)

    msg_text = ' '.join(args)

    if count_reminders(scope) > 5 and message.author not in get_patrons('Patrons'):
        await message.channel.send(embed=discord.Embed(description='Too many reminders in specified channel! Use `$del` to delete some of them, or use `$donate` to increase your maximum ($5 tier)'))
        return

    if len(msg_text) > 150 and message.author not in get_patrons('Patrons'):
        await message.channel.send(embed=discord.Embed(description='Reminder message too long! (max 150, you used {}). Use `$donate` to increase your character limit to 1900 ($5 tier)'.format(len(msg_text))))
        return

    if len(msg_text) >= 1900:
        await message.channel.send(embed=discord.Embed(description='Discord restrictions mean we can\'t send reminders 2000+ characters. Sorry'))
        return

    if pref == '#':
        if not message.author.guild_permissions.manage_messages:
            if scope not in restrictions.keys():
                restrictions[scope] = []
            for role in message.author.roles:
                if role.id in restrictions[scope]:
                    break
            else:
                await message.channel.send(embed=discord.Embed(description='You must be either admin or have a role capable of sending reminders to that channel. Please talk to your server admin, and tell her/him to use the `$restrict` command to specify allowed roles.'))
                return

    reminders.append(Reminder(time=msg_time, channel=scope, message=msg_text))
    reminders.sort(key=lambda x: x.time)

    await message.channel.send(embed=discord.Embed(description='New reminder registered for <{}{}> in {} seconds . You can\'t edit the reminder now, so you are free to delete the message.'.format(pref, scope, round(msg_time - time.time()))))
    print('Registered a new reminder for {}'.format(message.guild.name))
