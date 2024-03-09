import time
import io
import discord

from discord.ui import Button, View, InputText, Modal

from PIL import Image

import imagegen.imagegen as imagegen

def splitlb(lblist, chunksize):
    res = []
    while len(lblist) > chunksize:
        res.append(lblist[:chunksize])
        lblist = lblist[chunksize:]
    res.append(lblist)
    return res

class InputForm(Modal):
    def __init__(self, lblist):
        super().__init__(title="Choose the player")
        self.add_item(InputText(label="Place", placeholder="number", required=True, style=discord.InputTextStyle.short))
        self.lblist = lblist
        self.plid = None
    async def callback(self, interaction):
        try:
            val = int(self.children[0].value)
        except:
            await interaction.response.send_message("Provided input is not a valid number", ephemeral=True)
            return
        for i in self.lblist:
            if i["place"] == val:
                self.plid = i["plid"]
                await interaction.response.defer()
                return
        if self.plid == None:
            await interaction.response.send_message(f"Player with a place of {val} was not found on the list", ephemeral=True)

class GotoInput(Modal):
    def __init__(self):
        super().__init__(title="Skip to place")
        self.add_item(InputText(label="Place", placeholder="number", required=True, style=discord.InputTextStyle.short))
        self.val = None
    async def callback(self, interaction):
        try:
            val = int(self.children[0].value)
            self.val = val
            await interaction.response.defer()
        except:
            await interaction.response.send_message("Provided input is not a valid number", ephemeral=True)
        return

class SearchInput(Modal):
    def __init__(self):
        super().__init__(title="Search for a player")
        self.add_item(InputText(label="Playername", placeholder="playername", required=True, style=discord.InputTextStyle.short))
        self.val = None
    async def callback(self, interaction):
        val = self.children[0].value.lower()
        self.val = val
        await interaction.response.defer()

class LbViewCommon(View):
    def __init__(self, ctx, lblist, lbsize, mode, seasonN, chunksize):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.lblist = lblist
        self.plid = None
        self.lbsize = lbsize
        self.searchwarning = False
        self.mode = mode
        self.seasonN = seasonN
        self.chunksize = chunksize
        self.lbsplit = splitlb(lblist, chunksize)
        self.currentIndex = 0
        self.imagecahe = {}
    async def updateImage(self, imageIndex):
        for child in self.children:
            child.disabled = True
        await self.ctx.interaction.edit_original_response(view=self)
        if not imageIndex in self.imagecahe:
            if self.mode == "score":
                timg = imagegen.genChooserLB(self.lbsplit[imageIndex], len(self.lbsplit[imageIndex]), self.seasonN)
            else:
                timg = imagegen.genMiniLB(self.lbsplit[imageIndex], self.mode)
                timg.thumbnail((timg.size[0]//3, timg.size[1]//3), Image.Resampling.BICUBIC)
            self.imagecahe[imageIndex] = timg
        im = self.imagecahe[imageIndex]
        with io.BytesIO() as imbytes:
            im.save(imbytes, 'PNG', compress_level=2)
            imbytes.seek(0)
            await self.ctx.interaction.edit_original_response(file=discord.File(fp=imbytes, filename='image.png'))
        for child in self.children:
            if type(child) == discord.ui.Button and child.custom_id == "left" and self.currentIndex==0:
                child.disabled = True
            elif type(child) == discord.ui.Button and child.custom_id == "right" and self.currentIndex==(len(self.lbsplit)-1):
                child.disabled = True
            else:
                child.disabled = False
        await self.ctx.interaction.edit_original_response(view=self)
    async def interaction_check(self, interaction):
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message("You can't do that, as the original command was issued by someone else", ephemeral=True)
        return False
    async def on_timeout(self):
        await self.ctx.interaction.edit_original_response(view=None)

class LbViewCommonScroll(LbViewCommon):
    @discord.ui.button(label=u"", row=0, style=discord.ButtonStyle.primary, emoji="⬆️", disabled=True, custom_id="left")
    async def goUp(self, button, interaction):
        await interaction.response.defer()
        if self.currentIndex > 0:
            self.currentIndex -= 1
        await self.updateImage(self.currentIndex)
    @discord.ui.button(label=u"", row=0, style=discord.ButtonStyle.primary, emoji=u"⬇️", custom_id="right")
    async def goDown(self, button, interaction):
        await interaction.response.defer()
        if self.currentIndex < len(self.lbsplit)-1:
            self.currentIndex += 1
        await self.updateImage(self.currentIndex)
    @discord.ui.button(label="#?", row=0, style=discord.ButtonStyle.primary)
    async def goIndex(self, button, interaction):
        inputmodal = GotoInput()
        await interaction.response.send_modal(inputmodal)
        await inputmodal.wait()
        if inputmodal.val != None:
            wantedindex = (inputmodal.val-1)//self.chunksize
            if wantedindex < 0 or wantedindex >= len(self.lbsplit):
                await interaction.followup.send("Invalid index", ephemeral=True)
                return
            self.currentIndex = wantedindex
            await self.updateImage(self.currentIndex)
    @discord.ui.button(label=u"🔍", row=0, style=discord.ButtonStyle.primary)
    async def search(self, button, interaction):
        inputmodal = SearchInput()
        await interaction.response.send_modal(inputmodal)
        await inputmodal.wait()
        if inputmodal.val != None:
            cc = 0
            for i in self.lblist:
                if i["body"]["displayName"].lower() == inputmodal.val:
                    cc += 1
            if cc > 1 and not self.searchwarning:
                self.searchwarning = True
                await interaction.followup.send("Multiple players have the same name, the search will find the next one (after the current page) looping to the beginning when no more are left", ephemeral=True)
            for i in range((self.currentIndex+1)*self.chunksize, len(self.lblist)):
                if self.lblist[i]["body"]["displayName"].lower() == inputmodal.val:
                    self.currentIndex = i//8
                    await self.updateImage(self.currentIndex)
                    return
            for i in range(0, len(self.lblist)):
                if self.lblist[i]["body"]["displayName"].lower() == inputmodal.val:
                    self.currentIndex = i//8
                    await self.updateImage(self.currentIndex)
                    return
            await interaction.followup.send("Player not found", ephemeral=True)

class PlayerChooserView(LbViewCommon):
    async def init(self):
        await self.updateImage(0)
        await self.ctx.interaction.edit_original_response(content="Input the place of the player you want to choose, possible values are shown on the image.")
    @discord.ui.button(label="Choose", row=1, style=discord.ButtonStyle.primary)
    async def letChoose(self, button, interaction):
        inputmodal = InputForm(self.lblist)
        await interaction.response.send_modal(inputmodal)
        await inputmodal.wait()
        if inputmodal.plid != None:
            self.plid = inputmodal.plid
            await interaction.edit_original_response(view=None)
            self.stop()

class PlayerChooserViewScroll(LbViewCommonScroll):
    async def init(self):
        await self.updateImage(0)
        await self.ctx.interaction.edit_original_response(content="Input the place of the player you want to choose, possible values are shown on the image.")
    @discord.ui.button(label="Choose", row=1, style=discord.ButtonStyle.primary)
    async def letChoose(self, button, interaction):
        inputmodal = InputForm(self.lblist)
        await interaction.response.send_modal(inputmodal)
        await inputmodal.wait()
        if inputmodal.plid != None:
            self.plid = inputmodal.plid
            await interaction.edit_original_response(view=None)
            self.stop()

class LbView(LbViewCommonScroll):
    async def init(self):
        await self.updateImage(0)
        await self.ctx.interaction.edit_original_response(content=f"{self.mode} leaderboard ({self.mingames} min games) for season {self.seasonN} (with {len(self.lblist)} players)")

