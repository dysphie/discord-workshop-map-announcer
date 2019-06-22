import discord
import aiohttp
import os
import asyncio
import yaml
import re
from bs4 import BeautifulSoup

WORKSHOP_HOME = "https://steamcommunity.com/workshop/browse/?appid=224260"
WORKSHOP_FILE = "https://steamcommunity.com/sharedfiles/filedetails/?id="

ENV_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
if not ENV_BOT_TOKEN:
    raise Exception('You must set the DISCORD_BOT_TOKEN environment variable')


with open("config.yaml", 'r') as yml_file:
    cfg = yaml.safe_load(yml_file)


async def fetch_page(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                return BeautifulSoup(text, 'html.parser')


async def fetch_addon_list():
    index = await fetch_page(WORKSHOP_HOME + cfg['workshop_filter'])
    addon_list = []
    for entry in index.find_all('a', {'data-publishedfileid': True}):
        addon_list.append(int(entry['data-publishedfileid']))
    return addon_list


async def print_announcement(item):
    char_limit = cfg.['embed_description_limit']
    embed = discord.Embed(title=item.title, description=item.description, color=0x417B9C, url=item.url)
    embed.set_author(name="New Workshop item")
    embed.add_field(name="Category", value=item.category, inline=True)
    embed.add_field(name="Authors", value=item.authors, inline=True)

    if item.image:
        embed.set_thumbnail(url=item.image)

    await bot.workshop_channel.send(embed=embed)


def exception_callback(task):
    if task.exception():
        task.print_stack()


class NMRiH_WorkshopItem(object):

    @classmethod
    async def build(self, file_id):
        self = NMRiH_WorkshopItem()
        self._url = f'{WORKSHOP_FILE}{file_id}'
        self._page = await fetch_page(self.url)
        return self

    @property
    def description(self):
        cap = cfg['embed_description_limit']
        content = self.page.find('div', {'class': 'workshopItemDescription'}).text
        if content:
            content = discord.utils.escape_markdown(content)
            return content[:cap] + (content[cap:] and '..')

    @property
    def image(self):
        image = self.page.find('img', {'class': 'workshopItemPreviewImageMain'})
        return image['src'] if image else None

    @property
    def category(self):
        div = self.page.find('div', {'class': 'workshopTags'})
        if div:
            c = div.find('a')
            if c.text:
                name = discord.utils.escape_markdown(c.text)
                href = c['href']
                return f'[{name}]({href})'

    @property
    def title(self):
        content = self.page.find('div', {'class': 'workshopItemTitle'}).text
        if content:
            return discord.utils.escape_markdown(content)

    @property
    def authors(self):
        creators_block = self.page.find('div', {'class': 'creatorsBlock'})
        user_blocks = creators_block.find_all('div', {'class': re.compile('^friendBlock persona.*')})
        authors = {}
        for block in user_blocks:
            user_url = block.find('a')['href']
            user_name = block.find('div', {'class': 'friendBlockContent'}).contents[0].strip()
            authors[user_name] = user_url

        return ", ".join(f'[{discord.utils.escape_markdown(k)}]({v})' for k, v in authors.items())

    @property
    def page(self):
        return self._page

    @property
    def url(self):
        return self._url


class DiscordBot(discord.Client):

    def __init__(self):
        super(DiscordBot, self).__init__()
        self._cache = []
        self.updater = self.loop.create_task(self.check_for_updates())
        self.updater.add_done_callback(exception_callback)

    async def on_ready(self):
        print('Connected as {0.name}\n (ID: {0.id})'.format(self.user))

        for guild in bot.guilds:
            for channel in guild.channels:
                if channel.id == cfg['announcement_channel_id']:
                    self._workshop_channel = channel
                    break

    async def check_for_updates(self):

        await self.wait_until_ready()
        while not self.is_closed():

            new = await fetch_addon_list()
            if self.cache:
                for i in new:
                    if i in self.cache:
                        break

                    item = NMRiH_WorkshopItem.build(i)
                    await print_announcement(item)

            # Repeat task periodically
            await asyncio.sleep(cfg.['workshop_refresh_interval'])

    @property
    def workshop_channel(self):
        return self._workshop_channel

    @property
    def cache(self):
        return self._cache


if __name__ == "__main__":
    bot = DiscordBot()
    bot.run(ENV_BOT_TOKEN)
