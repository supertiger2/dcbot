import pymongo

def getlbprop(mode, plrentry):
    if mode == 'score':
        return 1
    if mode == 'wins':
        return plrentry['w']
    if mode == 'losses':
        return plrentry['l']
    if mode == 'draws+DCs':
        return plrentry['d']
    if mode == 'games played':
        return plrentry['w']+plrentry['l']+plrentry['d']
    if mode == 'winrate':
        if (plrentry['w']+plrentry['l']) == 0:
            return 0
        return plrentry['w']/(plrentry['w']+plrentry['l'])
    if mode == 'loserate':
        if (plrentry['w']+plrentry['l']+plrentry['d']) == 0:
            return 0
        return plrentry['l']/(plrentry['w']+plrentry['l']+plrentry['d'])
    if mode == 'w/l':
        return plrentry['w']/max(1, plrentry['l'])
    if mode == 'l/w':
        return plrentry['l']/max(1, plrentry['w'])
    if mode == 'playtime':
        return plrentry['pt']
    if mode == 'avg match duration':
        return plrentry['pt']/(plrentry['w']+plrentry['l']+plrentry['d'])

async def getlb(mongoclient, season, seasonNull, cutoffdate, mode, mingames, minscore, maxscore, lb):
    #matches = await mongoclient['b2']['matches'].find({'season': season}).to_list(length=None)
    if seasonNull:
        matches = mongoclient["b2"]["matches"].aggregate([
            {"$match": {'date': {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}}
        ])
    else:
        matches = mongoclient["b2"]["matches"].aggregate([
            {"$match": {'season': season, 'date': {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}}
        ])
    currlb = []
    for i in lb['lb']:
        currlb.append(i['profile'])
    playermap = []
    plidtoint = {}
    pticc = 0
    async for i in matches:
        if not i['body']['playerLeft']['profileURL'] in plidtoint:
            playermap.append({'w': 0, 'l': 0, 'd': 0, 'pt': 0})
            plidtoint[i['body']['playerLeft']['profileURL']] = pticc
            pticc += 1
        if not i['body']['playerRight']['profileURL'] in plidtoint:
            playermap.append({'w': 0, 'l': 0, 'd': 0, 'pt': 0})
            plidtoint[i['body']['playerRight']['profileURL']] = pticc
            pticc += 1
        if i['winner'] == 'draw':
            playermap[plidtoint[i['body']['playerLeft']['profileURL']]]['d'] += 1
            playermap[plidtoint[i['body']['playerRight']['profileURL']]]['d'] += 1
        else:
            playermap[plidtoint[i['winner']]]['w'] += 1
            playermap[plidtoint[i['loser']]]['l'] += 1
        playermap[plidtoint[i['body']['playerLeft']['profileURL']]]['pt'] += i['body']['duration']
        playermap[plidtoint[i['body']['playerRight']['profileURL']]]['pt'] += i['body']['duration']
    lblist = []
    for j in plidtoint.keys():
        i = {'profile': j}
        if not i['profile'] in plidtoint:
            continue
        plrentry = playermap[plidtoint[i['profile']]]
        if (plrentry['w']+plrentry['l']+plrentry['d']) < mingames:
            continue
        try:
            if not seasonNull:
                tmp = await mongoclient["b2"]["players"].find_one({"season": season, "plid": i["profile"]}, sort=[("date", -1)])
            if seasonNull or tmp==None:
                tmp = await mongoclient["b2"]["players"].find_one({"plid": i["profile"]}, sort=[("date", -1)])
            if (tmp['score']) < minscore or (tmp['score']) > maxscore:
                continue
            if not tmp['season'] == season:
                tmp['hidescore'] = True
            elif not tmp['plid'] in currlb:
                tmp['flagged'] = True
            tmp["__lbprop"] = getlbprop(mode, plrentry)
            tmp["__lbsort"] = tmp["__lbprop"]
            lblist.append(tmp)
        except:
            pass
    lblist = sorted(lblist, key=lambda d: d['__lbsort'], reverse=True)
    for index, i in enumerate(lblist, 1):
        i["__lbplace"] = index
    for i in range(1, len(lblist)):
        if lblist[i]["__lbsort"] == lblist[i-1]["__lbsort"]:
            lblist[i]["__lbplace"] = lblist[i-1]["__lbplace"]
    return lblist

async def getlbvs(mongoclient, season, seasonNull, cutoffdate, mode, mingames, minscore, maxscore, lb, vsplid):
    if mode == "wins":
        if seasonNull:
            matches = mongoclient['b2']['matches'].find({'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, 'loser': vsplid})
        else:
            matches = mongoclient['b2']['matches'].find({'season': season, 'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, 'loser': vsplid})
    elif mode == "losses":
        if seasonNull:
            matches = mongoclient['b2']['matches'].find({'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, 'winner': vsplid})
        else:
            matches = mongoclient['b2']['matches'].find({'season': season, 'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, 'winner': vsplid})
    else:
        if seasonNull:
            matches = mongoclient["b2"]["matches"].aggregate([
                {"$match": {'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, "$or": [{"body.playerRight.profileURL": vsplid}, {"body.playerLeft.profileURL": vsplid}]}}
            ])
        else:
            matches = mongoclient["b2"]["matches"].aggregate([
                {"$match": {'season': season, 'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}, "$or": [{"body.playerRight.profileURL": vsplid}, {"body.playerLeft.profileURL": vsplid}]}}
            ])
    currlb = []
    for i in lb['lb']:
        currlb.append(i['profile'])
    playermap = []
    plidtoint = {}
    pticc = 0
    async for i in matches:
        if not i['body']['playerLeft']['profileURL'] in plidtoint:
            playermap.append({'w': 0, 'l': 0, 'd': 0, 'pt': 0})
            plidtoint[i['body']['playerLeft']['profileURL']] = pticc
            pticc += 1
        if not i['body']['playerRight']['profileURL'] in plidtoint:
            playermap.append({'w': 0, 'l': 0, 'd': 0, 'pt': 0})
            plidtoint[i['body']['playerRight']['profileURL']] = pticc
            pticc += 1
        if i['winner'] == 'draw':
            playermap[plidtoint[i['body']['playerLeft']['profileURL']]]['d'] += 1
            playermap[plidtoint[i['body']['playerRight']['profileURL']]]['d'] += 1
        else:
            playermap[plidtoint[i['winner']]]['w'] += 1
            playermap[plidtoint[i['loser']]]['l'] += 1
        playermap[plidtoint[i['body']['playerLeft']['profileURL']]]['pt'] += i['body']['duration']
        playermap[plidtoint[i['body']['playerRight']['profileURL']]]['pt'] += i['body']['duration']
    lblist = []
    for j in plidtoint.keys():
        i = {'profile': j}
        if not i['profile'] in plidtoint:
            continue
        if i['profile'] == vsplid:
            continue
        plrentry = playermap[plidtoint[i['profile']]]
        if (plrentry['w']+plrentry['l']+plrentry['d']) < mingames:
            continue
        try:
            if not seasonNull:
                tmp = await mongoclient["b2"]["players"].find_one({"season": season, "plid": i["profile"]}, sort=[("date", -1)])
            if seasonNull or tmp==None:
                tmp = await mongoclient["b2"]["players"].find_one({"plid": i["profile"]}, sort=[("date", -1)])
            if (tmp['score']) < minscore or (tmp['score']) > maxscore:
                continue
            if not tmp['season'] == season:
                tmp['hidescore'] = True
            elif not tmp['plid'] in currlb:
                tmp['flagged'] = True
            tmp["__lbprop"] = getlbprop(mode, plrentry)
            tmp["__lbsort"] = tmp["__lbprop"]
            lblist.append(tmp)
        except:
            pass
    lblist = sorted(lblist, key=lambda d: d['__lbsort'], reverse=True)
    for index, i in enumerate(lblist, 1):
        i["__lbplace"] = index
    for i in range(1, len(lblist)):
        if lblist[i]["__lbsort"] == lblist[i-1]["__lbsort"]:
            lblist[i]["__lbplace"] = lblist[i-1]["__lbplace"]
    return lblist

import datetime
import math

def expected(A, B, b, i):
    return 1 / (1 + b ** ((B - A) / i))

def expectedcap(A, B, b, i, cap):
    delta = (B - A)
    if abs(delta) > cap:
        delta = (delta/abs(delta))*cap
    return 1 / (1 + b ** (delta / i))

def elo(old, exp, score, k):
    return old + k * (score - exp)

async def eloexperiment(mongoclient, season, seasonNull, cutoffdate, lb, mode, k, elo_i, elo_b, elo_cap, elo_start):
    if seasonNull:
        mlist = mongoclient["b2"]["matches"].aggregate([
            {"$match": {'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}}
        ])
    else:
        mlist = mongoclient["b2"]["matches"].aggregate([
            {"$match": {'season': season, 'date':  {"$gte": datetime.datetime.utcfromtimestamp(cutoffdate)}}}
        ])
    grmap = {}
    plist = []
    async for i in mlist:
        if not i['body']['playerLeft']['profileURL'] in plist:
            plist.append(i['body']['playerLeft']['profileURL'])
        if not i['body']['playerRight']['profileURL'] in plist:
            plist.append(i['body']['playerRight']['profileURL'])
        key = i["date"].astimezone(datetime.timezone.utc).timestamp()
        if key in grmap:
            grmap[key].append(i)
        else:
            grmap[key] = [i]
    elotable = {}
    gamenum = {}
    for i in plist:
        gamenum[i] = 0
        if mode == 'elo' or mode == 'elo capped':
            elotable[i] = elo_start
        if mode == 'jake discrete' or mode =='jake continuous':
            elotable[i] = elo_start
        if mode == 'accuracy':
            elotable[i] = elo_start
        elif mode == 'glicko2':
            pass #elotable[i] = glicko2.Player()
    for ii in sorted(grmap.keys()):
        expt = {}
        cls = {}
        dev = {}
        for i in grmap[ii]:
            if i['winner'] == 'draw':
                continue
            if not i['winner'] in expt:
                if mode == 'elo' or mode == 'elo capped':
                    expt[i['winner']] = 0
                    cls[i['winner']] = 0
                if mode == 'accuracy':
                    expt[i['winner']] = 0
                if mode == 'jake discrete' or mode =='jake continuous':
                    expt[i['winner']] = 0
            if not i['loser'] in expt:
                if mode == 'elo' or mode == 'elo capped':
                    expt[i['loser']] = 0
                    cls[i['loser']] = 0
                if mode == 'accuracy':
                    expt[i['loser']] = 0
                if mode == 'jake discrete' or mode =='jake continuous':
                    expt[i['loser']] = 0
            if mode == 'elo':
                expt[i['winner']] += expected(elotable[i['winner']], elotable[i['loser']], elo_b, elo_i)
                expt[i['loser']] += expected(elotable[i['loser']], elotable[i['winner']], elo_b, elo_i)
                cls[i['winner']] += 1
                cls[i['loser']] += 0
                gamenum[i['winner']] += 1
                gamenum[i['loser']] += 1
            if mode == 'elo capped':
                expt[i['winner']] += expectedcap(elotable[i['winner']], elotable[i['loser']], elo_b, elo_i, elo_cap)
                expt[i['loser']] += expectedcap(elotable[i['loser']], elotable[i['winner']], elo_b, elo_i, elo_cap)
                cls[i['winner']] += 1
                cls[i['loser']] += 0
                gamenum[i['winner']] += 1
                gamenum[i['loser']] += 1
            #if mode == 'jake discrete':
            #    expt[i['winner']] += 50/(2**math.floor((elotable[i['winner']]-elotable[i['loser']])/1000))
            #    expt[i['loser']] += 50/(2**math.floor((elotable[i['loser']]-elotable[i['winner']])/1000))
            if mode =='jake continuous':
                delo = 50/(elo_b**((max(elotable[i['winner']], elotable[i['loser']])-min(elotable[i['winner']], elotable[i['loser']]))/elo_i))
                if delo > 100:
                    delo = 100
                if delo < 5:
                    delo = 5
                if elotable[i['winner']] > elotable[i['loser']]:
                    expt[i['winner']] += delo
                    expt[i['loser']] -= delo
                else:
                    expt[i['winner']] += 100-delo
                    expt[i['loser']] -= 100-delo
            if mode =='accuracy':
                delo = 50-((elotable[i['winner']]-elotable[i['loser']])/150)
                if delo > 100:
                    delo = 100
                if delo < 5:
                    delo = 5
                expt[i['winner']] += delo
                expt[i['loser']] -= delo
        for i in expt:
            if mode == 'elo':
                elotable[i] = elo(elotable[i], expt[i], cls[i], k)
            if mode == 'elo capped':
                elotable[i] = elo(elotable[i], expt[i], cls[i], k)
            if mode == 'accuracy':
                elotable[i] += expt[i]
                if elotable[i]<0:
                    elotable[i] = 0
            if mode == 'jake discrete' or mode =='jake continuous':
                elotable[i] += expt[i]
    lblist = []
    for i in plist:
        if not i in elotable:
            continue
        try:
            tmp = await mongoclient["b2"]["players"].find_one({"plid": i}, sort=[("date", -1)])
            if not tmp['season'] == season:
                tmp['hidescore'] = True
            tmp["__lbprop"] = elotable[i]
            tmp["__lbsort"] = tmp["__lbprop"]
            lblist.append(tmp)
        except:
            pass
    lblist = sorted(lblist, key=lambda d: d['__lbsort'], reverse=True)
    for index, i in enumerate(lblist, 1):
        i["__lbplace"] = index
    for i in range(1, len(lblist)):
        if lblist[i]["__lbsort"] == lblist[i-1]["__lbsort"]:
            lblist[i]["__lbplace"] = lblist[i-1]["__lbplace"]
    return lblist
