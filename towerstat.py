
from collections import defaultdict
import datetime

def getStratName(mside, includeHero):
    sortedStrat = sorted((mside['towerone'], mside['towertwo'], mside['towerthree']))
    res = sortedStrat[0]+", "+sortedStrat[1]+", "+sortedStrat[2]
    if includeHero:
        res = mside['hero']+", "+res
    return res

async def getMatchlist(mongoclient, beg, end, season, seasonNull, plidFilter):
    filterdict = {"date": {"$lte": datetime.datetime.utcfromtimestamp(end), "$gte": datetime.datetime.utcfromtimestamp(beg)}}
    if not seasonNull:
        filterdict["season"] = season
    if plidFilter != None:
        filterdict["$or"] = [{"body.playerRight.profileURL": plidFilter}, {"body.playerLeft.profileURL": plidFilter}]
    matchlist = mongoclient["b2"]["matches"].aggregate([
        {"$match": filterdict}
    ])
    return matchlist

async def getHeroStats(matchlist, plidFilter):
    uses = defaultdict(lambda: 0)
    totalUses = 0
    wins = defaultdict(lambda: 0)
    async for i in matchlist:
        if plidFilter == None or i['body']['playerLeft']['profileURL'] == plidFilter:
            uses[i['body']['playerLeft']['hero']] += 1
            if i['body']['playerLeft']['result'] == "win":
                wins[i['body']['playerLeft']['hero']] += 1
            totalUses += 1

        if plidFilter == None or i['body']['playerRight']['profileURL'] == plidFilter:
            uses[i['body']['playerRight']['hero']] += 1
            if i['body']['playerRight']['result'] == "win":
                wins[i['body']['playerRight']['hero']] += 1
            totalUses += 1
    return (uses, totalUses, wins)

async def getTowerStats(matchlist, plidFilter):
    uses = defaultdict(lambda: 0)
    totalUses = 0
    wins = defaultdict(lambda: 0)
    async for i in matchlist:
        if plidFilter == None or i['body']['playerLeft']['profileURL'] == plidFilter:
            uses[i['body']['playerLeft']['towerone']] += 1
            uses[i['body']['playerLeft']['towertwo']] += 1
            uses[i['body']['playerLeft']['towerthree']] += 1
            if i['body']['playerLeft']['result'] == "win":
                wins[i['body']['playerLeft']['towerone']] += 1
                wins[i['body']['playerLeft']['towertwo']] += 1
                wins[i['body']['playerLeft']['towerthree']] += 1
            totalUses += 1

        if plidFilter == None or i['body']['playerRight']['profileURL'] == plidFilter:
            uses[i['body']['playerRight']['towerone']] += 1
            uses[i['body']['playerRight']['towertwo']] += 1
            uses[i['body']['playerRight']['towerthree']] += 1
            if i['body']['playerRight']['result'] == "win":
                wins[i['body']['playerRight']['towerone']] += 1
                wins[i['body']['playerRight']['towertwo']] += 1
                wins[i['body']['playerRight']['towerthree']] += 1
            totalUses += 1
    return (uses, totalUses, wins)

async def getStratStats(matchlist, plidFilter):
    uses = defaultdict(lambda: 0)
    totalUses = 0
    wins = defaultdict(lambda: 0)
    async for i in matchlist:
        if plidFilter == None or i['body']['playerLeft']['profileURL'] == plidFilter:
            uses[getStratName(i['body']['playerLeft'], False)] += 1
            if i['body']['playerLeft']['result'] == "win":
                wins[getStratName(i['body']['playerLeft'], False)] += 1
            totalUses += 1

        if plidFilter == None or i['body']['playerRight']['profileURL'] == plidFilter:
            uses[getStratName(i['body']['playerRight'], False)] += 1
            if i['body']['playerRight']['result'] == "win":
                wins[getStratName(i['body']['playerRight'], False)] += 1
            totalUses += 1
    return (uses, totalUses, wins)

async def getHeroStratStats(matchlist, plidFilter):
    uses = defaultdict(lambda: 0)
    totalUses = 0
    wins = defaultdict(lambda: 0)
    async for i in matchlist:
        if plidFilter == None or i['body']['playerLeft']['profileURL'] == plidFilter:
            uses[getStratName(i['body']['playerLeft'], True)] += 1
            if i['body']['playerLeft']['result'] == "win":
                wins[getStratName(i['body']['playerLeft'], True)] += 1
            totalUses += 1

        if plidFilter == None or i['body']['playerRight']['profileURL'] == plidFilter:
            uses[getStratName(i['body']['playerRight'], True)] += 1
            if i['body']['playerRight']['result'] == "win":
                wins[getStratName(i['body']['playerRight'], True)] += 1
            totalUses += 1
    return (uses, totalUses, wins)

async def getMapStats(matchlist, plidFilter):
    uses = defaultdict(lambda: 0)
    totalUses = 0
    wins = defaultdict(lambda: 0)
    async for i in matchlist:
        if plidFilter == None or i['body']['playerLeft']['profileURL'] == plidFilter:
            uses[i['body']['map']] += 1
            if i['body']['playerLeft']['result'] == "win":
                wins[i['body']['map']] += 1
            totalUses += 1

        if plidFilter == None or i['body']['playerRight']['profileURL'] == plidFilter:
            uses[i['body']['map']] += 1
            if i['body']['playerRight']['result'] == "win":
                wins[i['body']['map']] += 1
            totalUses += 1
    return (uses, totalUses, wins)

async def normalizeStats(stats, sortmode):
    # [(uses, userate, wins, winrate), ...]
    uses = stats[0]
    totalUses = stats[1]
    wins = stats[2]
    res = []
    for i in uses.keys():
        res.append((i, uses[i], round(uses[i]/totalUses*100, 2), wins[i], round(wins[i]/uses[i]*100, 2)))
    if sortmode == 'wins':
        res.sort(key=lambda x: x[3], reverse=True)
    elif sortmode == 'winrate':
        res.sort(key=lambda x: x[4], reverse=True)
    else: # we want to sort by userate by default ('uses/userate')
        res.sort(key=lambda x: x[1], reverse=True)
    # they changed the names of some heroes over time so we have to add them up
    heroNameMap = {
        "Agent_Jericho": "Jericho",
        "Highwayman_Jericho":  "Jericho_Highwayman"
    }
    for i in heroNameMap.keys():
        if i in res:
            res[heroNameMap[i]] += res[i]
            del res[i]
    return res

def makeCenteredTableCell(text, textlen, mcl):
    return '|'+' '*((mcl-textlen)//2)+text+' '*(mcl-textlen-((mcl-textlen)//2))

async def makeAsciiTable(nstats):
    longestlen = [0 for j in nstats[0]]
    for i in nstats:
        for j in range(len(longestlen)):
            longestlen[j] = max(longestlen[j], len(str(i[j])))
    longestlen[2] += 1
    longestlen[4] += 1
    longestlen[0] = max(longestlen[0], 4)
    longestlen[1] = max(longestlen[1], 4)
    longestlen[2] = max(longestlen[2], 2)
    longestlen[3] = max(longestlen[3], 4)
    longestlen[4] = max(longestlen[4], 2)
    linelength = longestlen[0]+longestlen[1]+longestlen[2]+longestlen[3]+longestlen[4]+6

    string = '```\n'
    string += makeCenteredTableCell('name', 4, longestlen[0])
    string += makeCenteredTableCell('uses', 4, longestlen[1])
    string += makeCenteredTableCell('ur', 2, longestlen[2])
    string += makeCenteredTableCell('wins', 4, longestlen[3])
    string += makeCenteredTableCell('wr', 2, longestlen[4])
    string += '|\n'
    for i in nstats:
        if (len(string)+linelength+linelength+2) >= 2000-4:
            string += makeCenteredTableCell('<TABLE NOT COMPLETE>', 20, linelength-2)+'|\n'
            break
        string += makeCenteredTableCell(str(i[0]), len(str(i[0])), longestlen[0])
        string += makeCenteredTableCell(str(i[1]), len(str(i[1])), longestlen[1])
        string += makeCenteredTableCell(str(i[2])+'%', len(str(i[2]))+1, longestlen[2])
        string += makeCenteredTableCell(str(i[3]), len(str(i[3])), longestlen[3])
        string += makeCenteredTableCell(str(i[4])+'%', len(str(i[4]))+1, longestlen[4])
        string += '|\n'
    string += '```'
    return string

async def makeCSV(nstats):
    string = 'name;uses;userate;wins;winrate\n'
    for i in nstats:
        string += str(i[0])+";"+str(i[1])+";"+str(i[2])+";"+str(i[3])+";"+str(i[4])+"\n"
    return string
