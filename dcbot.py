import time
import io
import os
import discord
import pymongo
import datetime
import cProfile, pstats, io, tracemalloc

from dotenv import load_dotenv
from PIL import Image

import imagegen.imagegen as imagegen
from playerspecifier import PlayerChoiceView

if __name__ == "__main__":
    load_dotenv()
    guild = os.getenv("GUILD")
    global cmdguilds
    cmdguilds = []
    if guild != 0:
        cmdguilds.append(guild)

bot = discord.Bot()

def getSeason():
    season = mongoclient["sutil"]["sutil"].find_one({"_id": 0})["seasonid"]
    return season

def getSeasonN():
    seasonN = mongoclient["sutil"]["sutil"].find_one({"_id": 0})["seasonN"]
    return seasonN

async def choosePlayer(ctx, season, playername):
    lb = mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    orgplayername = playername
    playername = playername.lower()
    # add special syntax
    if playername[:2] == '\\t':
        try:
            pos = int(playername[2:])
            if pos > 0:
                pos = pos-1
                if pos < 0 or pos > lbsize:
                    await ctx.followup.send(f"Out of range (leaderboard has {lbsize} players)")
                    return None
            return lb["lb"][pos]["profile"]
        except:
            await ctx.followup.send(f"Bad expression (possibly you included not a number)")
            return None
    lblist = []
    for i in lb["lb"]:
        if i["displayName"].lower() == playername:
            lblist.append(mongoclient["b2"]["players"].find({"plid": i["profile"], "season": season}).sort("date", -1).limit(1)[0])
    if len(lblist) == 0:
        await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do)")
        return None
    if len(lblist) == 1:
        return lblist[0]["plid"]
    im = imagegen.genMiniLB(lblist, lbsize, getSeasonN())
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'PNG')
        imbytes.seek(0)
        view = PlayerChoiceView(ctx, lblist)
        msg = await ctx.followup.send("Input the place of the player you want to choose, possible values are shown on the image.", file=discord.File(fp=imbytes, filename='image.png'), view=view)
        if await view.wait():
            await msg.edit("Timed out!", view=None)
            return None
        return view.plid

async def deltastat(ctx, season, playername, plid, beg, end):
    if (beg > end):
        await ctx.followup.send("Time interval must begin earlier then it ends")
        return False
    if plid == None:
        plid = await choosePlayer(ctx, season, playername)
    if plid == None:
        return False
    lbsize = mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lbsize == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return False
    lbsize = lbsize['lbsize']
    oldstat = mongoclient["b2"]["players"].find_one({"plid": plid, "season": season, "date": {"$lte": datetime.datetime.utcfromtimestamp(beg)}}, sort=[("date", -1)])
    if oldstat == None:
        oldest = mongoclient["b2"]["players"].find_one({"plid": plid, "season": season}, sort=[("date", 1)])
        if oldest == None:
            await ctx.followup.send(f"There are no stats for player {playername}")
            return False
        oldesttime = time.mktime(oldest["date"].timetuple())
        await ctx.followup.send(f"There are no stats this old for this season (<t:{int(beg)}:f>), oldest stats available for player {playername} are from <t:{int(oldesttime)}:f> [<t:{int(oldesttime)}:R>]")
        return False
    newstat = mongoclient["b2"]["players"].find_one({"plid": plid, "season": season, "date": {"$lte": datetime.datetime.utcfromtimestamp(end)}}, sort=[("date", -1)])
    lbsizeold = mongoclient["b2"]["lb"].find_one({"season": season, "date": {"$lte": datetime.datetime.utcfromtimestamp(end)}}, sort=[("date", -1)])
    beg = oldstat["date"].astimezone(datetime.timezone.utc).timestamp()
    end = newstat["date"].astimezone(datetime.timezone.utc).timestamp()
    if lbsizeold == None:
        lbsizeold = mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", 1)])
    lbsizeold = lbsizeold["lbsize"]
    playtime = list(mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "$or": [{"winner": plid}, {"loser": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "playtime": {"$sum": "$body.duration"}}}
    ]))
    if playtime == []:
        playtime = 0
    else:
        playtime = playtime[0]["playtime"]
    # wins get delivered with big delay so we count them from matches
    winsR = list(mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "winner": plid, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "win": {"$sum": 1}}}
    ]))
    if winsR == []:
        winsR = 0
    else:
        winsR = winsR[0]["win"]
    # losses too
    lossesR = list(mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "loser": plid, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "lll": {"$sum": 1}}}
    ]))
    if lossesR == []:
        lossesR = 0
    else:
        lossesR = lossesR[0]["lll"]
    # send some info about latest match too
    try:
        lm = mongoclient["b2"]["matches"].find_one({"season": season, "$or": [{"winner": plid}, {"loser": plid}]}, sort=[("date", -1)])
        if lm["winner"] == plid:
            lmres = "won"
        else:
            lmres = "lost"
        if lm["body"]["playerLeft"]["profileURL"] == plid:
            lmopponent = lm["body"]["playerRight"]["displayName"]
        else:
            lmopponent = lm["body"]["playerLeft"]["displayName"]
        matchstring = f"(newest recorded match was {lmres} against {lmopponent})"
    except:
        matchstring = ""
    # generate image
    im = imagegen.genDeltaStatImage(oldstat, newstat, winsR, lossesR, playtime, lbsizeold, getSeasonN())
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'PNG')
        imbytes.seek(0)
        await ctx.interaction.edit_original_response(content="Stat difference between <t:"+str(int(time.mktime(oldstat["date"].timetuple())))+":f> and <t:"+str(int(time.mktime(newstat["date"].timetuple())))+":f> "+matchstring,
            file=discord.File(fp=imbytes, filename='image.png'))
        return True

async def autocompletePname(ctx: discord.AutocompleteContext):
    possible = list(mongoclient["b2"]["lb"].find_one({}, sort=[("date", -1)])["namelist"])
    matched = []
    for i in possible:
        if ctx.options["playername"].lower() in i.lower() and len(matched) < 25:
            matched.append(i)
    return matched

@bot.slash_command(name="ndaily", description="Show stat difference between now and n days ago (n dosen't need to be integer)", guild_ids=cmdguilds)
async def ndaily(ctx, n: discord.Option(float, "n", required = True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=False)
    season = getSeason()
    plid = None
    if playername == None:
        plid = mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a plyername as an input or link your discord accout to Battles 2 name (/link)")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*24*n
    await deltastat(ctx, season, playername, plid, beg, end)

@bot.slash_command(name="daily", description="Show stat difference between now and one day ago", guild_ids=cmdguilds)
async def daily(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=False)
    season = getSeason()
    plid = None
    if playername == None:
        plid = mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a plyername as an input or link your discord accout to Battles 2 name (/link)")
            return
        plid = plid["b2plid"]
    end = time.time()
    #beg = time.time()
    beg = end - 60*60*24
    await deltastat(ctx, season, playername, plid, beg, end)

@bot.slash_command(name="seasonal", description="Show stat difference between now and one day ago", guild_ids=cmdguilds)
async def seasonal(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=False)
    season = getSeason()
    plid = None
    if playername == None:
        plid = mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a plyername as an input or link your discord accout to Battles 2 name (/link)")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, playername)
    old = mongoclient['b2']['players'].find_one({'plid': plid, 'season': season}, sort=[('date', 1)])
    if old == None:
        await ctx.followup.send("Error, players oldest stats were not found")
        return
    end = time.time()
    beg = time.mktime(old["date"].timetuple()) + old['date'].microsecond/1000000
    await deltastat(ctx, season, playername, plid, beg, end)

@bot.slash_command(name="link", description="", guild_ids=cmdguilds)
async def link(ctx, playername: discord.Option(str, "playername", required = True, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=True)
    season = getSeason()
    plid = await choosePlayer(ctx, season, playername)
    if plid == None:
        return;
    if mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id}) == None:
        mongoclient["dc"]["links"].insert_one({"dcid": ctx.author.id, "b2plid": plid})
    else:
        mongoclient["dc"]["links"].update_one({"dcid": ctx.author.id}, {"$set": {"dcid": ctx.author.id, "b2plid": plid}})
    # we send an 1x1 transparent image to replace the minilb
    bio = io.BytesIO()
    im = Image.new("RGBA", (1,1), (255, 255, 255, 0))
    im.save(bio, 'PNG')
    bio.seek(0)
    if plid == mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})["b2plid"]:
        await ctx.interaction.edit_original_response(content="You have been succesfully linked", file=discord.File(fp=bio, filename="empty.png"))
    else:
        await ctx.interaction.edit_original_response(content="Something went wrong while linking", file=discord.File(fp=bio, filename="empty.png"))

@bot.slash_command(name="unlink", description="", guild_ids=cmdguilds)
async def unlink(ctx):
    await ctx.defer(ephemeral=True)
    if mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id}) == None:
        await ctx.interaction.edit_original_response(content="You aren't linked to begin with")
        return
    else:
        mongoclient["dc"]["links"].delete_one({"dcid": ctx.author.id})
    if mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id}) == None:
        await ctx.interaction.edit_original_response(content="You have been succesfully unlinked")
    else:
        await ctx.interaction.edit_original_response(content="Something went wrong while unlinking")

@bot.slash_command(name="rpr", description="render profile image", guild_ids=cmdguilds)
async def rpr(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    season = getSeason()
    plid = None
    if playername == None:
        plid = mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a plyername as an input or link your discord accout to Battles 2 name (/link)")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, playername)
    lb = mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    im = imagegen.genLBEImage(mongoclient["b2"]["players"].find({"season": season, "plid": plid}).sort("date", -1).limit(1)[0], lbsize, getSeasonN())
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'PNG')
        imbytes.seek(0)
        await ctx.respond(file=discord.File(fp=imbytes, filename='image.png'))

if __name__ == "__main__":
    time.sleep(3)
    global mongoclient
    mongoclient = pymongo.MongoClient("mongodb://root:example@database:27017/")
    TOKEN = os.getenv("DC_TOKEN")
    bot.run(TOKEN)

