import asyncio
import os
from io import BytesIO
from typing import Literal

import discord
from discord import app_commands, Interaction, Attachment
from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import select, distinct, and_

import utils
from app import DamiBot
from db import SessionContext
from db.model.DLC import DLC
from db.model.Music import Music
from db.model.SubLevel import SubLevel
from utils import MusicManager

class Admin(commands.Cog):
    def __init__(self, bot):
        print(f'{type(self).__name__}가 로드되었습니다.')
        self.bot: DamiBot = bot

    @commands.command()
    async def 싱크(self, ctx: Context):
        if not utils.is_developer(ctx.author):
            return

        for guild in self.bot.guilds:
            self.bot.tree.copy_global_to(guild=guild)
            await self.bot.tree.sync(guild=guild)
        msg = await ctx.reply(f'명령어 동기화가 완료되었습니다.')
        await msg.delete(delay=10)
        await ctx.message.delete(delay=10)

    @commands.command()
    async def 언싱크(self, ctx: Context):
        if not utils.is_developer(ctx.author):
            return
        for guild in self.bot.guilds:
            self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)
        msg = await ctx.reply(f'명령어 동기화를 해제합니다.')
        await msg.delete(delay=10)
        await ctx.message.delete(delay=10)

    @app_commands.command(description='DJMAX RESPECT V의 수록곡을 추가합니다.')
    @app_commands.describe(title="곡명", artist="아티스트", bpm="BPM", dlc="DLC", nickname="별명", thumbnail="썸네일")
    @app_commands.autocomplete(dlc=utils.autocomplete_dlc)
    async def 곡추가(self, action: Interaction[DamiBot], title: str,  dlc: str, artist: str=None, bpm: str=None,
                    nickname: str=None, thumbnail: Attachment=None):
        if not utils.is_developer(action.user):
            return

        title = title.strip()
        dlc = dlc.strip()
        if not title or not dlc:
            await action.response.send_message(f"❌ 곡을 추가하려면, 곡명과 DLC를 입력해야 합니다.")
            return

        image_bytes = None
        image_file = None
        if thumbnail:
            image_bytes = await thumbnail.read()
            image_bytes = utils.convert_thumbnail(image_bytes)

            image_file = discord.File(BytesIO(image_bytes), filename="thumbnail.jpg")


        embed = None
        with SessionContext() as session:
            prev_music = session.query(Music).filter(and_(Music.music_name == title, Music.music_dlc == dlc)).first()

            if prev_music:
                if bpm: prev_music.music_bpm = bpm
                if artist: prev_music.music_artist = artist
                if nickname: prev_music.music_nickname = nickname
                if image_bytes: prev_music.music_thumbnail = image_bytes
                
                embed = discord.Embed(title=f"⚡ 곡 업데이트", description=f"", color=0x8d76bc)
                embed.set_footer(text=f"DJMAX RESPECT V｜기록 관리봇 담이", icon_url=self.bot.user.display_avatar)
                embed.add_field(name="Title", value=f"{prev_music.music_name}")
                embed.add_field(name="Artist", value=f"{prev_music.music_artist}")
                embed.add_field(name="DLC", value=f"{prev_music.music_dlc}")
                embed.add_field(name="BPM", value=f"{prev_music.music_bpm}")

            else:
                new_music = Music(music_name=title, music_artist=artist, music_bpm=bpm, music_dlc=dlc,
                                  music_nickname=nickname, music_thumbnail=image_bytes)
                session.add(new_music)

                embed = discord.Embed(title=f"⚡ 곡 추가", description=f"", color=0x8d76bc)
                embed.set_footer(text=f"DJMAX RESPECT V｜기록 관리봇 담이", icon_url=self.bot.user.display_avatar)
                embed.add_field(name="Title", value=f"{new_music.music_name}")
                embed.add_field(name="Artist", value=f"{new_music.music_artist}")
                embed.add_field(name="DLC", value=f"{new_music.music_dlc}")
                embed.add_field(name="BPM", value=f"{new_music.music_bpm}")

            session.commit()

        if image_file:
            embed.set_thumbnail(url="attachment://thumbnail.jpg")
        utils.reset_singleton(MusicManager)

        if image_file:
            await action.response.send_message(embed=embed, file=image_file)
        else:
            await action.response.send_message(embed=embed)


    @app_commands.command(description='DJMAX RESPECT V의 수록곡을 삭제합니다.')
    @app_commands.describe(title="곡명", dlc="DLC")
    @app_commands.autocomplete(title=utils.autocomplete_title, dlc=utils.autocomplete_dlc)
    async def 곡삭제(self, action: Interaction[DamiBot], title: str,  dlc: str):
        if not utils.is_developer(action.user):
            return

        with SessionContext() as session:
            deleted_count = session.query(Music).filter(and_(Music.music_name == title, Music.music_dlc == dlc)).delete(synchronize_session=False)
            if deleted_count > 0:
                await action.response.send_message(f"✅ {title} ({dlc}) 곡이 삭제되었습니다.")
            else:
                await action.response.send_message(f"❌ {title} ({dlc}) 곡은 존재하지 않습니다.")

            session.commit()

    @app_commands.command(description='DJMAX RESPECT V의 수록곡의 세부난이도를 추가합니다.')
    @app_commands.describe(title="곡명", dlc="DLC", sub_level="세부난이도 txt로 각 버튼별 난이도를 tab구분으로 작성")
    @app_commands.autocomplete(title=utils.autocomplete_title, dlc=utils.autocomplete_dlc)
    async def 세부난이도추가(self, action: Interaction[DamiBot], title: str, dlc: str, sub_level: Attachment):
        if not utils.is_developer(action.user):
            return

        if sub_level and "text/plain" not in sub_level.content_type:
            await action.response.send_message(f"❌ 세부난이도는 txt 파일로 업로드해야 합니다.\n> 버튼 별 난이도를 tab으로 구분하여 작성")
            return

        raw_bytes = await sub_level.read()
        try:
            content = raw_bytes.decode("utf-8")  # 또는 필요한 인코딩
            sub_level_list = content.split("\t")
        except UnicodeDecodeError:
            await action.response.send_message(f"❌ UTF-8 인코딩된 텍스트 파일만 지원됩니다.")
            return

        with SessionContext() as session:
            music = session.query(Music).filter(and_(Music.music_name == title, Music.music_dlc == dlc)).first()

            print(music)

            update = 0
            insert = 0

            for idx, sub_lv in enumerate(sub_level_list):
                button = {0:4, 1:5, 2:6, 3:8}[(idx // 4)]
                level = ((idx % 4)+1)*10

                sub_detail = session.query(SubLevel).filter(and_(SubLevel.music_id == music.id, SubLevel.music_button == button, SubLevel.music_level == level)).first()
                if sub_detail:
                    sub_detail.music_sub_level = sub_lv
                    update += 1
                else:
                    sub = SubLevel(music_id=music.id, music_button=button, music_level=level, music_sub_level=sub_lv)
                    session.add(sub)
                    insert += 1

            session.commit()
            await action.response.send_message(f"✅ {music.music_name} ({music.music_dlc})에 대한 세부 난이도가 추가되었습니다.\n> 추가 ({insert}) / 수정 ({update})")


async def setup(bot):
    await bot.add_cog(Admin(bot))
