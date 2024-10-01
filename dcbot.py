import time
import io
import os
import discord
import pymongo
import motor.motor_asyncio
import datetime
import zoneinfo
import asyncio
import cProfile, pstats, io, tracemalloc

from dotenv import load_dotenv
from PIL import Image

import imagegen.imagegen as imagegen
import imagegen.textutil as textutil
import lbutil
from playerspecifier import PlayerChooserView, PlayerChooserViewScroll, LbView, NamehistView

async def getSMap():
    return await mongoclient['sutil']['map'].find_one({'_id': 'seasonmap'})

async def getSNMap():
    return await mongoclient['sutil']['map'].find_one({'_id': 'seasonNmap'})

if __name__ == "__main__":
    load_dotenv()
    time.sleep(3)
    global mongoclient
    mongoclient = motor.motor_asyncio.AsyncIOMotorClient("mongodb://root:example@database:27017/")
    loop = asyncio.get_event_loop()
    tasks = getSMap(), getSNMap()
    seasonmap, seasonNmap = loop.run_until_complete(asyncio.gather(*tasks))
    del seasonmap['_id']
    del seasonNmap['_id']
    seasonlist = list(seasonmap.keys())
    guild = os.getenv("GUILD")
    global cmdguilds
    cmdguilds = []
    if guild != 0:
        cmdguilds.append(guild)

bot = discord.Bot()

async def getSeason():
    season = await mongoclient["sutil"]["sutil"].find_one({"_id": 0})
    return season["seasonid"]

async def getSeasonN():
    seasonN = await mongoclient["sutil"]["sutil"].find_one({"_id": 0})
    return seasonN["seasonN"]

async def getPlayer(plid, season, seasonNull=False):
    if seasonNull:
        res = await mongoclient["b2"]["players"].find_one({"plid": plid}, sort=[("date", -1)])
    else:
        res = await mongoclient["b2"]["players"].find_one({"plid": plid, "season": season}, sort=[("date", -1)])
    if res == None:
        return None
    if not res['season'] == season:
        res['hidescore'] = True
    else:
        lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
        plidlb = []
        for i in lb["lb"]:
            plidlb.append(i['profile'])
        if len(plidlb)>0 and not res['plid'] in plidlb:
            res['flagged'] = True
    return res

async def choosePlayer(ctx, season, seasonN, playername):
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    orgplayername = playername
    playername = playername.lower()
    lblist = []
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
    elif playername[:2] == '\\f':
        realname = playername[2:]
        plids = await mongoclient["b2"]["players"].aggregate([
            {"$match": {"season": season}},
            {"$group": {"_id": "$plid"}}
        ]).to_list(length=None)
        if plids == None:
            await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do) [the bot works only on HoM players]")
        plids = list(plids)
        for i in plids:
            cur = await getPlayer(i["_id"], season)
            if cur['body']['displayName'].lower() == realname:
                lblist.append(cur)
    elif playername[:2] == '\\m':
        realname = playername[2:]
        plids = await mongoclient["b2"]["players"].aggregate([
            {"$group": {"_id": "$plid"}}
        ]).to_list(length=None)
        if plids == None:
            await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do) [the bot works only on HoM players]")
        plids = list(plids)
        for i in plids:
            cur = await getPlayer(i["_id"], season, seasonNull=True)
            if cur['body']['displayName'].lower() == realname:
                #if not i['_id'] in plidlb:
                #    cur["flagged"] = True
                lblist.append(cur)
    elif len(playername) == 90:
        return playername
    else:
        for i in lb["lb"]:
            if i["displayName"].lower() == playername:
                lblist.append(await getPlayer(i["profile"], season))
    if len(lblist) == 0:
        await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do) [the bot works only on HoM players]")
        return None
    if len(lblist) == 1:
        return lblist[0]["plid"]
    seenplaces = {}
    for i in lblist:
        if i['place'] in seenplaces:
            i['place'] = i['place'] + (seenplaces[i['place']]/10)
            seenplaces[i['place']] += 1
        else:
            seenplaces[i['place']] = 0
    # dont use the view with buttons when list is short enough
    if len(lblist) <= 8:
        view = PlayerChooserView(ctx, lblist, lbsize, "score", "score", seasonN, 8, 0, -2)
    else:
        view = PlayerChooserViewScroll(ctx, lblist, lbsize, "score", "score", seasonN, 8, 0, -2)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content="Timed out!", view=None)
        return None
    return view.plid

async def deltastat(ctx, extended, season, seasonN, playername, plid, beg, end):
    if beg <= 1:
        beg = 1
    if end <= 1:
        end = 1
    if (beg > end):
        await ctx.followup.send("Time interval must begin earlier then it ends")
        return False
    if plid == None:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    if plid == None:
        return False
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return False
    oldstat = await mongoclient["b2"]["players"].find_one({"plid": plid, "season": season, "date": {"$lte": datetime.datetime.utcfromtimestamp(beg)}}, sort=[("date", -1)])
    if oldstat == None:
        oldest = await mongoclient["b2"]["players"].find_one({"plid": plid, "season": season}, sort=[("date", 1)])
        if oldest == None:
            await ctx.followup.send(f"There are no stats for player {playername}")
            return False
        oldesttime = time.mktime(oldest["date"].timetuple())
        await ctx.followup.send(f"There are no stats this old for this season (<t:{int(beg)}:f>), oldest stats available for player {playername} are from <t:{int(oldesttime)}:f> [<t:{int(oldesttime)}:R>]")
        return False
    newstat = await mongoclient["b2"]["players"].find_one({"plid": plid, "season": season, "date": {"$lte": datetime.datetime.utcfromtimestamp(end)}}, sort=[("date", -1)])
    lbsizeold = await mongoclient["b2"]["lb"].find_one({"season": season, "date": {"$lte": datetime.datetime.utcfromtimestamp(end)}}, sort=[("date", -1)])
    #beg = oldstat["date"].astimezone(datetime.timezone.utc).timestamp()
    #end = newstat["date"].astimezone(datetime.timezone.utc).timestamp()
    if lbsizeold == None:
        lbsizeold = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", 1)])
    lbsizeold = lbsizeold["lbsize"]
    flagged = True
    for i in lb["lb"]:
        if i['profile'] == plid:
            flagged = False
    newstat['flagged'] = flagged

    #matchlist = await mongoclient["b2"]["matches"].aggregate([
    #    {"$match": {"season": season, "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}}
    #]).to_list(length=None)
    #elodecay = 0
    #if len(matchlist) > 0:
    #    matchlist = sorted(matchlist, key=lambda d: d["date"])
    #    for i in range(1, len(matchlist)):
    #        t = matchlist[i]["date"].astimezone(datetime.timezone.utc).timestamp() - matchlist[i-1]["date"].astimezone(datetime.timezone.utc).timestamp()
    #        elodecay += max(0, 5*(((t/3600)-72)//2))
    #    t = end - matchlist[len(matchlist)-1]["date"].astimezone(datetime.timezone.utc).timestamp()
    #    elodecay += max(0, 5*(((t/3600)-72)//2))
    #    begmatch = await mongoclient["b2"]["matches"].find_one({"date": {"$lte": datetime.datetime.utcfromtimestamp(beg-1)}})
    #    if begmatch != None:
    #        t = matchlist[0]["date"].astimezone(datetime.timezone.utc).timestamp() - begmatch["date"].astimezone(datetime.timezone.utc).timestamp()
    #        if t < 3600*2:
    #            t = matchlist[0]["date"].astimezone(datetime.timezone.utc).timestamp() - beg
    #            elodecay += max(0, 5*(((t/3600)-72)//2))
    #else:
    #    pass
    #print(elodecay ,flush=True)
    elodecay = 0
    playtime = await mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "playtime": {"$sum": "$body.duration"}}}
    ]).to_list(length=None)
    if playtime == []:
        playtime = 0
    else:
        playtime = playtime[0]["playtime"]
    # wins get delivered with big delay so we count them from matches
    winsR = await mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "winner": plid, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "win": {"$sum": 1}}}
    ]).to_list(length=None)
    if winsR == []:
        winsR = 0
    else:
        winsR = winsR[0]["win"]
    # losses too
    lossesR = await mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "loser": plid, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "lll": {"$sum": 1}}}
    ]).to_list(length=None)
    if lossesR == []:
        lossesR = 0
    else:
        lossesR = lossesR[0]["lll"]
    # draws
    drawsR = await mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "winner": 'draw', "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "ddd": {"$sum": 1}}}
    ]).to_list(length=None)
    if drawsR == []:
        drawsR = 0
    else:
        drawsR = drawsR[0]["ddd"]
    # full draws (without counting opponentLobbyDC)
    drawsRFull = await mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season, "body.playerRight.result": 'draw', "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
        {"$group": {"_id": 1, "ddd": {"$sum": 1}}}
    ]).to_list(length=None)
    if drawsRFull == []:
        drawsRFull = 0
    else:
        drawsRFull = drawsRFull[0]["ddd"]
    # send some info about latest match too
    try:
        lm = await mongoclient["b2"]["latestm"].find_one({"_id": plid})
        if lm["match"]["winner"] == plid:
            lmres = "won"
        elif lm["match"]["loser"] == plid:
            lmres = "lost"
        else:
            lmres = "drawn"
        if lm["match"]["body"]["playerLeft"]["profileURL"] == plid:
            lmopponent = lm["match"]["body"]["playerRight"]["displayName"]
        else:
            lmopponent = lm["match"]["body"]["playerLeft"]["displayName"]
        matchstring = f"(newest recorded match was {lmres} against {lmopponent})"
    except:
        matchstring = ""
    # generate image
    if extended:
        # peak elo from bot data, we may add in the more accurate tracking data some time in the future
        peakguess = max(oldstat["score"], newstat["score"])
        peakelo = await mongoclient["b2"]["players"].aggregate([
            {"$match": {"season": season, "plid": plid, "score": {"$gte": peakguess}, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}},
            {"$group": {"_id": 1, "max": {"$max": "$score"}}}
        ]).to_list(length=None)
        if peakelo == []:
            peakelo = peakguess
        else:
            peakelo = peakelo[0]["max"]
        im = await imagegen.genDeltaStatImageExtended(oldstat, newstat, winsR, lossesR, drawsR, drawsRFull, elodecay, peakelo, playtime, lbsizeold, seasonN)
    else:
        im = await imagegen.genDeltaStatImage(oldstat, newstat, winsR, lossesR, drawsR, elodecay, playtime, lbsizeold, seasonN)
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'PNG')
        imbytes.seek(0)
        await ctx.interaction.edit_original_response(content="Stat difference between <t:"+str(int(time.mktime(oldstat["date"].timetuple())))+":f> and <t:"+str(int(time.mktime(newstat["date"].timetuple())))+":f> "+matchstring,
            file=discord.File(fp=imbytes, filename='image.png'))
        return True

async def autocompletePname(ctx: discord.AutocompleteContext):
    try:
        season = ctx.options["season"]
    except:
        season = None
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    lb = await mongoclient["b2"]["lb"].find_one({'season': season}, sort=[("date", -1)])
    possible = list(lb["namelist"])
    matched = []
    for i in possible:
        if ctx.options["playername"].lower() in i.lower() and len(matched) < 25:
            matched.append(i)
    return matched

async def autocompleteTimezone(ctx: discord.AutocompleteContext):
    possible = zoneinfo.available_timezones()
    matched = []
    for i in possible:
        if ctx.options["timezone"].lower() in i.lower() and len(matched) < 25:
            matched.append(i)
    return matched

async def autocompletePname_opponent(ctx: discord.AutocompleteContext):
    try:
        season = ctx.options["season"]
    except:
        season = None
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    lb = await mongoclient["b2"]["lb"].find_one({'season': season}, sort=[("date", -1)])
    possible = list(lb["namelist"])
    matched = []
    for i in possible:
        if ctx.options["opponent"].lower() in i.lower() and len(matched) < 25:
            matched.append(i)
    return matched

@bot.slash_command(name="ndaily", description="Show stat difference between now and n days (n*24h) ago (n dosen't need to be integer)", guild_ids=cmdguilds)
async def ndaily(ctx, n: discord.Option(float, "n", required = True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*24*n
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="24h", description="Show stat difference between now and one day (24h) ago", guild_ids=cmdguilds)
async def daily24h(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*24
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="12h", description="Show stat difference between now and 12h (half a day) ago", guild_ids=cmdguilds)
async def halfdaily12h(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*12
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="previous24h", description="Show stat difference between one day (24h) and two days (48h) ago", guild_ids=cmdguilds)
async def yesterday24h(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()-60*60*24
    beg = end - 60*60*24*2
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="daily", description="Show stat difference between now and the last reset time point (set it with /link)", guild_ids=cmdguilds)
async def daily(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    playertz = await mongoclient["dc"]["tz"].find_one({"dcid": ctx.author.id})
    if playertz == None:
        await ctx.followup.send("You need to provide your reset time details through /link (or use /24h as an alternative)")
        return
    end = time.time()
    beg = midnight=(datetime.datetime.now(zoneinfo.ZoneInfo(playertz['tz']))).replace(hour=playertz['rh'], minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
    if beg > time.time():
        beg -= 60*60*24
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="yesterday", description="Show stat difference between the last reset time point and 24h earlier (set it with /link)", guild_ids=cmdguilds)
async def yesterday(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    playertz = await mongoclient["dc"]["tz"].find_one({"dcid": ctx.author.id})
    if playertz == None:
        await ctx.followup.send("You need to provide your reset time details through /link (or use /24h as an alternative)")
        return
    end = midnight=(datetime.datetime.now(zoneinfo.ZoneInfo(playertz['tz']))).replace(hour=playertz['rh'], minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
    if end > time.time():
        end -= 60*60*24
    beg = end-60*60*24
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="weekly", description="Show stat difference between now and one week ago", guild_ids=cmdguilds)
async def daily(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    #beg = time.time()
    beg = end - 60*60*24*7
    await deltastat(ctx, extended, season, await getSeasonN(), playername, plid, beg, end)

@bot.slash_command(name="delta", description="Show stat difference between beg and end (unix timestamps)", guild_ids=cmdguilds)
async def delta(ctx, beg: discord.Option(float, "beg", required = True), end: discord.Option(float, "end", required = True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    await deltastat(ctx, extended, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="seasonal", description="Show stats for this season", guild_ids=cmdguilds)
async def seasonal(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), extended: discord.Option(bool, "extended", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    if plid == None:
        return
    old = await mongoclient['b2']['players'].find_one({'plid': plid, 'season': season}, sort=[('date', 1)])
    if old == None:
        await ctx.followup.send("Error, players oldest stats were not found")
        return
    end = time.time()
    beg = time.mktime(old["date"].timetuple()) + old['date'].microsecond/1000000
    await deltastat(ctx, extended, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="seasoninfo", description="Show some info about the chosen season", guild_ids=cmdguilds)
async def seasoninfo(ctx, season: discord.Option(str, "season", choices=seasonlist, required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    slistentry = await mongoclient['sutil']['slist'].find_one({'_id': season})
    starttime = slistentry['start']//1000
    endtime = slistentry['end']//1000
    matchinfo = await mongoclient["b2"]["matches"].aggregate([
        {"$match": {"season": season}},
        {"$group": {"_id": 1, "playtime": {"$sum": "$body.duration"}, "nummatches": {"$sum": 1}}}
    ]).to_list(length=None)
    if matchinfo == []:
        playtime = 0
        nummatches = 0
    else:
        playtime = matchinfo[0]["playtime"]
        nummatches = matchinfo[0]["nummatches"]
    playtime = textutil.time_round(playtime)
    uniqueplayers = await mongoclient["b2"]["players"].aggregate([
        {"$match": {"season": season}},
        {"$group": {"_id": "$plid"}},
        {"$group": {"_id": 1, "uniqueplayers": {"$sum": 1}}}
    ]).to_list(length=None)
    if uniqueplayers == []:
        uniqueplayers = 0
    else:
        uniqueplayers = uniqueplayers[0]["uniqueplayers"]
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    lbsize = lb['lbsize']
    await ctx.interaction.edit_original_response(content=f"Season {seasonN} ({season}):\n- Starts: <t:{starttime}:f> (<t:{starttime}:R>)\n- Ends: <t:{endtime}:f> (<t:{endtime}:R>)\n- During the season {nummatches} matches were played on HoM totalling {playtime}\n- {lbsize} players are on the most recent leaderboard ({uniqueplayers-lbsize} disappeared from the lb throughout the season)")

@bot.slash_command(name="scanstatus", description="Show info on database update", guild_ids=cmdguilds)
async def scanstatus(ctx):
    await ctx.defer(ephemeral=False)
    season = await getSeason()
    seasonN = seasonNmap[season]
    res = f"Latest season: Season {seasonN} ({season})\n"
    lb = await mongoclient["b2"]["lb"].find_one({}, sort=[("date", -1)])
    if lb == None:
        res += "Latest lb not found\n"
    else:
        timestamp = int(lb['date'].astimezone(datetime.timezone.utc).timestamp())
        res += f"Latest lb date: <t:{timestamp}:f>\n"
    match = await mongoclient["b2"]["matches"].find_one({}, sort=[("date", -1)])
    if match == None:
        res += "Latest match not found\n"
    else:
        timestamp = int(match['date'].astimezone(datetime.timezone.utc).timestamp())
        res += f"Latest match date: <t:{timestamp}:f>\n"
    player = await mongoclient["b2"]["players"].find_one({}, sort=[("date", -1)])
    if player == None:
        res += "Latest player not found\n"
    else:
        timestamp = int(player['date'].astimezone(datetime.timezone.utc).timestamp())
        res += f"Latest player date: <t:{timestamp}:f>\n"
    await ctx.interaction.edit_original_response(content=res)

@bot.slash_command(name="vs", description="Show wins and losses against another player", guild_ids=cmdguilds)
async def vs(ctx, opponent: discord.Option(str, "opponent", required = True, autocomplete=autocompletePname_opponent), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), ndaily: discord.Option(int, "n last days are taken into consideration", required=False)):
    await ctx.defer(ephemeral=False)
    # "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if not ndaily == None:
        cutoffdate = max(1, time.time()-24*3600*ndaily)
    if season == None or seasonNull:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    plido = await choosePlayer(ctx, season, seasonN, opponent)
    if seasonNull:
        draws = await mongoclient["b2"]["matches"].aggregate([
            {"$match": {"winner": "draw", "loser": "draw", "$or": [{"$and": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plido}]}, {"$and": [{"body.playerRight.profileURL": plido}, {"body.playerLeft.profileURL": plid}]}], "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
            {"$group": {"_id": 1, "dd": {"$sum": 1}}}
        ]).to_list(length=None)
    else:
        draws = await mongoclient["b2"]["matches"].aggregate([
            {"$match": {"season": season, "winner": "draw", "loser": "draw", "$or": [{"$and": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plido}]}, {"$and": [{"body.playerRight.profileURL": plido}, {"body.playerLeft.profileURL": plid}]}], "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
            {"$group": {"_id": 1, "dd": {"$sum": 1}}}
        ]).to_list(length=None)
    if draws == []:
        draws = 0
    else:
        draws = draws[0]["dd"]
    if seasonNull:
        wins = await mongoclient["b2"]["matches"].aggregate([
            {"$match": {"winner": plid, "loser": plido, "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
            {"$group": {"_id": 1, "win": {"$sum": 1}}}
        ]).to_list(length=None)
    else:
        wins = await mongoclient["b2"]["matches"].aggregate([
            {"$match": {"season": season, "winner": plid, "loser": plido, "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
            {"$group": {"_id": 1, "win": {"$sum": 1}}}
        ]).to_list(length=None)
    if wins == []:
        wins = 0
    else:
        wins = wins[0]["win"]
    if seasonNull:
        winso = await mongoclient["b2"]["matches"].aggregate([
            {"$match": {"winner": plido, "loser": plid, "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
            {"$group": {"_id": 1, "win": {"$sum": 1}}}
        ]).to_list(length=None)
    else:
        winso = await mongoclient["b2"]["matches"].aggregate([
            {"$match": {"season": season, "winner": plido, "loser": plid, "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
            {"$group": {"_id": 1, "win": {"$sum": 1}}}
        ]).to_list(length=None)
    if winso == []:
        winso = 0
    else:
        winso = winso[0]["win"]
    profile = await getPlayer(plid, season, seasonNull=seasonNull)
    profileo = await getPlayer(plido, season, seasonNull=seasonNull)
    if profile == None:
        ctx.followup.send("Player (main) not found")
        return
    if profileo == None:
        ctx.followup.send("Player (opponent) not found")
        return
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    im = await imagegen.genVs(profile, profileo, wins, winso, draws, lbsize, seasonN)
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'PNG')
        imbytes.seek(0)
        msgtext = ""
        if seasonNull:
            msgtext = f"Wins/losses for the last {ndaily} days"
            if cutoffdate < 1701961220: # season 16 start
                msgtext += " (the bot doesn't see anything earlier than season 16)"
        elif not ndaily == None:
            msgtext = f"Wins/losses for season {seasonN} for the last {ndaily} days"
            if cutoffdate < 1701961220: # season 16 start
                msgtext += " (the bot doesn't see anything earlier than season 16)"
        else:
            msgtext = f"Wins/losses for season {seasonN}"
        await ctx.interaction.edit_original_response(content=msgtext,
            file=discord.File(fp=imbytes, filename='image.png'))
        return True

@bot.slash_command(name="_eloexp", description="runs HoM match database through an alternate elo system", guild_ids=cmdguilds)
async def eloexp(ctx, mode: discord.Option(str, "type", choices=['elo', 'elo capped'], required=True), season: discord.Option(str, "season", choices=seasonlist, required=False), k: discord.Option(int, "k", required=False), b: discord.Option(int, "b", required=False), i: discord.Option(int, "i", required=False), cap: discord.Option(int, "cap", required=False), start: discord.Option(int, "start", required=False)):
    await ctx.defer()
    if k == None:
        k = 32
    if b == None:
        b = 10
    if i == None:
        i = 400
    if start == None:
        start = 1500
    if cap == None:
        cap = 400
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    lblist = []
    lblist = await lbutil.eloexperiment(mongoclient, season, lb, mode, k, i, b, cap, start)
    view = LbView(ctx, lblist, lbsize, "eloexp", "eloexp", seasonN, 8, 0, 0)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="lb", description="Shown leaderboards of selected stat", guild_ids=cmdguilds)
async def lb(ctx, mode: discord.Option(str, "type", choices=['score', 'wins', 'losses', 'winrate', 'w/l', 'l/w', 'playtime', 'games played', 'avg match duration', 'score gained'], required=True), min_games: discord.Option(int, "min games", required=False), min_score: discord.Option(int, "min score", required=False), season: discord.Option(str, "season", choices=seasonlist, required=False), ndaily: discord.Option(int, "n last days are taken into consideration", required=False)):
    await ctx.defer()
    if min_games == None:
        min_games = 0
    if min_score == None:
        min_score = 0
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if not ndaily == None:
        cutoffdate = max(1, time.time()-24*3600*ndaily)
    if season == None or seasonNull:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    lblist = []
    if mode == 'score':
        for i in lb["lb"]:
            lblist.append(await getPlayer(i["profile"], season))
        if min_games > 0:
            newlist = []
            mglist = await lbutil.getlb(mongoclient, season, False, 1, "score", min_games, min_score, lb)
            for i in range(len(mglist)):
                mglist[i] = mglist[i]["plid"]
            for i in lblist:
                if i["plid"] in mglist:
                    newlist.append(i)
            lblist = newlist
    elif mode == 'score gained':
        # this possibly can be made faster with a list of seasons (mongo quer seems overkill)
        if seasonNull:
            ulbl = await mongoclient['b2']['lb'].aggregate([
                {"$match": {"date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
                {"$sort": {'date': -1}},
                {"$group":{"_id": '$season', "lbo": {"$first": "$$ROOT"}}},
                {"$replaceRoot": {"newRoot": "$lbo"}},
                {"$sort": {'date': 1}}
            ]).to_list(length=None)
        else:
            ulbl = await mongoclient['b2']['lb'].aggregate([
                {"$match": {"season": season, "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}},
                {"$sort": {'date': -1}},
                {"$group":{"_id": '$season', "lbo": {"$first": "$$ROOT"}}},
                {"$replaceRoot": {"newRoot": "$lbo"}},
                {"$sort": {'date': 1}}
            ]).to_list(length=None)
        lbdict = {}
        for ii in ulbl:
            for i in ii['lb']:
                if not i['profile'] in lbdict:
                    lbdict[i['profile']] = 0
                lbdict[i['profile']] += i['score']-3500
        nlb = await mongoclient['b2']['lb'].find_one({'date': {'$lte': datetime.datetime.utcfromtimestamp(cutoffdate)}}, sort=[('date', -1)])
        if nlb != None:
            for i in nlb['lb']:
                if i['profile'] in lbdict:
                    lbdict[i['profile']] += 3500-i['score']
        for i in lbdict.keys():
            tmp = await getPlayer(i, season, seasonNull)
            if tmp == None:
                print(i, flush=True)
            tmp['__lbprop'] = lbdict[i]
            tmp['__lbsort'] = lbdict[i]
            lblist.append(tmp)
        lblist = sorted(lblist, key=lambda d: d['__lbsort'], reverse=True)
        for index, i in enumerate(lblist, 1):
            i["__lbplace"] = index
        for i in range(1, len(lblist)):
            if lblist[i]["__lbsort"] == lblist[i-1]["__lbsort"]:
                lblist[i]["__lbplace"] = lblist[i-1]["__lbplace"]
    else:
        lblist = await lbutil.getlb(mongoclient, season, seasonNull, cutoffdate, mode, min_games, min_score, lb)
    msgtext = ""
    passedSeasonN = None
    if seasonNull:
        msgtext = f"{mode} for the last {ndaily} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    elif not ndaily == None:
        passedSeasonN = seasonN
        msgtext = f"{mode} for season {seasonN} for the last {ndaily} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    else:
        passedSeasonN = seasonN
        msgtext = f"{mode} for season {seasonN}"
    if len(lblist) == 0:
        await ctx.interaction.edit_original_response(content=f"The selected leaderboard ({mode} with {min_games} min games) is empty, you can try selecting lower min games")
        return
    view = LbView(ctx, lblist, lbsize, mode, msgtext, passedSeasonN, 8, min_games, min_score)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="vs_lb", description="Shows a leaderboard of who you won/lost agains the most", guild_ids=cmdguilds)
async def vslb(ctx, mode: discord.Option(str, "type", choices=['wins against player', 'losses against player', 'winrate against player', 'w/l against player', 'l/w against player', 'games played against player'], required=True), playername: discord.Option(str, "playername", required=False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), min_score: discord.Option(int, "min score", required=False), min_games: discord.Option(int, "min games", required=False), ndaily: discord.Option(int, "n last days are taken into consideration", required=False)):
    await ctx.defer()
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if not ndaily == None:
        cutoffdate = max(1, time.time()-24*3600*ndaily)
    if season == None or seasonNull:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    if not seasonNull and playername != None and playername[:2] == "\\m":
        seasonNull = True
    if min_games == None:
        min_games = 0
    if min_score == None:
        min_score = 0
    if min_score != 0 and seasonNull == True:
        await ctx.followup.send(f"You can't use min_score in multiseasonal mode")
        return
    if mode == "wins against player":
        mode= "wins"
    if mode == "losses against player":
        mode = "losses"
    if mode == "winrate against player":
        mode = "winrate"
    if mode == "w/l against player":
        mode = "w/l"
    if mode == "l/w against player":
        mode = "l/w"
    if mode == "games played against player":
        mode = "games played"
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    if plid == None:
        return
    vsname = await mongoclient['b2']['players'].find_one({'plid': plid}, sort=[('date', -1)])
    if vsname == None:
        vsname = "<no name found>"
    else:
        vsname = vsname['body']['displayName']
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    lblist = []
    lblist = await lbutil.getlbvs(mongoclient, season, seasonNull, cutoffdate, mode, min_games, min_score, lb, plid)
    if len(lblist) == 0:
        await ctx.interaction.edit_original_response(content=f"The selected leaderboard is empty")
        return
    msgtext = ""
    if seasonNull:
        msgtext = f"{mode} against {vsname} for the last {ndaily} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    elif not ndaily == None:
        msgtext = f"{mode} against {vsname} for season {seasonN} for the last {ndaily} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    else:
        msgtext = f"{mode} against {vsname} for season {seasonN}"
    view = LbView(ctx, lblist, lbsize, mode, msgtext, None, 8, min_games, min_score)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="link", description="Links B2 account to discord so you can type less", guild_ids=cmdguilds)
async def link(ctx, playername: discord.Option(str, "playername", required=False, autocomplete=autocompletePname), timezone: discord.Option(str, "timezone", required=False, autocomplete=autocompleteTimezone), reset_hour: discord.Option(int, "reset hour (24h format, without minutes)", required=False)):
    await ctx.defer(ephemeral=True)
    if playername == None and timezone == None:
        await ctx.followup.send("You need to provide some arguments for /link to make sense", ephemeral=True)
    plid = None
    midnight = None
    if playername != None:
        season = await getSeason()
        plid = await choosePlayer(ctx, season, await getSeasonN(), playername)
        if plid == None:
            return
        if await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id}) == None:
            await mongoclient["dc"]["links"].insert_one({"dcid": ctx.author.id, "b2plid": plid})
        else:
            await mongoclient["dc"]["links"].update_one({"dcid": ctx.author.id}, {"$set": {"dcid": ctx.author.id, "b2plid": plid}})
    if timezone != None:
        if not timezone in zoneinfo.available_timezones():
            await ctx.followup.send("Invalid timezone, you must choose the timezone from the autocomplete list (it's case sensitive)", ephemeral=True)
        else:
            if reset_hour == None:
                reset_hour = 0
            reset_hour = reset_hour%24
            if await mongoclient["dc"]["tz"].find_one({"dcid": ctx.author.id}) == None:
                await mongoclient["dc"]["tz"].insert_one({"dcid": ctx.author.id, "tz": timezone, "rh": reset_hour})
            else:
                await mongoclient["dc"]["tz"].update_one({"dcid": ctx.author.id}, {"$set": {"dcid": ctx.author.id, "tz": timezone, "rh": reset_hour}})
    # we send an 1x1 transparent image to replace the minilb
    bio = io.BytesIO()
    im = Image.new("RGBA", (1,1), (255, 255, 255, 0))
    im.save(bio, 'PNG')
    bio.seek(0)
    if plid != None:
        rlylinked = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == rlylinked["b2plid"]:
            await ctx.followup.send(content="You have been succesfully linked", file=discord.File(fp=bio, filename="empty.png"), ephemeral=True)
        else:
            await ctx.followup.send(content="Something went wrong while linking", file=discord.File(fp=bio, filename="empty.png"), ephemeral=True)
    if timezone != None:
        midnight=(datetime.datetime.now(zoneinfo.ZoneInfo(timezone))).replace(hour=reset_hour, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
        if midnight > time.time():
            midnight -= 60*60*24
        await ctx.followup.send(f"Your reset time for /today has been set to <t:{int(midnight)}:t>", ephemeral=True)

@bot.slash_command(name="unlink", description="Unlinks /link", guild_ids=cmdguilds)
async def unlink(ctx):
    await ctx.defer(ephemeral=True)
    if await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id}) == None and await mongoclient["dc"]["tz"].find_one({"dcid": ctx.author.id}) == None:
        await ctx.interaction.edit_original_response(content="You aren't linked to begin with")
        return
    else:
        await mongoclient["dc"]["links"].delete_one({"dcid": ctx.author.id})
        await mongoclient["dc"]["tz"].delete_one({"dcid": ctx.author.id})
    if await mongoclient["dc"]["links"].  find_one({"dcid": ctx.author.id}) == None and await mongoclient["dc"]["tz"].find_one({"dcid": ctx.author.id}) == None:
        await ctx.interaction.edit_original_response(content="You have been succesfully unlinked")
    else:
        await ctx.interaction.edit_original_response(content="Something went wrong while unlinking")

@bot.slash_command(name="namehistory", description="Shows a history of player's name and profile look", guild_ids=cmdguilds)
async def namehistory(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", choices=seasonlist, required=False), include_medals: discord.Option(bool, "does a change in badges equipped constitute a new profile", required=False), multiseasonal: discord.Option(bool, "should the namelist go through all recorded season", required=False)):
    await ctx.defer(ephemeral=False)
    if season == None:
        season = await getSeason()
    else:
        season = seasonmap[season]
    seasonN = seasonNmap[season]
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    if plid == None:
        return
    includedProps = {"name": "$body.displayName", "border": "$body.equippedBorder", "banner": "$body.equippedBanner", "pfp": "$body.equippedAvatar"}
    if include_medals:
        includedProps["medals"] = "$body.badges_equipped"
    if multiseasonal == True:
        pastprofiles = await mongoclient['b2']['players'].aggregate([
            {"$match": {"plid": plid}},
            {"$group":{"_id": includedProps, "player": {"$first": "$$ROOT"}}},
            {"$replaceRoot": {"newRoot": "$player"}},
            {"$sort": {"date": -1}}
        ]).to_list(length=None)
    else:
        pastprofiles = await mongoclient['b2']['players'].aggregate([
            {"$match": {"season": season, "plid": plid}},
            {"$group":{"_id": includedProps, "player": {"$first": "$$ROOT"}}},
            {"$replaceRoot": {"newRoot": "$player"}},
            {"$sort": {"date": -1}}
        ]).to_list(length=None)
    for i in pastprofiles:
        i["hidescore"] = True
        i["__lbprop"] = ""
        i["__lbplace"] = 0
        if not include_medals:
            i["body"]["badges_equipped"] = []
    view = NamehistView(ctx, pastprofiles, 0, "namehistory", pastprofiles[0]['body']['displayName'], seasonN, 8, 0, 0)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="b2lol", description="get link for player's b2.lol page", guild_ids=cmdguilds)
async def b2lol_link(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=False)
    season = await getSeason()
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, await getSeasonN(), playername)
    await ctx.interaction.edit_original_response(content=f"https://b2.lol/playerInfo/playerInfo.html?{plid}")

@bot.slash_command(name="plid", description="get player's api url (used as player id internally)", guild_ids=cmdguilds)
async def plid(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=False)
    season = await getSeason()
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, await getSeasonN(), playername)
    await ctx.interaction.edit_original_response(content=plid)

@bot.slash_command(name="rpr", description="render profile image", guild_ids=cmdguilds)
async def rpr(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), no_medals: discord.Option(bool, "hide player's medals from image", required = False), no_score: discord.Option(bool, "hide player's score from image", required = False), fake_score: discord.Option(int, "make player look like they have x score", required = False), fake_place: discord.Option(int, "make player look like they are nth on the lb", required = False)):
    season = await getSeason()
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, await getSeasonN(), playername)
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    player = await mongoclient["b2"]["players"].find_one({"season": season, "plid": plid}, sort=[("date", -1)])
    if fake_place != None:
        player["place"] = fake_place
    if fake_score != None:
        player["score"] = fake_score
    if no_score != None:
        player["score"] = ""
    if no_medals != None:
        player["body"]["badges_equipped"] = []
    im = await imagegen.genLBEImage(player, lbsize, await getSeasonN())
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'PNG')
        imbytes.seek(0)
        await ctx.respond(file=discord.File(fp=imbytes, filename='image.png'))

if __name__ == "__main__":
    TOKEN = os.getenv("DC_TOKEN")
    bot.run(TOKEN)

