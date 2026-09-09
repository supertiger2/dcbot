import time
import io
import os
import discord
import pymongo
import motor.motor_asyncio
import datetime
import zoneinfo
import asyncio
import json
import re
from difflib import SequenceMatcher
import cProfile, pstats, io, tracemalloc

from dotenv import load_dotenv
from PIL import Image

from knownplayers import knownplayers
import towerstat
import imagegen.imagegen as imagegen
import imagegen.textutil as textutil
import lbutil
from playerspecifier import PlayerChooserView, PlayerChooserViewScroll, LbView, NamehistView

if __name__ == "__main__":
    load_dotenv()
    time.sleep(3)
    global mongoclient
    mongoclient = motor.motor_asyncio.AsyncIOMotorClient("mongodb://root:example@database:27017/")
    global seasonmapCache # [timeout, seasonmap, seasonlist]
    seasonmapCache = [0, {}, []]
    guild = os.getenv("GUILD")
    global cmdguilds
    cmdguilds = []
    if guild != 0:
        cmdguilds.append(guild)

bot = discord.Bot()

async def updateUsagestat(name):
    s = await mongoclient["usageinfo"]["cc"].find_one({"_id": name})
    if s == None:
        s = {"_id": name, "count": 0}
        await mongoclient["usageinfo"]["cc"].insert_one(s)
    s['count'] += 1
    await mongoclient["usageinfo"]["cc"].update_one({'_id': name}, {"$set": s})

async def refreshSMap():
    if time.time() < seasonmapCache[0]:
        return
    smapdb = await mongoclient['sutil']['map'].find_one({'_id': 'seasonmap'})
    del smapdb['_id']
    seasonmap = {}
    seasonlist = []
    for k, i in smapdb.items():
        seasonmap[int(''.join(i for i in k if i.isdigit()))] = i
        seasonlist.append(k)
    seasonmapCache[0] = time.time()+3600
    seasonmapCache[1] = seasonmap
    seasonmapCache[2] = seasonlist
    print(seasonmapCache, flush=True)

async def getSMap():
    await refreshSMap()
    return seasonmapCache[1]

async def getSList():
    await refreshSMap()
    return seasonmapCache[2]

async def getSeason(sname, ctx=None, getCurrent=False, forceOutput=False):
    if (not getCurrent) and (sname != None) and (sname != ''):
        sdigits = ''.join(i for i in sname if i.isdigit())
        if sdigits != '':
            snum = int(sdigits)
            seasonmap = await getSMap()
            if snum in seasonmap:
                season = seasonmap[snum]
                return (season, snum)
            else:
                if ctx != None:
                    await ctx.followup.send("No season with given number found")
                if not forceOutput:
                    return (None, None)
        else:
            if ctx != None:
                await ctx.followup.send("No number found in the provided season input")
            if not forceOutput:
                return (None, None)
    seasondb = await mongoclient["sutil"]["sutil"].find_one({"_id": 0})
    return (seasondb["seasonid"], seasondb["seasonN"])

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
    notScoreLb = False
    lbsize = lb["lbsize"]
    orgplayername = playername
    playername = playername.lower()
    lblist = []
    placematch = re.match(r"^\[#(\d+)s(\d+)\]", playername)
    # add special syntax
    if playername[:2] == '\\k' or playername[:2] == '/k':
        if playername.lower() in knownplayers:
            return knownplayers[playername.lower()]
        await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do)")
    elif placematch != None:
        pos = int(placematch.groups()[0])
        sn = int(placematch.groups()[1])
        if seasonN != sn:
            seasonmap = await getSMap()
            if not sn in seasonmap:
                await ctx.followup.send("No season with given number found (while chosing player)")
                return None
            lb = await mongoclient["b2"]["lb"].find_one({"season": seasonmap[sn]}, sort=[("date", -1)])
            lbsize = lb["lbsize"]
            if lb == None:
                await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
                return None
        if pos > 0:
            pos = pos-1
            if pos < 0 or pos > lbsize:
                await ctx.followup.send(f"Out of range (leaderboard has {lbsize} players)")
                return None
        return lb["lb"][pos]["profile"]
    elif playername[:2] == '\\t' or playername[:2] == '/t' or placematch != None:
        # takes a number instead of a name, returns the n-th player from the lb
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
    elif playername[:2] == '\\f' or playername[:2] == '/f':
        # searches for all players with the name bypassing the lb (useful for finding flagged players)
        realname = playername[2:]
        plids = await mongoclient["b2"]["players"].aggregate([
            {"$match": {"searchname": realname}},
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
    elif playername[:2] == '\\m' or playername[:2] == '/m':
        # searches for all players with the name bypassing the lb (useful for doing multiseasonal commands with players who arent active currently)
        notScoreLb = True
        realname = playername[2:]
        plids = await mongoclient["b2"]["players"].aggregate([
            {"$match": {"searchname": realname}},
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
    elif playername[:2] == '\\p' or playername[:2] == '/p':
        # searches for all players who had the name AT SOME POINT in the current season
        realname = playername[2:]
        plids = await mongoclient["b2"]["players"].aggregate([
            {"$match": {"season": season}},
            {"$match": {"searchname": realname}},
            {"$group": {"_id": "$plid"}}
        ]).to_list(length=None)
        if plids == None:
            await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do) [the bot works only on HoM players]")
        plids = list(plids)
        for i in plids:
            cur = await getPlayer(i["_id"], season, seasonNull=True)
            lblist.append(cur)
    elif playername[:2] == '\\h' or playername[:2] == '/h':
        # searches for all players who had the name AT SOME POINT in the whole database
        notScoreLb = True
        realname = playername[2:]
        plids = await mongoclient["b2"]["players"].aggregate([
            {"$match": {"searchname": realname}},
            {"$group": {"_id": "$plid"}}
        ]).to_list(length=None)
        if plids == None:
            await ctx.followup.send(f"No player with the name of {orgplayername} found (capitalization doesn't matter, but spaces do) [the bot works only on HoM players]")
        plids = list(plids)
        for i in plids:
            cur = await getPlayer(i["_id"], season, seasonNull=True)
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
    lblist = sorted(lblist, key=lambda d: d['place'])
    seenplaces = {}
    count = 1
    for i in lblist:
        if i['place'] in seenplaces:
            i['place'] = i['place'] + (seenplaces[i['place']]/100)
            seenplaces[i['place']] += 1
        else:
            seenplaces[i['place']] = 0
        if notScoreLb:
            i['__lbplace'] = count
        else:
            i['__lbplace'] = i['place']
        i['__lbprop'] = ''
        count += 1
    # dont use the view with buttons when list is short enough
    if len(lblist) <= 8:
        if notScoreLb:
            view = PlayerChooserView(ctx, lblist, lbsize, "arbitrary", "arbitrary", seasonN, 8, 0, -2, 2147483647)
        else:
            view = PlayerChooserView(ctx, lblist, lbsize, "score", "score", seasonN, 8, 0, -2, 2147483647)
    else:
        if notScoreLb:
            view = PlayerChooserViewScroll(ctx, lblist, lbsize, "arbitrary", "arbitrary", seasonN, 8, 0, -2, 2147483647)
        else:
            view = PlayerChooserViewScroll(ctx, lblist, lbsize, "score", "score", seasonN, 8, 0, -2, 2147483647)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content="Timed out!", view=None)
        return None
    return view.plid

async def parseDate(input, begmode=True):
    if input == "0":
        return 0
    try:
        try:
            res = float(input)
            return time.time()-24*3600*res
        except ValueError:
            pass
        # check for "<number>" assumed to be ndaily
        match = re.match(r"^(\d+)$", input)
        if match != None:
            return time.time()-24*3600*float(match.groups()[0])
        # check for "u<timestamp>"
        match = re.match(r"^u(\d+)$", input)
        if match != None:
            return match.groups()[0]
        # check for "D/M/Y"
        match = re.match(r"^(\d+)/(\d+)/(\d+)$", input)
        if match != None:
            g = match.groups()
            return datetime.datetime(int(g[2]), int(g[1]), int(g[0]), 0, 0, 0, 0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
        # check for "D.M.Y"
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", input)
        if match != None:
            g = match.groups()
            return datetime.datetime(int(g[2]), int(g[1]), int(g[0]), 0, 0, 0, 0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
        # check for "D/M/Y H:M"
        match = re.match(r"^(\d+)/(\d+)/(\d+) (\d+):(\d+)$", input)
        if match != None:
            g = match.groups()
            return datetime.datetime(int(g[2]), int(g[1]), int(g[0]), int(g[3]), int(g[4]), 0, 0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
        # check for "D.M.Y H:M"
        match = re.match(r"^(\d+)\.(\d+)\.(\d+) (\d+):(\d+)$", input)
        if match != None:
            g = match.groups()
            return datetime.datetime(int(g[2]), int(g[1]), int(g[0]), int(g[3]), int(g[4]), 0, 0).astimezone(datetime.timezone.utc).astimezone(datetime.timezone.utc).timestamp()
        # check for "s<number>"
        match = re.match(r"^[sS](\d+)$", input)
        if match != None:
            (season, seasonN) = await getSeason(match.groups()[0])
            if season == None:
                return None
            res = await mongoclient['sutil']['slist'].find_one({'_id': season})
            if begmode:
                return res["start"]//1000
            else:
                return res["end"]//1000
        # check for "s<number>-<number>"
        match = re.match(r"^[sS](\d+)-(\d+)$", input)
        if match != None:
            (season, seasonN) = await getSeason(match.groups()[0])
            if season == None:
                return None
            res = await mongoclient['sutil']['slist'].find_one({'_id': season})
            if begmode:
                return (res["start"]//1000)-24*3600*int(match.groups()[1])
            else:
                return (res["end"]//1000)-24*3600*int(match.groups()[1])
        # check for "s<number>+<number>"
        match = re.match(r"^[sS](\d+)\+(\d+)$", input)
        if match != None:
            (season, seasonN) = await getSeason(match.groups()[0])
            if season == None:
                return None
            res = await mongoclient['sutil']['slist'].find_one({'_id': season})
            if begmode:
                return (res["start"]//1000)+24*3600*int(match.groups()[1])
            else:
                return (res["end"]//1000)+24*3600*int(match.groups()[1])
        return None
    except:
        return None

async def countmatches(toSum, *filters, matchdb="matches"):
    filter = {}
    for i in filters:
        filter.update(i)
    matches = await mongoclient["b2"][matchdb].aggregate([
        {"$match": filter},
        {"$group": {"_id": 1, "res": {"$sum": toSum}}}
    ]).to_list(length=None)
    if matches == []:
        return 0
    else:
        return matches[0]["res"]

async def deltastat(ctx, extended, useDeltasNotMatches, season, seasonN, playername, plid, beg, end):
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
        im = await imagegen.genDeltaStatImageExtended(oldstat, newstat, useDeltasNotMatches, winsR, lossesR, drawsR, drawsRFull, elodecay, peakelo, playtime, lbsizeold, seasonN)
    else:
        im = await imagegen.genDeltaStatImage(oldstat, newstat, useDeltasNotMatches, winsR, lossesR, drawsR, elodecay, playtime, lbsizeold, seasonN)
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'WEBP', quality=90)
        imbytes.seek(0)
        await ctx.interaction.edit_original_response(content="Stat difference between <t:"+str(int(time.mktime(oldstat["date"].timetuple())))+":f> and <t:"+str(int(time.mktime(newstat["date"].timetuple())))+":f> "+matchstring,
            file=discord.File(fp=imbytes, filename='image.webp'))
        return True

async def autocompletePname(ctx: discord.AutocompleteContext):
    try:
        season = ctx.options["season"]
    except:
        season = None
    (season, seasonN) = await getSeason(season, forceOutput=True)
    possible = []
    matched = []
    if len(ctx.options["playername"]) > 1 and (ctx.options["playername"][:2] == "\\k" or ctx.options["playername"][:2] == "/k"):
        ctx.options["playername"]
        possible = list(knownplayers.keys())
        for i in possible:
            if ctx.options["playername"].lower() in i.lower() and len(matched) < 25:
                matched.append(i)
    else:
        lb = await mongoclient["b2"]["lb"].find_one({'season': season}, sort=[("date", -1)])
        possible = list(lb["namelist"])
        dontrepeat = []
        for i in range(len(possible)):
            if ctx.options["playername"].lower() in possible[i].lower() and len(matched) < 25 and (not possible[i].lower() in dontrepeat):
                matched.append(possible[i])
                matcher = SequenceMatcher(None, possible[i].lower(), ctx.options["playername"].lower())
                if matcher.quick_ratio() >= 0.75 and matcher.ratio() >= 0.75:
                    if not possible[i].lower() in dontrepeat:
                        dontrepeat.append(possible[i].lower())
                    matched.append('[#'+str(i+1)+'s'+str(seasonN)+'] '+possible[i])
    return matched

async def autocompletePname_opponent(ctx: discord.AutocompleteContext):
    try:
        season = ctx.options["season"]
    except:
        season = None
    (season, seasonN) = await getSeason(season, forceOutput=True)
    possible = []
    matched = []
    if len(ctx.options["opponent"]) > 1 and (ctx.options["opponent"][:2] == "\\k" or ctx.options["opponent"][:2] == "/k"):
        ctx.options["opponent"]
        possible = list(knownplayers.keys())
        for i in possible:
            if ctx.options["opponent"].lower() in i.lower() and len(matched) < 25:
                matched.append(i)
    else:
        lb = await mongoclient["b2"]["lb"].find_one({'season': season}, sort=[("date", -1)])
        possible = list(lb["namelist"])
        dontrepeat = []
        for i in range(len(possible)):
            if ctx.options["opponent"].lower() in possible[i].lower() and len(matched) < 25 and (not possible[i].lower() in dontrepeat):
                matched.append(possible[i])
                matcher = SequenceMatcher(None, possible[i].lower(), ctx.options["opponent"].lower())
                if matcher.quick_ratio() >= 0.75 and matcher.ratio() >= 0.75:
                    if not possible[i].lower() in dontrepeat:
                        dontrepeat.append(possible[i].lower())
                    matched.append('[#'+str(i+1)+'s'+str(seasonN)+'] '+possible[i])
    return matched

async def autocompleteSeason(ctx: discord.AutocompleteContext):
    matched = []
    slist = await getSList()
    for i in slist:
        if ctx.options['season'] in i and len(matched) < 25:
            matched.append(i)
    return matched

async def autocompleteTimezone(ctx: discord.AutocompleteContext):
    possible = zoneinfo.available_timezones()
    matched = []
    for i in possible:
        if ctx.options["timezone"].lower() in i.lower() and len(matched) < 25:
            matched.append(i)
    return matched

@bot.slash_command(name="ndaily", description="Show stat difference between now and n days (n*24h) ago (n dosen't need to be integer)", guild_ids=cmdguilds)
async def ndaily(ctx, n: discord.Option(float, "n", required = True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("ndaily")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*24*n
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="nhourly", description="Show stat difference between now and n days (n*24h) ago (n dosen't need to be integer)", guild_ids=cmdguilds)
async def nhourly(ctx, n: discord.Option(float, "n", required = True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("nhourly")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*n
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="24h", description="Show stat difference between now and one day (24h) ago", guild_ids=cmdguilds)
async def daily24h(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("24h")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*24
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="12h", description="Show stat difference between now and 12h (half a day) ago", guild_ids=cmdguilds)
async def halfdaily12h(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("12h")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()
    beg = end - 60*60*12
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="previous24h", description="Show stat difference between one day (24h) and two days (48h) ago", guild_ids=cmdguilds)
async def yesterday24h(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("prev24h")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    end = time.time()-60*60*24
    beg = end - 60*60*24*2
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="daily", description="Show stat difference between now and the last reset time point (set it with /link)", guild_ids=cmdguilds)
async def daily(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("daily")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="yesterday", description="Show stat difference between the last reset time point and 24h earlier (set it with /link)", guild_ids=cmdguilds)
async def yesterday(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("yesterday")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="weekly", description="Show stat difference between now and one week ago", guild_ids=cmdguilds)
async def weekly(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("weekly")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="delta", description="Show stat difference between beg and end (unix timestamps)", guild_ids=cmdguilds)
async def delta(ctx, begin_date: discord.Option(str, "the start of the time to consider", required=True), end_date: discord.Option(str, "the end of the time to consider", required=True), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("delta")
    if begin_date == None:
        beg = 1
    else:
        beg = await parseDate(begin_date, True)
        if beg == None:
            await ctx.followup.send("Error parsing begin date")
    if end_date == None:
        end = time.time()
    else:
        end = await parseDate(end_date, False)
        if end == None:
            await ctx.followup.send("Error parsing end date")
    if beg <= 1:
        beg = 1
    if end <= 1:
        end = 1
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="seasonal", description="Show stats for this season", guild_ids=cmdguilds)
async def seasonal(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), extended: discord.Option(bool, "extended", required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("seasonal")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
        await ctx.followup.send("Error, players oldest stats were not found (this might also mean the player wasn't in HoM in the chosen season)")
        return
    end = time.time()
    beg = time.mktime(old["date"].timetuple()) + old['date'].microsecond/1000000
    await deltastat(ctx, extended, usedeltasnotmatches, season, seasonN, playername, plid, beg, end)

@bot.slash_command(name="matchstat", description="Shows a summary of match data (no data about score or places)", guild_ids=cmdguilds)
async def matchstat(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), begin_date: discord.Option(str, "the start of the time to consider", required=False), end_date: discord.Option(str, "the end of the time to consider", required=False), forceside: discord.Option(str, "consider only matches played from chosed side", choices=["right", "left"], required=False), match_pool: discord.Option(str, "The match pool to get matches from", choices=["HoM", "unranked", "zomg"], required=False), usedeltasnotmatches: discord.Option(bool, "useDeltasNotMatches", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("matchstat")
    seasonNull = False
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if begin_date == None:
        beg = 1
    else:
        beg = await parseDate(begin_date, True)
        if beg == None:
            await ctx.followup.send("Error parsing begin date")
    if end_date == None:
        end = time.time()
    else:
        end = await parseDate(end_date, False)
        if end == None:
            await ctx.followup.send("Error parsing end date")
    if beg <= 1:
        beg = 1
    if end <= 1:
        end = 1
    if (beg > end):
        await ctx.followup.send("Time interval must begin earlier then it ends")
        return False
    matchdb = "matches"
    if match_pool == "unranked":
        matchdb = "umatches"
    elif match_pool == "zomg":
        matchdb = "zmatches"
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    bonusFilter = {}
    if not seasonNull:
        bonusFilter.update({"season": season})
    if forceside == "left":
        bonusFilter.update({"body.playerLeft.profileURL": plid})
    elif forceside == "right":
        bonusFilter.update({"body.playerRight.profileURL": plid})
    # draws
    draws = await countmatches(1, bonusFilter, {"winner": "draw", "loser": "draw", "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}, matchdb=matchdb)
    # full draws (without counting opponentLobbyDC)
    drawsFull = await countmatches(1, bonusFilter, {"body.playerRight.result": 'draw', "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}, matchdb=matchdb)
    # wins
    wins = await countmatches(1, bonusFilter, {"winner": plid, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}, matchdb=matchdb)
    # losses
    losses = await countmatches(1, bonusFilter, {"loser": plid, "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}, matchdb=matchdb)
    # playtime
    playtime = await countmatches("$body.duration", bonusFilter, {"$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}], "date": {"$lte": datetime.datetime.utcfromtimestamp(end+1), "$gte": datetime.datetime.utcfromtimestamp(beg-1)}}, matchdb=matchdb)
    # make the image
    profile = await getPlayer(plid, season, seasonNull=seasonNull)
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    im = await imagegen.genMatchStatImage(profile, wins, losses, draws, drawsFull, playtime, lbsize, seasonN)
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'WEBP', quality=90)
        imbytes.seek(0)
        msgtext = "Match stats from <t:"+str(int(beg))+":f> to <t:"+str(int(end))+":f>"
        if beg < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
        await ctx.interaction.edit_original_response(content=msgtext, file=discord.File(fp=imbytes, filename='image.webp'))
        return True

@bot.slash_command(name="seasoninfo", description="Show some info about the chosen season", guild_ids=cmdguilds)
async def seasoninfo(ctx, season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("seasoninfo")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
    await updateUsagestat("scanstatus")
    (season, seasonN) = await getSeason(None, getCurrent=True)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
async def vs(ctx, opponent: discord.Option(str, "opponent", required = True, autocomplete=autocompletePname_opponent), ndaily: discord.Option(str, "n last days are taken into consideration", required=False), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("vs")
    # "date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if (not ndaily == None) and (ndaily != 0):
        cutoffdate = max(1, await parseDate(ndaily))
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
        await ctx.followup.send("Player (main) not found (this might also mean the player wasn't in HoM in the chosen season)")
        return
    if profileo == None:
        await ctx.followup.send("Player (opponent) not found (this might also mean the opponent wasn't in HoM in the chosen season)")
        return
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    im = await imagegen.genVs(profile, profileo, wins, winso, draws, lbsize, seasonN)
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'WEBP', quality=90)
        imbytes.seek(0)
        msgtext = ""
        daysTillCutoff = int(time.time()-cutoffdate)/3600/24
        if seasonNull:
            if ndaily == 0:
                msgtext = f"Wins/losses for the last a lot of days"
            else:
                msgtext = f"Wins/losses for the last {daysTillCutoff:g} days"
            if cutoffdate < 1701961220: # season 16 start
                msgtext += " (the bot doesn't see anything earlier than season 16)"
        elif not ndaily == None:
            if ndaily == 0:
                msgtext = f"Wins/losses for the whole season {seasonN}"
            else:
                msgtext = f"Wins/losses for season {seasonN} for the last {daysTillCutoff:g} days"
            if cutoffdate < 1701961220: # season 16 start
                msgtext += " (the bot doesn't see anything earlier than season 16)"
        else:
            msgtext = f"Wins/losses for season {seasonN}"
        await ctx.interaction.edit_original_response(content=msgtext,
            file=discord.File(fp=imbytes, filename='image.webp'))
        return True

@bot.slash_command(name="_eloexp", description="runs HoM match database through an alternate elo system", guild_ids=cmdguilds)
async def eloexp(ctx, mode: discord.Option(str, "type", choices=['elo', 'elo capped', 'jake continuous', 'accuracy'], required=True), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), ndaily: discord.Option(str, "n last days are taken into consideration", required=False), k: discord.Option(int, "k", required=False), b: discord.Option(int, "b", required=False), i: discord.Option(int, "i", required=False), cap: discord.Option(int, "cap", required=False), start: discord.Option(int, "start", required=False)):
    await ctx.defer()
    await updateUsagestat("eloexp")
    if k == None:
        k = 32
    if b == None:
        b = 10
        if 'jake' in mode:
            b = 2
    if i == None:
        i = 400
        if 'jake' in mode:
            i = 1000
    if start == None:
        if 'jake' in mode:
            start = 3500
        elif mode == 'accuracy':
            start = 3500
        else:
            start = 1500
    if cap == None:
        cap = 400
        if 'jake' in mode:
            cap = 100
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if (not ndaily == None) and (ndaily != 0):
        cutoffdate = max(1, await parseDate(ndaily))
        #if cutoffdate < time.time()-3600*24*100:
        #    await ctx.followup.send("To avoid lag the bot refuses to calculate eloexp with ndaily > 100")
        #    return
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    lb = await mongoclient["b2"]["lb"].find_one({"season": season}, sort=[("date", -1)])
    if lb == None:
        await ctx.followup.send(f"Error occured while getting a leaderboard (wait a few minutes and try again)")
        return None
    lbsize = lb["lbsize"]
    lblist = []
    lblist = await lbutil.eloexperiment(mongoclient, season, seasonNull, cutoffdate, lb, mode, k, i, b, cap, start)
    view = LbView(ctx, lblist, lbsize, "eloexp", f"eloexp ({mode})", seasonN, 8, 0, 0, 2147483647)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="_nukelb", description="estimated elo transfer leaderboard (ignores draws, uses new formulas)", guild_ids=cmdguilds)
async def nukelb(ctx, mode: discord.Option(str, "type", choices=['total', 'loss', 'gain', 'total_abs'], required=True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), ndaily: discord.Option(str, "n last days are taken into consideration", required=False)):
    await ctx.defer()
    await updateUsagestat("nukelb")
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if (not ndaily == None) and (ndaily != 0):
        cutoffdate = max(1, await parseDate(ndaily))
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    matchlist = []
    profile = await getPlayer(plid, season)
    if profile == None:
        await ctx.followup.send("Error, player's stats were not found (this might also mean the player wasn't in HoM in the chosen season)")
        return
    pname = profile["body"]["displayName"]
    if seasonNull:
        matchlist = mongoclient["b2"]["matches"].find({'date': {'$gte': datetime.datetime.utcfromtimestamp(cutoffdate)}, "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}]}, sort=[("date", -1)])
    else:
        matchlist = mongoclient["b2"]["matches"].find({"season": season, 'date': {'$gte': datetime.datetime.utcfromtimestamp(cutoffdate)}, "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}]}, sort=[("date", -1)])
    nukelb = {plid : 0}
    oldlb = None
    async for m in matchlist:    
        if oldlb is None or oldlb["date"] != m["date"]:
            if seasonNull:
                oldlb = await mongoclient["b2"]["lb"].find_one({"date": {"$gte": m["date"]}}, sort=[("date", -1)])
            else:
                oldlb = await mongoclient["b2"]["lb"].find_one({"season": season, "date": {"$gte": m["date"]}}, sort=[("date", -1)])
            # if still none use newest lb
            if oldlb == None:
                oldlb = await mongoclient["b2"]["lb"].find_one({}, sort=[("date", -1)])
                # if still none just give up this iteration
                if oldlb == None:
                    continue
        winsc, losesc = 0, 0
        for i in oldlb["lb"]:
            if i["profile"] == m["winner"]:
                winsc = i["score"]
            if i["profile"] == m["loser"]:
                losesc = i["score"]
        if m["winner"] == plid:
            if not m["loser"] in nukelb:
                nukelb[m["loser"]] = 0      
            mygain = min(max(50 + (losesc - winsc)/150, 5), 100)
            if mode in ('total', 'gain', 'total_abs'):
                nukelb[m["loser"]] += mygain
        elif m["loser"] == plid:
            if not m["winner"] in nukelb:
                nukelb[m["winner"]] = 0  
            myloss = -min(max(50 + (losesc - winsc)/150, 5), 95)
            if mode in ('total', 'loss'):
                nukelb[m["winner"]] += myloss
            if mode == 'total_abs':
                nukelb[m["winner"]] += abs(myloss)

    lblist = []
    for i in nukelb:
        try:
            tmp = await mongoclient["b2"]["players"].find_one({"plid": i}, sort=[("date", -1)])
            if not tmp['season'] == season:
                tmp['hidescore'] = True
            tmp["__lbprop"] = nukelb[i]
            tmp["__lbsort"] = tmp["__lbprop"]
            lblist.append(tmp)
        except:
            pass
    revsort = mode != 'loss'
    lblist = sorted(lblist, key=lambda d: d['__lbsort'], reverse=revsort)
    for index, i in enumerate(lblist, 1):
        i["__lbplace"] = index
    for i in range(1, len(lblist)):
        if lblist[i]["__lbsort"] == lblist[i-1]["__lbsort"]:
            lblist[i]["__lbplace"] = lblist[i-1]["__lbplace"]
    if len(lblist) == 0:
        await ctx.interaction.edit_original_response(content=f"The selected leaderboard is empty")
        return
    vsname = await mongoclient['b2']['players'].find_one({'plid': plid}, sort=[('date', -1)])
    if vsname == None:
        vsname = "<no name found>"
    else:
        vsname = vsname['body']['displayName']

    msgtext = ""
    daysTillCutoff = int(time.time()-cutoffdate)/3600/24
    if seasonNull:
        if ndaily == 0:
            msgtext = f"score transfers to {vsname} (counting {mode}) for the last a lot of days"
        else:
            msgtext = f"score transfers to {vsname} (counting {mode}) for the last {daysTillCutoff:g} days"
        if cutoffdate < 1723802400: # season 16 start
            msgtext += " (THIS USES FRONG FORMULAS FOR S21 AND EARLIER)"
    elif not ndaily == None:
        if ndaily == 0:
            msgtext = f"score transfers to {vsname} (counting {mode}) for whole season {seasonN}"
        else:
            msgtext = f"score transfers to {vsname} (counting {mode}) for season {seasonN} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1723802400: # season 16 start
            msgtext += " (THIS USES FRONG FORMULAS FOR S21 AND EARLIER)"
    else:
        msgtext = f"{mode} against {vsname} for season {seasonN}"
    view = LbView(ctx, lblist, 1, "nukelb", msgtext, seasonN, 8, 0, 0, 2147483647)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)


@bot.slash_command(name="lb", description="Shown leaderboards of selected stat", guild_ids=cmdguilds)
async def lb(ctx, mode: discord.Option(str, "type", choices=['score', 'wins', 'losses', 'winrate', 'loserate', 'w/l', 'l/w', 'playtime', 'draws+DCs', 'games played', 'avg match duration', 'score gained'], required=True), min_games: discord.Option(int, "min games", required=False), min_score: discord.Option(int, "min score", required=False), max_score: discord.Option(int, "max score", required=False), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), ndaily: discord.Option(str, "n last days are taken into consideration", required=False)):
    await ctx.defer()
    await updateUsagestat("lb")
    if min_games == None:
        min_games = 0
    if min_score == None:
        min_score = 0
    if max_score == None:
        max_score = 2147483647
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if (not ndaily == None) and (ndaily != 0):
        cutoffdate = max(1, await parseDate(ndaily))
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
            mglist = await lbutil.getlb(mongoclient, season, False, 1, "score", min_games, min_score, max_score, lb)
            for i in range(len(mglist)):
                mglist[i] = mglist[i]["plid"]
            for i in lblist:
                if i["plid"] in mglist:
                    newlist.append(i)
            lblist = newlist
    elif mode == 'score gained':
        #if (min_score != 0 or max_score != 2147483647) and seasonNull:
        #    await ctx.followup.send("Min score and max score is not supported in multiseasonal mode")
        #    return
        slist = await mongoclient["sutil"]["slist"].find({}).to_list(length=None)
        ulbl = []
        for i in slist:
            ulb = await mongoclient["b2"]["lb"].find_one({"season": i["_id"]}, sort=[("date", -1)])
            if ulb == None:
                continue
            if cutoffdate <= i["end"]//1000:
                ulbl.append(ulb)
        lbdict = {}
        tofilter = []
        for ii in ulbl:
            for i in ii['lb']:
                if not i['profile'] in lbdict:
                    lbdict[i['profile']] = 0
                if (i['score'] > max_score) or (i['score'] < min_score):
                    tofilter.append(i['profile'])
                lbdict[i['profile']] += i['score']-3500
        nlb = await mongoclient['b2']['lb'].find_one({'date': {'$lte': datetime.datetime.utcfromtimestamp(cutoffdate)}}, sort=[('date', -1)])
        if nlb != None:
            for i in nlb['lb']:
                if i['profile'] in lbdict:
                    lbdict[i['profile']] += 3500-i['score']
        for i in lbdict.keys():
            if i in tofilter:
                continue
            tmp = await getPlayer(i, season, seasonNull)
            #if tmp == None:
            #    print(i, flush=True)
            if (seasonNull==False) and ((tmp["score"]<min_score) or (tmp["score"]>max_score)):
                continue
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
        lblist = await lbutil.getlb(mongoclient, season, seasonNull, cutoffdate, mode, min_games, min_score, max_score, lb)
    msgtext = ""
    passedSeasonN = None
    daysTillCutoff = int(time.time()-cutoffdate)/3600/24
    if seasonNull:
        if ndaily == 0:
            msgtext = f"{mode} for the last a lot of days"
        else:
            msgtext = f"{mode} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    elif not ndaily == None:
        passedSeasonN = seasonN
        if ndaily == 0:
            msgtext = f"{mode} for the whole season {seasonN}"
        else:
            msgtext = f"{mode} for season {seasonN} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    else:
        passedSeasonN = seasonN
        msgtext = f"{mode} for season {seasonN}"
    if len(lblist) == 0:
        await ctx.interaction.edit_original_response(content=f"The selected leaderboard ({mode} with {min_games} min games) is empty, you can try selecting lower min games")
        return
    view = LbView(ctx, lblist, lbsize, mode, msgtext, passedSeasonN, 8, min_games, min_score, max_score)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="vs_lb", description="Shows a leaderboard of who you won/lost agains the most", guild_ids=cmdguilds)
async def vslb(ctx, mode: discord.Option(str, "type", choices=['wins against player', 'losses against player', 'winrate against player', 'loserate against player', 'w/l against player', 'l/w against player', 'games played against player'], required=True), playername: discord.Option(str, "playername", required=False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), min_score: discord.Option(int, "min score", required=False), max_score: discord.Option(int, "max score", required=False), min_games: discord.Option(int, "min games", required=False), ndaily: discord.Option(str, "n last days are taken into consideration", required=False)):
    await ctx.defer()
    await updateUsagestat("vslb")
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if (not ndaily == None) and (ndaily != 0):
        cutoffdate = max(1, await parseDate(ndaily))
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    if not seasonNull and playername != None and playername[:2] == "\\m":
        seasonNull = True
    if min_games == None:
        min_games = 0
    if min_score == None:
        min_score = 0
    if max_score == None:
        max_score = 2147483647
    if mode == "wins against player":
        mode= "wins"
    if mode == "losses against player":
        mode = "losses"
    if mode == "winrate against player":
        mode = "winrate"
    if mode == "loserate against player":
        mode = "loserate"
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
    lblist = await lbutil.getlbvs(mongoclient, season, seasonNull, cutoffdate, mode, min_games, min_score, max_score, lb, plid)
    if len(lblist) == 0:
        await ctx.interaction.edit_original_response(content=f"The selected leaderboard is empty")
        return
    msgtext = ""
    daysTillCutoff = int(time.time()-cutoffdate)/3600/24
    if seasonNull:
        if ndaily == 0:
            msgtext = f"{mode} against {vsname} for the last a lot of days"
        else:
            msgtext = f"{mode} against {vsname} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    elif not ndaily == None:
        if ndaily == 0:
            msgtext = f"{mode} against {vsname} for whole season {seasonN}"
        else:
            msgtext = f"{mode} against {vsname} for season {seasonN} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    else:
        msgtext = f"{mode} against {vsname} for season {seasonN}"
    view = LbView(ctx, lblist, lbsize, mode, msgtext, None, 8, min_games, min_score, max_score)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="link", description="Links B2 account to discord so you can type less", guild_ids=cmdguilds)
async def link(ctx, playername: discord.Option(str, "playername", required=False, autocomplete=autocompletePname), timezone: discord.Option(str, "timezone", required=False, autocomplete=autocompleteTimezone), reset_hour: discord.Option(int, "reset hour (24h format, without minutes)", required=False)):
    await ctx.defer(ephemeral=True)
    await updateUsagestat("link")
    if playername == None and timezone == None:
        await ctx.followup.send("You need to provide some arguments for /link to make sense", ephemeral=True)
    plid = None
    midnight = None
    if playername != None:
        (season, seasonN) = await getSeason(None, getCurrent=True)
        plid = await choosePlayer(ctx, season, seasonN, playername)
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
    await updateUsagestat("unlink")
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
async def namehistory(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), include_medals: discord.Option(bool, "does a change in badges equipped constitute a new profile", required=False), multiseasonal: discord.Option(bool, "should the namelist go through all recorded season", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("namehist")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
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
    if multiseasonal == None or multiseasonal == True:
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
    view = NamehistView(ctx, pastprofiles, 0, "namehistory", pastprofiles[0]['body']['displayName'], seasonN, 8, 0, 0, 2147483647)
    await view.init()
    if await view.wait():
        await ctx.interaction.edit_original_response(content=f"Timed out! [{view.infostring}]", view=None)

@bot.slash_command(name="exportmatches", description="get a txt file with the player's matches", guild_ids=cmdguilds)
async def exportmatches(ctx, fileformat: discord.Option(str, "type", choices=['csv', 'json-nk'], required=True), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason), ndaily: discord.Option(str, "n last days are taken into consideration", required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("exportmatches")
    seasonNull = False
    cutoffdate = 1
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if (not ndaily == None) and (ndaily != 0):
        cutoffdate = max(1, await parseDate(ndaily))
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    if not seasonNull and playername != None and playername[:2] == "\\m":
        seasonNull = True
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    matchlist = []
    profile = await getPlayer(plid, season, seasonNull)
    if profile == None:
        await ctx.followup.send("Error, player's stats were not found (this might also mean the player wasn't in HoM in the chosen season)")
        return
    pname = profile["body"]["displayName"]
    if seasonNull:
        matchlist = await mongoclient["b2"]["matches"].find({"date": {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}]}, sort=[("date", -1)]).to_list(length=None)
    else:
        matchlist = await mongoclient["b2"]["matches"].find({"season": season, "$or": [{"body.playerRight.profileURL": plid}, {"body.playerLeft.profileURL": plid}]}, sort=[("date", -1)]).to_list(length=None)
    # convert names of maps to the newer versions (some maps changed names in the api)
    mapNameMap = {
        "mayan_map_01": "mayan",
        "le_ruins": "castle_ruins",
        "building_site_scene": "building_site",
        "bloon_bot_factory": "bot_factory",
        "banana_depot_scene": "banana_depot",
        "off_tide": "offtide",
        "salmon_pool": "salmon_ladder"
    }
    for i in matchlist:
        if i["body"]["map"] in mapNameMap:
            i["body"]["map"] = mapNameMap[i["body"]["map"]]
    if fileformat == 'csv':
        outstr = 'id;side;1;map;endRound;duration;win;hero;towerone;towertwo;towerthree\n'
        for i in matchlist:
            if i["body"]["playerLeft"]["profileURL"] == plid:
                outstr += f'''{i['_id']};left;1;{i['body']['map']};{i['body']['endRound']};{i['body']['duration']};{int(i['body']['playerLeft']['result']=='win')};{i['body']['playerLeft']['hero']};{i['body']['playerLeft']['towerone']};{i['body']['playerLeft']['towertwo']};{i['body']['playerLeft']['towerthree']}\n'''
            if i["body"]["playerRight"]["profileURL"] == plid:
                outstr += f'''{i['_id']};right;1;{i['body']['map']};{i['body']['endRound']};{i['body']['duration']};{int(i['body']['playerRight']['result']=='win')};{i['body']['playerRight']['hero']};{i['body']['playerRight']['towerone']};{i['body']['playerRight']['towertwo']};{i['body']['playerRight']['towerthree']}\n'''
    elif fileformat == 'json-nk':
        outstr = '{"body":['
        res = []
        for i in matchlist:
            leftcurrent = i['body']['playerLeft']['profileURL'] == plid
            i['body']['playerLeft']['currentUser'] = leftcurrent
            i['body']['playerRight']['currentUser'] = not leftcurrent
            outstr += json.dumps(i["body"])
            outstr += ","
        outstr = outstr[:-1]
        outstr += ']}'
    daysTillCutoff = int(time.time()-cutoffdate)/3600/24
    if seasonNull:
        if ndaily == 0:
            msgtext = f"Matches exported for {pname}"
        else:
            msgtext = f"Matches exported for {pname} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    elif not ndaily == None:
        if ndaily == 0:
            msgtext = f"Matches exported for {pname} for whole season {seasonN}"
        else:
            msgtext = f"Matches exported for {pname} for season {seasonN} for the last {daysTillCutoff:g} days"
        if cutoffdate < 1701961220: # season 16 start
            msgtext += " (the bot doesn't see anything earlier than season 16)"
    else:
        msgtext = f"Matches exported for {pname} for season {seasonN}"
    filename = f"matches-{plid[42:]}"
    if fileformat == 'csv':
        filename += ".txt"
    elif fileformat == 'json-nk':
        filename += ".json"
    with io.BytesIO() as filebytes:
        filebytes.write(bytes(outstr, 'ascii'))
        filebytes.seek(0)
        await ctx.interaction.edit_original_response(content=msgtext,
            file=discord.File(fp=filebytes, filename=filename))
        return True

@bot.slash_command(name="b2lol", description="get link for player's b2.lol page", guild_ids=cmdguilds)
async def b2lol_link(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("b2lol")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    await ctx.interaction.edit_original_response(content=f"https://b2.lol/playerInfo/playerInfo.html?{plid[42:]}")

@bot.slash_command(name="b2la", description="testing", guild_ids=cmdguilds)
async def b2la_link(ctx, season: discord.Option(str, "season", required=True, autocomplete=autocompleteSeason), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("b2la")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    await ctx.interaction.edit_original_response(content=f"https://b2la.netlify.app/matchviewer/matches?{season}.{plid[42:]}")

@bot.slash_command(name="plid", description="get player's api url (used as player id internally)", guild_ids=cmdguilds)
async def plid(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname),  season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("plid")
    (season, seasonN) = await getSeason(season, ctx=ctx)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
    await ctx.interaction.edit_original_response(content=plid)

@bot.slash_command(name="towerstats", description="Shows inforamtion about tower usage and win rates", guild_ids=cmdguilds)
async def towerstats(ctx, mode: discord.Option(str, "what to count in the matches", choices=['hero', 'tower', 'strat', 'strat+hero', 'map'], required=True), season: discord.Option(str, "season", required=False, autocomplete=autocompleteSeason),  fileformat: discord.Option(str, "file format", choices=['csv', 'asciitable'], required=False), begin_date: discord.Option(str, "the start of the time to consider", required=False), end_date: discord.Option(str, "the end of the time to consider", required=False), playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), sortmode: discord.Option(str, "which field to sort by", choices=['uses/userate', 'winrate', 'wins'], required=False)):
    await ctx.defer(ephemeral=False)
    await updateUsagestat("towerstat")
    seasonNull = False
    if (season == None) and (not ndaily == None):
        seasonNull = True
    if begin_date == None:
        beg = 1
    else:
        beg = await parseDate(begin_date, True)
        if beg == None:
            await ctx.followup.send("Error parsing begin date")
    if end_date == None:
        end = time.time()
    else:
        end = await parseDate(end_date, False)
        if end == None:
            await ctx.followup.send("Error parsing end date")
    if beg <= 1:
        beg = 1
    if end <= 1:
        end = 1
    if (beg > end):
        await ctx.followup.send("Time interval must begin earlier then it ends")
        return False
    (season, seasonN) = await getSeason(season, ctx=ctx, getCurrent=seasonNull)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plidFilter = None
    if playername != None:
        plidFilter = await choosePlayer(ctx, season, seasonN, playername)
    if fileformat == None:
        fileformat = "csv"
    matchlist = await towerstat.getMatchlist(mongoclient, beg, end, season, seasonNull, plidFilter)
    if mode == 'hero':
        res = await towerstat.getHeroStats(matchlist, plidFilter)
    if mode == 'tower':
        res = await towerstat.getTowerStats(matchlist, plidFilter)
    if mode == 'strat':
        res = await towerstat.getStratStats(matchlist, plidFilter)
    if mode == 'strat+hero':
        res = await towerstat.getHeroStratStats(matchlist, plidFilter)
    if mode == 'map':
        res = await towerstat.getMapStats(matchlist, plidFilter)
    res = await towerstat.normalizeStats(res, sortmode)
    string = ""
    if fileformat == "csv":
        string = await towerstat.makeCSV(res)
        with io.BytesIO() as filebytes:
            filebytes.write(bytes(string, 'ascii'))
            filebytes.seek(0)
            await ctx.interaction.edit_original_response(content=f"",
                file=discord.File(fp=filebytes, filename="towerstat.txt"))
            return True
    elif fileformat == "asciitable":
        string = await towerstat.makeAsciiTable(res)
        await ctx.interaction.edit_original_response(content=string)
        return True

@bot.slash_command(name="rpr", description="render profile image", guild_ids=cmdguilds)
async def rpr(ctx, playername: discord.Option(str, "playername", required = False, autocomplete=autocompletePname), no_medals: discord.Option(bool, "hide player's medals from image", required = False), no_score: discord.Option(bool, "hide player's score from image", required = False), fake_score: discord.Option(int, "make player look like they have x score", required = False), fake_place: discord.Option(int, "make player look like they are nth on the lb", required = False)):
    (season, seasonN) = await getSeason(None, getCurrent=True)
    if season == None:
        await ctx.followup.send("Error getting season")
        return
    plid = None
    if playername == None:
        plid = await mongoclient["dc"]["links"].find_one({"dcid": ctx.author.id})
        if plid == None:
            await ctx.followup.send("You need to provide a playername as an input or link your discord account to Battles 2 name (/link) [the bot works only on HoM players]")
            return
        plid = plid["b2plid"]
    else:
        plid = await choosePlayer(ctx, season, seasonN, playername)
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
    im = await imagegen.genLBEImage(player, lbsize, seasonN)
    with io.BytesIO() as imbytes:
        im.save(imbytes, 'WEBP', quality=90, exact=True)
        imbytes.seek(0)
        await ctx.respond(file=discord.File(fp=imbytes, filename='image.webp'))

@bot.listen()
async def on_reaction_add(reaction, user):
    if (reaction.message.interaction_metadata == None) or (reaction.message.interaction_metadata.user.id != user.id):
        return
    if reaction.emoji == "❌" and (datetime.datetime.now(datetime.timezone.utc)-reaction.message.created_at).total_seconds() < 180:
        await reaction.message.delete()

if __name__ == "__main__":
    TOKEN = os.getenv("DC_TOKEN")
    bot.run(TOKEN)

