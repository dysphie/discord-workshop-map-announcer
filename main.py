'''
TODO: 
- Safer yaml loading
- Few sanity checks against null descriptions, etc.
'''

import asyncio
import discord
import requests
import re
import os
import yaml
from bs4 import BeautifulSoup

ENV_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
if not ENV_BOT_TOKEN:
    raise Exception('You must set the DISCORD_BOT_TOKEN environment variable')


bot = discord.Client()

WORKSHOP_HOME = "https://steamcommunity.com/workshop/browse/?appid=224260"
WORKSHOP_FILE = "https://steamcommunity.com/sharedfiles/filedetails/?id="

with open("config.yaml", 'r') as yml_file:
    cfg = yaml.load(yml_file)


def scrape_url(url):
    response = requests.get(url)
    return BeautifulSoup(response.content, "html.parser")


def fetch_addon_list():

    index = scrape_url(WORKSHOP_HOME + cfg.get('workshop_filter'))

    addon_list = []
    for entry in index.find_all('a', {'data-publishedfileid': True}):
        addon_list.append(int(entry['data-publishedfileid']))

    return addon_list


class WorkshopItem(object):

    def __init__(self, file_id):
        super(WorkshopItem, self).__init__()
        self._url = f'{WORKSHOP_FILE}{file_id}'
        self._page = scrape_url(self.url)

    @property
    def url(self):
        return self._url

    @property
    def authors(self):
        authors = {}
        creators_block = self.page.find('div', {'class': 'creatorsBlock'})
        user_blocks = creators_block.find_all('div', {'class': re.compile('^friendBlock persona.*')})
        for block in user_blocks:
            user_url = block.find('a')['href']
            user_name = block.find('div', {'class': 'friendBlockContent'}).contents[0].strip()
            authors[user_name] = user_url
        return authors

    def description(self, length):
        body = self.page.find('div', {'class': 'workshopItemDescription'}).text
        body = discord.utils.escape_markdown(body)
        return (body[:length] + '..') if len(body) > length else body

    @property
    def image_url(self):
        img_tag = self.page.find('img', {'class': 'workshopItemPreviewImageMain'})
        return img_tag['src'] if img_tag else None

    @property
    def tags(self):
        details_block = self.page.find('div', {'class': 'rightDetailsBlock'})
        return [tag.text for tag in details_block.find_all('a')]

    @property
    def page(self):
        return self._page

    @property
    def title(self):
        content = self.page.find('div', {'class': 'workshopItemTitle'}).text
        return discord.utils.escape_markdown(content)

    @property
    def category_string(self):
        c = discord.utils.escape_markdown(self.tags[0])
        return f'[{c}]({WORKSHOP_HOME}&requiredtags%5B%5D={requests.utils.requote_uri(c)})'

    @property
    def authors_string(self):
        return ", ".join(f'[{discord.utils.escape_markdown(k)}]({v})' for k, v in self.authors.items())

    @property
    def usertags_string(self):
        if self.has_usertags():
            return ", ".join(discord.utils.escape_markdown(tag) for tag in self.tags[1:])
        return "None"

    def has_usertags(self):
        return bool(self.tags[1:])


class DiscordBot(discord.Client):

    def __init__(self):
        super(DiscordBot, self).__init__()
        self._cache = []

    async def on_ready(self):
        print('Connected as {0.name}\n (ID: {0.id})'.format(self.user))
        self.bg_task = self.loop.create_task(self.check_for_updates())

        for guild in bot.guilds:
            for channel in guild.channels:
                if channel.id == cfg.get('announcement_channel_id'):
                    self._workshop_channel = channel
                    break

    async def check_for_updates(self):

        await self.wait_until_ready()
        while not self.is_closed():

            #print('[Debug] Fetching addon list..')

            new = fetch_addon_list()

            if self.cache:
                for i in list(set(new) - set(self.cache)):
                    item = WorkshopItem(i)
                    await print_announcement(item)
                    await asyncio.sleep(1)

            self._cache = new

            #print('[Debug] Up to date. Sleeping.')

            # Repeat task periodically
            await asyncio.sleep(cfg.get('workshop_refresh_interval'))

    @property
    def workshop_channel(self):
        return self._workshop_channel

    @property
    def cache(self):
        return self._cache


async def print_announcement(item):

    char_limit = cfg.get('embed_description_limit')
    embed = discord.Embed(title=item.title, description=item.description(char_limit), color=0x417B9C, url=item.url)
    embed.set_author(name="New Workshop item")
    embed.add_field(name="Category", value=item.category_string, inline=True)
    embed.add_field(name="Authors", value=item.authors_string, inline=True)
    # if item.has_usertags():
    #    embed.add_field(name="Tags", value=item.usertags_string, inline=False)
    if item.image_url:
        embed.set_thumbnail(url=item.image_url)
    print(bot.workshop_channel)
    await bot.workshop_channel.send(embed=embed)


bot = DiscordBot()
bot.run(ENV_BOT_TOKEN)
