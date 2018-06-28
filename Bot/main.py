from sloccount import sloccount_py
from models import Reminder, 

import discord
import msgpack
import pytz
import asyncio
import aiohttp

from itertools import chain
from datetime import datetime
import time
import sys
import os
import configparser
import json


class BotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)

        self.times = {
            'last_loop' : time.time(),
            'start' : 0,
            'loops' : 0
        }

        self.commands = {
            'help' : self.help,
            'info' : self.info,
            'donate' : self.donate,

            'prefix' : self.change_prefix,
            'blacklist' : self.blacklist,
            'restrict' : self.restrict,

            'timezone' : self.timezone,
            'clock' : self.clock,
            'lang' : self.language,

            'remind' : self.remind,
            'interval' : self.interval,
            'del' : self.delete,

            'todo' : self.todo,
            'todos' : self.todo,
            'tag' : self.tag,

            'autoclear' : self.autoclear,
            'clear' : self.clear,

            'cleanup' : self.cleanup,
            'welcome' : self.welcome
        }

        self.strings = {

        }

        self.languages = {

        }

        for fn in os.listdir('EXT'):
            if fn.startswith('strings_'):
                with open('EXT/' + fn, 'r') as f:
                    a = f.read()
                    self.strings[fn[8:10]] = eval(a)
                    self.languages[a.split('\n')[0].strip('#:\n ')] = fn[8:10]

        print('Languages enabled: ' + str(self.languages))

        self.donor_roles = {
            1 : [353630811561394206],
            2 : [353226278435946496],
            3 : [353639034473676802, 404224194641920011]
        }

        self.config = configparser.SafeConfigParser()
        self.config.read('config.ini')
        self.dbl_token = self.config.get('DEFAULT', 'dbl_token')
        self.patreon = self.config.get('DEFAULT', 'patreon_enabled') == 'yes'
        self.patreon_servers = [int(x.strip()) for x in self.config.get('DEFAULT', 'patreon_server').split(',')]

        if self.patreon:
            print('Patreon is enabled. Will look for servers {}'.format(self.patreon_servers))

        try:
            with open('DATA/todos.json', 'r') as f:
                self.todos = json.load(f)
                self.todos = {int(x) : y for x, y in self.todos.items()}
        except FileNotFoundError:
            print('No todos file found')
            self.todos = {}

        try:
            with open('DATA/process_deletes.mp', 'rb') as f:
                self.process_deletes = msgpack.unpack(f, encoding='utf8')
        except FileNotFoundError:
            print('No deletes file found')
            self.process_deletes = {}

        try:
            open('EXT/strings_EN.py', 'r').close()
        except FileNotFoundError:
            print('English strings file not present. Exiting...')
            sys.exit()


    def get_server(self, guild):
        self.cursor.execute('SELECT * FROM servers WHERE id = ?', (guild.id, ))
        d = self.cursor.fetchone()

        if d is None:
            return None

        else:
            return ServerData(**dict(d))


    def write_server(self, data):
        print(data)

        command = '''UPDATE servers
        SET prefix = ?, timezone = ?, language = ?, blacklist = ?, restrictions = ?, tags = ?, autoclears = ?
        WHERE id = ?
        '''

        self.cursor.execute(command, (
            data.prefix,
            data.timezone,
            data.language,
            json.dumps(data.blacklist),
            json.dumps(data.restrictions),
            json.dumps(data.tags),
            json.dumps(data.autoclears),
            data.id
        ))

        self.connection.commit()


    def count_reminders(self, loc):
        self.cursor.execute('SELECT * FROM reminders WHERE channel = ?', (loc,))
        return len([r for r in self.cursor.fetchall() if dict(r)['interval'] == None])


    def get_patrons(self, memberid, level=2):
        if self.patreon:
            p_servers = [client.get_guild(x) for x in self.patreon_servers]
            members = []
            for guild in p_servers:
                for member in guild.members:
                    if member.id == memberid:
                        members.append(member)

            roles = []
            for member in members:
                for role in member.roles:
                    roles.append(role.id)

            return bool(set(self.donor_roles[level]) & set(roles))

        else:
            return True


    def parse_mention(self, message, text, server):
        if text[2:-1][0] == '!':
            tag = int(text[3:-1])

        else:
            try:
                tag = int(text[2:-1])
            except ValueError:
                return None, None

        if text[1] == '@': # if the scope is a user
            pref = '@'
            scope = message.guild.get_member(tag)

        else:
            pref = '#'
            scope = message.guild.get_channel(tag)

        if scope is None:
            return None, None

        else:
            return scope.id, pref


    def perm_check(self, message, server):
        if not message.author.guild_permissions.manage_messages:
            for role in message.author.roles:
                if role.id in server.restrictions:
                    return True
            else:
                return False

        else:
            return True


    def length_check(self, message, text):
        if len(text) > 150 and not self.get_patrons(message.author.id):
            return '150'

        if len(text) >= 1900:
            return '2000'

        else:
            return True


    def format_time(self, text, server):
        if '/' in text or ':' in text:
            date = datetime.now(pytz.timezone(server.timezone))

            for clump in text.split('-'):
                if '/' in clump:
                    a = clump.split('/')
                    if len(a) == 2:
                        date = date.replace(month=int(a[1]), day=int(a[0]))
                    elif len(a) == 3:
                        date = date.replace(year=int(a[2]), month=int(a[1]), day=int(a[0]))

                elif ':' in clump:
                    a = clump.split(':')
                    if len(a) == 2:
                        date = date.replace(hour=int(a[0]), minute=int(a[1]))
                    elif len(a) == 3:
                        date = date.replace(hour=int(a[0]), minute=int(a[1]), second=int(a[2]))
                    else:
                        return None

                else:
                    date = date.replace(day=int(clump))

            return date.timestamp()

        else:
            current_buffer = '0'
            seconds = 0
            minutes = 0
            hours = 0
            days = 0

            for char in text:

                if char == 's':
                    seconds = int(current_buffer)
                    current_buffer = '0'

                elif char == 'm':
                    minutes = int(current_buffer)
                    current_buffer = '0'

                elif char == 'h':
                    hours = int(current_buffer)
                    current_buffer = '0'

                elif char == 'd':
                    days = int(current_buffer)
                    current_buffer = '0'

                else:
                    try:
                        int(char)
                        current_buffer += char
                    except ValueError:
                        return None

            time_sec = round(time.time() + seconds + (minutes * 60) + (hours * 3600) + (days * 86400) + int(current_buffer))
            return time_sec


    def get_strings(self, server):
        if server is None:
            return self.strings['EN']
        else:
            return self.strings[server.language]


    async def welcome(self, guild, *args):
        if isinstance(guild, discord.Message):
            guild = guild.guild

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not channel.is_nsfw():
                await channel.send('Thank you for adding reminder-bot! To begin, type `$help`, `mbprefix`, `$lang` or `$timezone` to set your timezone.')
                break
            else:
                continue

        print('done')


    async def cleanup(self, *args):
        command = '''SELECT * FROM servers'''

        self.cursor.execute(command)
        all_ids = [g.id for g in self.guilds]

        for d in self.cursor.fetchall():
            idx = dict(d)['id']

            if idx not in all_ids:
                print('Deleting server {}'.format(idx))
                self.cursor.execute('DELETE FROM servers WHERE id = ?', (idx,))


    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------------')
        await client.change_presence(activity=discord.Game(name='@{} help'.format(self.user.name)))


    async def on_guild_remove(self, guild):
        await self.send()

        await self.cleanup()


    async def on_guild_join(self, guild):
        await self.send()

        await self.welcome(guild)


    async def send(self):
        guild_count = len(self.guilds)
        member_count = len([x for x in self.get_all_members()])

        if not self.dbl_token:
            return

        session = aiohttp.ClientSession()
        dump = json.dumps({
            'server_count': len(client.guilds)
        })

        head = {
            'authorization': self.dbl_token,
            'content-type' : 'application/json'
        }

        url = 'https://discordbots.org/api/bots/stats'
        async with session.post(url, data=dump, headers=head) as resp:
            print('returned {0.status} for {1}'.format(resp, dump))

        session.close()

        async with aiohttp.ClientSession() as session:
            async with session.post('https://api.fusiondiscordbots.com/{}/'.format(self.user.id), data={'token' : 'WxxjHtXWk0-JphXi', 'guilds' : guild_count, 'members' : member_count}) as resp:
                print('returned {0.status} from api.fusiondiscordbots.com'.format(resp))


    async def on_message(self, message):
        if message.guild is not None and self.get_server(message.guild) is None:

            command = '''INSERT INTO servers (id, prefix, timezone, language, blacklist, restrictions, tags, autoclears)
            VALUES (?, "$", "UTC", "EN", "[]", "[]", "{}", "{}")'''

            self.cursor.execute(command, (message.guild.id, ))
            self.connection.commit()

        server = None if message.guild is None else self.get_server(message.guild)
        if server is not None and message.channel.id in server.autoclears.keys():
            self.process_deletes[message.id] = {'time' : time.time() + server.autoclears[message.channel.id], 'channel' : message.channel.id}

        if message.author.bot or message.content == None:
            return

        try:
            if await self.get_cmd(message):
                print('Command: ' + message.content)

        except discord.errors.Forbidden:
            try:
                await message.channel.send('Action forbidden. Please ensure I have the correct permissions.')
            except discord.errors.Forbidden:
                print('Twice Forbidden')

    async def get_cmd(self, message):

        server = None if message.guild is None else self.get_server(message.guild)
        prefix = '$' if server is None else server.prefix

        if message.content.startswith('mbprefix'):
            await self.change_prefix(message, ' '.join(message.content.split(' ')[1:]), server)


        if message.content[0:len(prefix)] == prefix:
            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            if command in self.commands:
                if server is not None and message.channel.id in server.blacklist and not message.content.startswith(('{}help'.format(server.prefix), '{}blacklist'.format(server.prefix))):
                    await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['blacklisted']))
                    return False

                stripped = (message.content + ' ')[message.content.find(' '):].strip()
                await self.commands[command](message, stripped, server)
                return True

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:
            if message.content.split(' ')[1] in self.commands.keys():
                if server is not None and message.channel.id in server.blacklist and not message.content.startswith(('{}help'.format(server.prefix), '{}blacklist'.format(server.prefix))):
                    await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['blacklisted']))
                    return False

                stripped = (message.content + ' ').split(' ', 2)[-1].strip()
                await self.commands[message.content.split(' ')[1]](message, stripped, server)
                return True

        return False


    async def help(self, message, stripped, server):
        embed = discord.Embed(description=self.get_strings(server)['help'])
        await message.channel.send(embed=embed)


    async def info(self, message, stripped, server):
        embed = discord.Embed(description=self.get_strings(server)['info'].format(prefix=server.prefix, sloc=sloccount_py(), user=self.user.name))
        await message.channel.send(embed=embed)


    async def donate(self, message, stripped, server):
        embed = discord.Embed(description=self.get_strings(server)['donate'])
        await message.channel.send(embed=embed)


    async def change_prefix(self, message, stripped, server):
        if server is None:
            return

        if stripped:
            stripped += ' '
            server.prefix = stripped[:stripped.find(' ')]
            await message.channel.send(self.get_strings(server)['prefix']['success'].format(prefix=server.prefix))

        else:
            await message.channel.send(self.get_strings(server)['prefix']['no_argument'].format(prefix=server.prefix))

        self.write_server(server)


    async def timezone(self, message, stripped, server):
        if server is None:
            return

        if stripped == '':
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['timezone']['no_argument'].format(prefix=server.prefix, timezone=server.timezone)))

        else:
            if stripped not in pytz.all_timezones:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['timezone']['no_timezone']))
            else:
                server.timezone = stripped
                d = datetime.now(pytz.timezone(server.timezone))

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['timezone']['success'].format(timezone=server.timezone, time=d.strftime('%H:%M:%S'))))

                self.write_server(server)

    async def language(self, message, stripped, server):
        if server is None:
            return

        if stripped.lower() in self.languages.keys():
            server.language = self.languages[stripped.lower()]
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['lang']['set']))

        elif stripped.upper() in self.languages.values():
            server.language = stripped.upper()
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['lang']['set']))

        else:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['lang']['invalid'].format('\n'.join(['{} ({})'.format(x.title(), y.upper()) for x, y in self.languages.items()]))))
            return

        self.write_server(server)


    async def clock(self, message, stripped, server):
        if server is None:
            return

        t = datetime.now(pytz.timezone(server.timezone))

        if stripped == '12':
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['clock']['time'].format(t.strftime('%I:%M:%S %p'))))

        else:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['clock']['time'].format(t.strftime('%H:%M:%S'))))


    async def remind(self, message, stripped, server):
        if server is None:
            return

        args = stripped.split(' ')

        if len(args) < 2:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['no_argument'].format(prefix=server.prefix)))
            return

        scope = message.channel.id
        pref = '#'

        if args[0].startswith('<'): # if a scope is provided

            scope, pref = self.parse_mention(message, args[0], server)
            if scope is None:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_tag']))
                return

            args.pop(0)

        try:
            while args[0] == '':
                args.pop(0)

            msg_time = self.format_time(args[0], server)
        except ValueError:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_time']))
            return

        if msg_time is None:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_time']))
            return

        args.pop(0)

        msg_text = ' '.join(args)

        if self.count_reminders(scope) > 5 and not self.get_patrons(message.author.id):
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_count'].format(prefix=server.prefix)))
            return

        if self.length_check(message, msg_text) is not True:
            if self.length_check(message, msg_text) == '150':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_chars'].format(len(msg_text), prefix=server.prefix)))

            elif self.length_check(message, msg_text) == '2000':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_chars_2000']))

            return

        if pref == '#':
            if not self.perm_check(message, server):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['no_perms'].format(prefix=server.prefix)))
                return

        reminder = Reminder(time=msg_time, channel=scope, message=msg_text)

        command = '''INSERT INTO reminders (interval, time, channel, message)
        VALUES (?, ?, ?, ?)'''

        self.cursor.execute(command, (reminder.interval, reminder.time, reminder.channel, reminder.message))

        await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['success'].format(pref, scope, round(msg_time - time.time()))))
        print('Registered a new reminder for {}'.format(message.guild.name))


    async def interval(self, message, stripped, server):
        if server is None:
            return

        if not self.get_patrons(message.author.id, level=1):
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['interval']['donor'].format(prefix=server.prefix)))
            return

        args = message.content.split(' ')
        args.pop(0) # remove the command item

        if len(args) < 3:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['interval']['no_argument'].format(prefix=server.prefix)))
            return

        scope = message.channel.id
        pref = '#'

        if args[0].startswith('<'): # if a scope is provided

            scope, pref = self.parse_mention(message, args[0], server)
            if scope is None:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_tag']))
                return

            args.pop(0)

        while args[0] == '':
            args.pop(0)

        msg_time = self.format_time(args[0], server)

        if msg_time == None:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_time']))
            return

        args.pop(0)

        while args[0] == '':
            args.pop(0)

        msg_interval = self.format_time(args[0], message.guild.id)

        if msg_interval == None:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['interval']['invalid_interval']))
            return

        msg_interval -= time.time()
        msg_interval = round(msg_interval)

        if msg_interval < 8:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['interval']['8_seconds']))
            return

        args.pop(0)

        msg_text = ' '.join(args)

        if self.length_check(message, msg_text) is not True:
            if self.length_check(message, msg_text) == '150':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_chars'].format(len(msg_text))))

            elif self.length_check(message, msg_text) == '2000':
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['invalid_chars_2000']))

            return

        if pref == '#':
            if not self.perm_check(message, server):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['no_perms']))
                return


        reminder = Reminder(time=msg_time, interval=msg_interval, channel=scope, message=msg_text)

        command = '''INSERT INTO reminders (interval, time, channel, message)
        VALUES (?, ?, ?, ?)'''

        self.cursor.execute(command, (reminder.interval, reminder.time, reminder.channel, reminder.message))

        await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['interval']['success'].format(pref, scope, round(msg_time - time.time()))))
        print('Registered a new interval for {}'.format(message.guild.name))


    async def autoclear(self, message, stripped, server):
        if server is None:
            return

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['admin_required']))
            return

        seconds = 10

        for item in stripped.split(' '): # determin a seconds argument
            try:
                seconds = float(item)
                break
            except ValueError:
                continue

        if len(message.channel_mentions) == 0:
            if message.channel.id in server.autoclears.keys():
                del server.autoclears[message.channel.id]
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['autoclear']['disable'].format(message.channel.mention)))
            else:
                server.autoclears[message.channel.id] = seconds
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['autoclear']['enable'].format(seconds, message.channel.mention)))

        else:
            disable_all = True
            for i in message.channel_mentions:
                if i.id not in server.autoclears.keys():
                    disable_all = False
                server.autoclears[i.id] = seconds


            if disable_all:
                for i in message.channel_mentions:
                    del server.autoclears[i.id]

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['autoclear']['disable'].format(', '.join(map(lambda x: x.name, message.channel_mentions)))))
            else:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['autoclear']['enable'].format(seconds)))

        self.write_server(server)


    async def blacklist(self, message, stripped, server):
        if server is None:
            return

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['admin_required']))
            return

        if len(message.channel_mentions) > 0:
            disengage_all = True

            for mention in message.channel_mentions:
                if mention.id not in server.blacklist:
                    disengage_all = False

            if disengage_all:
                for mention in message.channel_mentions:
                    server.blacklist.remove(mention.id)

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['blacklist']['removed_from']))

            else:
                for mention in message.channel_mentions:
                    if mention.id not in server.blacklist:
                        server.blacklist.append(mention.id)

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['blacklist']['added_from']))

        else:
            if message.channel.id in server.blacklist:
                server.blacklist.remove(message.channel.id)
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['blacklist']['removed']))

            else:
                server.blacklist.append(message.channel.id)
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['blacklist']['added']))

        self.write_server(server)


    async def clear(self, message, stripped, server):
        if server is None:
            return

        if not message.author.guild_permissions.manage_messages:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['admin_required']))
            return

        if len(message.mentions) == 0:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['clear']['no_argument']))
            return

        delete_list = []

        async for m in message.channel.history(limit=1000):
            if time.time() - m.created_at.timestamp() >= 1209600 or len(delete_list) > 99:
                break

            if m.author in message.mentions:
                delete_list.append(m)

        await message.channel.delete_messages(delete_list)


    async def restrict(self, message, stripped, server):
        if server is None:
            return

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['admin_required']))

        else:
            disengage_all = True
            args = False

            for role in message.role_mentions:
                args = True
                if role.id not in server.restrictions:
                    disengage_all = False
                server.restrictions.append(role.id)

            if disengage_all and args:
                for role in message.role_mentions:
                    server.restrictions.remove(role.id)
                    server.restrictions.remove(role.id)

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['restrict']['disabled']))

            elif args:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['restrict']['enabled']))

            else:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['restrict']['allowed'].format(' '.join(['<@&' + str(i) + '>' for i in server.restrictions]))))

        self.write_server(server)


    async def tag(self, message, stripped, server):
        if server is None:
            return

        not_done = True

        splits = stripped.split(' ')

        if stripped == '':
            if len(server.tags) == 0:
                await message.channel.send(embed=discord.Embed(title='No Tags!', description=self.get_strings(server)['tags']['help'].format(prefix=server.prefix)))
            else:
                await message.channel.send(embed=discord.Embed(title='Tags', description='\n'.join(server.tags.keys())))

            not_done = False

        elif len(splits) > 1:
            content = ' '.join(splits[1:])

            if splits[0] in ['add', 'new']:
                if len(server.tags) > 5 and not self.get_patrons(message.author.id):
                    await message.channel.send(self.get_strings(server)['tags']['invalid_count'].format(prefix=server.prefix))
                    return

                elif len(content) > 80 and not self.get_patrons(message.author.id):
                    await message.channel.send(self.get_strings(server)['tags']['invalid_chars'])
                    return

                content = content.split(':')
                if len(content) == 1:
                    await message.channel.send(self.get_strings(server)['tags']['colon'])

                else:
                    if content[0].startswith(('add', 'new', 'remove', 'del')):
                        await message.channel.send(self.get_strings(server)['tags']['illegal'])
                        return

                    server.tags[content[0]] = ':'.join(content[1:]).strip()
                    await message.channel.send(self.get_strings(server)['tags']['added'].format(content[0]))

                not_done = False

            elif splits[0] in ['remove', 'del']:
                name = ' '.join(splits[1:])
                if name not in server.tags.keys():
                    await message.channel.send(self.get_strings(server)['tags']['unfound'])
                    return

                del server.tags[name]
                await message.channel.send(self.get_strings(server)['tags']['deleted'].format(name))

                not_done = False

        if not_done:
            name = ' '.join(splits).strip()

            if name not in server.tags.keys():
                await message.channel.send(self.get_strings(server)['tags']['help'].format(prefix=server.prefix))
                return

            await message.channel.send(server.tags[name])

        self.write_server(server)


    async def todo(self, message, stripped, server):
        if 'todos' in message.content.split(' ')[0]:
            if server is None:
                await message.channel.send(self.get_strings(server)['todo']['server_only'].format(prefix='$'))
                return

            location = message.guild.id
            name = message.guild.name
            command = 'todos'
        else:
            location = message.author.id
            name = message.author.name
            command = 'todo'


        if location not in self.todos.keys():
            self.todos[location] = []

        splits = stripped.split(' ')

        todo = self.todos[location]

        if len(splits) == 1 and splits[0] == '':
            msg = ['\n{}: {}'.format(i+1, todo[i]) for i in range(len(todo))]
            if len(msg) == 0:
                msg.append(self.get_strings(server)['todo']['add'].format(prefix='$' if server is None else server.prefix, command=command))
            await message.channel.send(embed=discord.Embed(title='{}\'s TODO'.format(name), description=''.join(msg)))

        elif len(splits) >= 2:
            if splits[0] in ['add', 'a']:
                a = ' '.join(splits[1:])
                if len(a) > 80:
                    await message.channel.send(self.get_strings(server)['todo']['too_long'])
                    return

                elif len(''.join(todo)) > 800:
                    await message.channel.send(self.get_strings(server)['todo']['too_long2'])
                    return

                self.todos[location].append(a)
                await message.channel.send(self.get_strings(server)['todo']['added'].format(name=a))

            elif splits[0] in ['remove', 'r']:
                try:
                    a = self.todos[location].pop(int(splits[1])-1)
                    await message.channel.send(self.get_strings(server)['todo']['removed'].format(a))

                except ValueError:
                    await message.channel.send(self.get_strings(server)['todo']['error_value'].format(prefix='$' if server is None else server.prefix, command=command))
                except IndexError:
                    await message.channel.send(self.get_strings(server)['todo']['error_index'])


            else:
                await message.channel.send(self.get_strings(server)['todo']['help'].format(prefix='$' if server is None else server.prefix, command=command))

        else:
            if stripped in ['remove*', 'r*', 'clear', 'clr']:
                self.todos[location] = []
                await message.channel.send(self.get_strings(server)['todo']['cleared'])

            else:
                await message.channel.send(self.get_strings(server)['todo']['help'].format(prefix='$' if server is None else server.prefix, command=command))

        with open('DATA/todos.json', 'w') as f:
            json.dump(self.todos, f)


    async def delete(self, message, stripped, server):
        if server is not None:
            if not self.perm_check(message, server):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server)['remind']['no_perms'].format(prefix=server.prefix)))
                return

            li = [ch.id for ch in message.guild.channels] ## get all channels and their ids in the current server
        else:
            li = [message.author.id]

        await message.channel.send(self.get_strings(server)['del']['listing'])

        n = 1
        remli = []

        command = '''SELECT *
        FROM reminders
        WHERE channel IN ({})
        '''.format(', '.join([str(x) for x in li]))

        self.cursor.execute(command)

        s = ''
        for r in self.cursor.fetchall():
            rem = Reminder(dictv=dict(r))
            if rem.channel in li:
                remli.append(rem)
                s_temp = '**' + str(n) + '**: \'' + rem.message + '\' (' + datetime.fromtimestamp(rem.time, pytz.timezone('UTC' if server is None else server.timezone)).strftime('%Y-%m-%d %H:%M:%S') + ') ' + ('' if self.get_channel(rem.channel) is None else self.get_channel(rem.channel).mention) + '\n'
                if len(s) + len(s_temp) > 2000:
                    await message.channel.send(s)
                    s = s_temp
                else:
                    s += s_temp

                n += 1

        if s:
            await message.channel.send(s)

        await message.channel.send(self.get_strings(server)['del']['listed'])

        num = await client.wait_for('message', check=lambda m: m.author == message.author and m.channel == message.channel)
        nums = [n.strip() for n in num.content.split(',')]

        dels = 0
        for i in nums:
            try:
                i = int(i) - 1
                if i < 0:
                    continue

                if remli[i].interval is None:
                    self.cursor.execute('DELETE FROM reminders WHERE time = ? and channel = ? and message = ?', (remli[i].time, remli[i].channel, remli[i].message))
                else:
                    self.cursor.execute('DELETE FROM reminders WHERE interval = ? and channel = ? and message = ?', (remli[i].interval, remli[i].channel, remli[i].message))

                print('Deleted reminder')
                dels += 1

            except ValueError:
                continue
            except IndexError:
                continue

        await message.channel.send(self.get_strings(server)['del']['count'].format(dels))


    async def check_reminders(self):
        await self.wait_until_ready()

        self.times['start'] = time.time()
        while not self.is_closed():
            self.times['last_loop'] = time.time()
            self.times['loops'] += 1

            command = '''
            SELECT *
            FROM reminders
            WHERE time < ?;
            '''
            self.cursor.execute(command, (time.time(),))

            for r in self.cursor.fetchall():
                print('Looping for reminder(s)...')
                reminder = Reminder(dictv=dict(r))

                command = '''DELETE
                FROM reminders
                WHERE time = ? AND channel = ? AND message = ?;
                '''
                self.cursor.execute(command, (reminder.time, reminder.channel, reminder.message))

                if reminder.interval is not None and reminder.interval < 8:
                    continue

                users = self.get_all_members()
                channels = self.get_all_channels()

                msg_points = chain(users, channels)

                recipient = discord.utils.get(msg_points, id=reminder.channel)

                if recipient == None:
                    print('{}: Failed to locate channel'.format(datetime.utcnow().strftime('%H:%M:%S')))
                    continue

                try:
                    if reminder.interval == None:
                        await recipient.send(reminder.message)
                        print('{}: Administered reminder to {}'.format(datetime.utcnow().strftime('%H:%M:%S'), recipient.name))

                    else:
                        server_members = recipient.guild.members

                        if any([self.get_patrons(m.id, level=1) for m in server_members]):
                            if reminder.message.startswith('-del_on_send'):
                                try:
                                    await recipient.purge(check=lambda m: m.content == reminder.message[len('-del_on_send'):].strip() and time.time() - m.created_at.timestamp() < 1209600 and m.author == client.user)
                                except Exception as e:
                                    print(e)

                                await recipient.send(reminder.message[len('-del_on_send'):])

                            elif reminder.message.startswith('-del_after_'):

                                chars = ''

                                for char in reminder.message[len('-del_after_'):]:
                                    if char in '0123456789':
                                        chars += char
                                    else:
                                        break

                                wait_time = int(chars)

                                message = await recipient.send(reminder.message[len('-del_after_{}'.format(chars)):])

                                self.process_deletes[message.id] = {'time' : time.time() + wait_time, 'channel' : message.channel.id}

                            else:
                                await recipient.send(reminder.message)

                            print('{}: Administered interval to {} (Reset for {} seconds)'.format(datetime.utcnow().strftime('%H:%M:%S'), recipient.name, reminder.interval))
                        else:
                            await recipient.send(self.get_strings(self.get_server(recipient.guild))['interval']['removed'])
                            continue

                        while reminder.time <= time.time():
                            reminder.time += reminder.interval ## change the time for the next interval

                        command = '''INSERT INTO reminders (interval, time, channel, message)
                        VALUES (?, ?, ?, ?)'''

                        self.cursor.execute(command, (reminder.interval, reminder.time, reminder.channel, reminder.message))

                except Exception as e:
                    print(e)

            try:
                for message, info in self.process_deletes.copy().items():
                    if info['time'] <= time.time():
                        del self.process_deletes[message]

                        message = await self.get_channel(info['channel']).get_message(message)

                        if message is None or message.pinned:
                            pass
                        else:
                            print('{}: Attempting to auto-delete a message...'.format(datetime.utcnow().strftime('%H:%M:%S')))
                            try:
                                await message.delete()
                            except Exception as e:
                                print(e)

            except Exception as e:
                print('Error in deletion loop: {}'.format(e))

            with open('DATA/process_deletes.mp', 'wb') as f:
                msgpack.dump(self.process_deletes, f)

            self.connection.commit()
            await asyncio.sleep(2.5)

client = BotClient()

try:
    client.loop.create_task(client.check_reminders())

    client.run(client.config.get('DEFAULT', 'token'), max_messages=400)
except Exception as e:
    print('Error detected. Restarting in 15 seconds.')
    print(sys.exc_info()[0])
    time.sleep(15)

    os.execl(sys.executable, sys.executable, *sys.argv)
