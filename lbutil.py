import pymongo

def getlbprop(mode, plrentry):
    if mode == 'wins':
        return plrentry['w']
    if mode == 'losses':
        return plrentry['l']
    if mode == 'games played':
        return plrentry['w']+plrentry['l']+plrentry['d']
    if mode == 'winrate':
        if (plrentry['w']+plrentry['l']+plrentry['d']) == 0:
            return 0
        return plrentry['w']/(plrentry['w']+plrentry['l']+plrentry['d'])
    if mode == 'w/l':
        return plrentry['w']/max(1, plrentry['l'])
    if mode == 'playtime':
        return plrentry['pt']

def getlb(mongoclient, season, mode, mingames, minscore, lb):
    matches = list(mongoclient['b2']['matches'].find({'season': season}))
    playermap = []
    plidtoint = {}
    pticc = 0
    for i in matches:
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
    for i in lb["lb"]:
        if not i['profile'] in plidtoint:
            continue
        plrentry = playermap[plidtoint[i['profile']]]
        if (plrentry['w']+plrentry['l']+plrentry['d']) < mingames:
            continue
        tmp = mongoclient["b2"]["players"].find({"plid": i["profile"], "season": season}).sort("date", -1).limit(1)[0]
        if (tmp['score']) < minscore:
            continue
        tmp["__lbprop"] = getlbprop(mode, plrentry)
        tmp["__lbsort"] = tmp["__lbprop"]
        lblist.append(tmp)
    lblist = sorted(lblist, key=lambda d: d['__lbsort'], reverse=True)
    for index, i in enumerate(lblist, 1):
        i["__lbplace"] = index
    for i in range(1, len(lblist)):
        if lblist[i]["__lbsort"] == lblist[i-1]["__lbsort"]:
            lblist[i]["__lbplace"] = lblist[i-1]["__lbplace"]
    return lblist

