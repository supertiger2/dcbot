import time
import io
import discord

from discord.ui import Button, View, InputText, Modal

from PIL import Image

import imagegen.imagegen as imagegen

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

class PlayerChoiceView(View):
    def __init__(self, ctx, lblist):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.lblist = lblist
        self.plid = None
    @discord.ui.button(label="Choose", style=discord.ButtonStyle.primary)
    async def letChoose(self, button, interaction):
        #await interaction.response.edit_message(content="abc", view=self)
        inputmodal = InputForm(self.lblist)
        await interaction.response.send_modal(inputmodal)
        await inputmodal.wait()
        if inputmodal.plid != None:
            self.plid = inputmodal.plid
            await interaction.edit_original_response(view=None)
            self.stop()
    async def interaction_check(self, interaction):
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message("You can't do that, as the original command was issued by someone wlse", ephemeral=True)
        return False

