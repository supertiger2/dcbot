import io
import os

from PIL import Image, ImageDraw, ImageFont

import imagegen.imgcache as imgcache
import imagegen.fontcache as fontcache
import imagegen.medalutil as medalutil

from imagegen.textutil import *

# kinda copied from geeksforgeeks :P
async def getRoman(number):
    ans = ""
    num = [1, 4, 5, 9, 10, 40, 50, 90,
        100, 400, 500, 900, 1000]
    sym = ["I", "IV", "V", "IX", "X", "XL",
        "L", "XC", "C", "CD", "D", "CM", "M"]
    i = 12
    while number:
        div = number // num[i]
        number %= num[i]
        while div:
            ans += sym[i]
            div -= 1
        i -= 1
    return ans

async def seasonMedal(url, season):
    roman = await getRoman(season)
    font = fontcache.getfont("font.ttf", 30)
    img = await imgcache.getimg(url, "medal")
    img2 = Image.new("RGBA", img.size, (255, 255, 255, 0))
    imgd = ImageDraw.Draw(img)
    text_color = (255, 255, 255, 255)
    outline_color = (0, 0, 0, 255)
    centershift = (65-imgd.textlength(roman, font=font))//2
    imgd.text((31+centershift, 10), roman, font=font, fill=text_color, stroke_width=3, stroke_fill=outline_color)
    img = Image.alpha_composite(img, img2)
    return img

async def genProfileImage(profile):
    #print(profile, flush=True)
    img = await imgcache.getimg(profile["body"]["equippedBannerURL"], "banner")
    pfp_ol = await imgcache.getimg("pfp_outline", "misc")
    img.paste(pfp_ol, (14+11, 11), pfp_ol)
    pfpim = Image.new("RGBA", img.size, (255, 255, 255, 0))
    pfp = await imgcache.getimg(profile["body"]["equippedAvatarURL"], "pfp")
    pfpim.paste(pfp, (14+15, 15))
    img = Image.alpha_composite(img, pfpim)
    # add name and score
    font = fontcache.getfont("font.ttf", 100)
    elofont = fontcache.getfont("elofont.ttf", 66)
    tim = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tim_d = ImageDraw.Draw(tim)
    outline_color = (0, 0, 0, 255)
    if ("hidescore" in profile and profile["hidescore"]):
        tim_d.text((210, 93), "N/A", font=elofont, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=outline_color)
    elif ("flagged" in profile and profile["flagged"]):
        tim_d.text((210, 93), str(profile["score"]), font=elofont, fill=(255, 96, 96, 255), stroke_width=4, stroke_fill=outline_color)
    elif ("notInHom" in profile and profile["notInHom"]):
        tim_d.text((210, 93), str(profile["score"]), font=elofont, fill=(80, 229, 255, 255), stroke_width=4, stroke_fill=outline_color)
    else:
        tim_d.text((210, 93), str(profile["score"]), font=elofont, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=outline_color)
    text_color = (255, 255, 255, 255)
    if profile["body"]["is_club_member"]:
        text_color = (252, 164, 9, 255)
        outline_color = (103, 33, 12, 255)
    if tim_d.textlength(profile["body"]["displayName"], font=font) > 831:
            font = fontcache.getfont("font.ttf", int((831/tim_d.textlength(profile["body"]["displayName"], font=font))*100))
    tim_d.text((196, 25), profile["body"]["displayName"], font=font, fill=text_color, stroke_width=6, stroke_fill=outline_color)
    img = Image.alpha_composite(img, tim)
    # add medals
    nextmx = 1280
    mim = Image.new("RGBA", img.size, (255, 255, 255, 0))
    if profile["body"]["badges_equipped"] == None:
        profile["body"]["badges_equipped"] = []
    for i in reversed(profile["body"]["badges_equipped"]):
        medal = await seasonMedal(i["iconURL"], i["season"])
        mim.paste(medal, (nextmx, 10))
        nextmx = nextmx - 126
    img = Image.alpha_composite(img, mim)
    # add border
    border = await imgcache.getimg(profile["body"]["equippedBorderURL"], "border")
    tmp = Image.new("RGBA", border.size, (255, 255, 255, 0))
    tmp.paste(img, (1, 6))
    img = Image.alpha_composite(tmp, border)
    return img

async def genLBEImage(profile, lbsize, season):
    img = Image.new("RGBA", (1839, 201), (255, 255, 255, 0))
    profimg = await genProfileImage(profile)
    img.paste(profimg, (417, 0))
    img.paste(await seasonMedal(medalutil.getMedalUrl(profile["place"], lbsize), season), (2, 28))
    placecolor = (255, 255, 255)
    placestr = str(profile["place"])
    if "flagged" in profile and profile["flagged"]:
        placecolor = (255, 0, 0, 255)
        placestr += "*"
    img = sctext_ncx(img, (166, 0, 362, 201), "font.ttf", placestr, 150, placecolor, 8, (0, 0, 0))
    return img

async def genDeltaStatImage(oldstat, newstat, winsR, lossesR, drawsR, elodecay, playtime, lbsize, season):
    img = await imgcache.getimg("star_background", "misc")
    profimg = await genProfileImage(newstat)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmp.paste(await genLBEImage(newstat, lbsize, season), (26, 44))
    img = Image.alpha_composite(img, tmp)
    # wins losses unused here, as counting from matches has much smaller delay
    dwins =  newstat["body"]["rankedStats"]["wins"]-oldstat["body"]["rankedStats"]["wins"]
    dlosses = newstat["body"]["rankedStats"]["losses"]-oldstat["body"]["rankedStats"]["losses"]
    img = sctext(img, (65, 315, 496, 373), "font.ttf", "Elo gain:", 62, (255, 255, 255), 6, (0, 0, 0))
    # render elo with the triangle
    delo = " "+str(abs(newstat["score"]-oldstat["score"]))
    elop = ''
    elop_color = (0, 0, 0)
    elop_ocolor = (0, 0, 0, 0)
    if newstat["score"]-oldstat["score"] > 0:
        elop = u'🞁'
        elop_color = (111, 215, 38)
        elop_ocolor = (9, 83, 3, 255)
    if newstat["score"]-oldstat["score"] < 0:
        elop = u'🞃'
        elop_color = (240, 8, 37)
        elop_ocolor = (92, 4, 6, 255)
    rect = (65, 401, 496, 538)
    font = fontcache.getfont("font.ttf", 180)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmpd = ImageDraw.Draw(tmp)
    if tmpd.textlength(elop+delo, font=font) > rect[2]-rect[0]:
        font = fontcache.getfont("font.ttf", int(((rect[2]-rect[0])/tmpd.textlength(elop+delo, font=font))*180))
    tbox = tmpd.textbbox((0, 0), elop+delo, font=font)
    tbox = (tbox[2], tbox[3])
    tsx = (((rect[2]-rect[0])-tbox[0])//2)+rect[0]
    tsy = (((rect[3]-rect[1])-tbox[1])//2)+rect[1]
    efont = fontcache.getfont("font.ttf", 180)
    tmpd.text((tsx, tsy), elop, font=efont, fill=elop_color, stroke_width=11, stroke_fill=elop_ocolor)
    tsx += tmpd.textlength(elop, font=font)
    tmpd.text((tsx, tsy), delo, font=font, fill=(255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0))
    img = Image.alpha_composite(img, tmp)
    avgain = 0
    if (winsR) != 0:
        avgain = (100*lossesR+(newstat["score"]-oldstat["score"]+elodecay))/(winsR+lossesR)
    avloss = 0
    if (lossesR) != 0:
        avloss = (100*winsR-(newstat["score"]-oldstat["score"]+elodecay))/(winsR+lossesR)
    winrate = 0
    wrc = (255, 255, 255)
    if (winsR+lossesR+drawsR) != 0:
        winrate = winsR/(winsR+lossesR+drawsR)
        if winrate > 0.5:
            wrc = (160, 255, 160)
        elif winrate < 0.5:
            wrc = (255, 160, 160)
    # the rest
    img = sctext(img, (619, 315, 884, 373), "font.ttf", "Wins:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (619, 401, 884, 538), "font.ttf", str(winsR), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (1021, 315, 1286, 373), "font.ttf", "Losses:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (1021, 401, 1286, 538), "font.ttf", str(lossesR), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (1441, 315, 1731, 373), "font.ttf", "WR:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (1461, 401, 1771, 538), "font.ttf", str(int(round(winrate*100, 1)))+'%', 180, wrc, 9, (0, 0, 0))
    img = sctext(img, (1441, 555, 1731, 615), "font.ttf", "W/L: "+str(round(winsR/max(1, lossesR), 2)), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (550, 555, 953, 615), "font.ttf", "Avg gain: "+str(round(avgain, 1)), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (952, 555, 1355, 615), "font.ttf", "Avg loss: "+str(round(avloss, 1)), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (97, 666, 608, 727), "font.ttf", "Playtime:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (97, 755, 608, 892), "font.ttf", time_round(playtime), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (850, 666, 1717, 727), "font.ttf", "Places gain:", 62, (255, 255, 255), 6, (0, 0, 0))
    oldplace = str(oldstat['place'])
    if oldstat['place'] == 0:
        oldplace = "?"
    img = sctext(img, (850, 755, 1717, 892), "font.ttf", "#"+str(oldplace)+u" 🡆 #"+str(newstat["place"]), 180, (255, 255, 255), 9, (0, 0, 0))
    return img

async def genDeltaStatImageExtended(oldstat, newstat, winsR, lossesR, drawsR, drawsRFull, elodecay, peakelo, playtime, lbsize, season):
    img = await imgcache.getimg("star_background_extended", "misc")
    profimg = await genProfileImage(newstat)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmp.paste(await genLBEImage(newstat, lbsize, season), (26, 44))
    img = Image.alpha_composite(img, tmp)
    # wins losses unused here, as counting from matches has much smaller delay
    dwins =  newstat["body"]["rankedStats"]["wins"]-oldstat["body"]["rankedStats"]["wins"]
    dlosses = newstat["body"]["rankedStats"]["losses"]-oldstat["body"]["rankedStats"]["losses"]
    img = sctext(img, (65, 666, 496, 726), "font.ttf", "Elo gain:", 62, (255, 255, 255), 6, (0, 0, 0))
    # render elo with the triangle
    delo = " "+str(abs(newstat["score"]-oldstat["score"]))
    elop = ''
    elop_color = (0, 0, 0)
    elop_ocolor = (0, 0, 0, 0)
    if newstat["score"]-oldstat["score"] > 0:
        elop = u'🞁'
        elop_color = (111, 215, 38)
        elop_ocolor = (9, 83, 3, 255)
    if newstat["score"]-oldstat["score"] < 0:
        elop = u'🞃'
        elop_color = (240, 8, 37)
        elop_ocolor = (92, 4, 6, 255)
    rect = (65, 752, 496, 889)
    font = fontcache.getfont("font.ttf", 180)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmpd = ImageDraw.Draw(tmp)
    if tmpd.textlength(elop+delo, font=font) > rect[2]-rect[0]:
        font = fontcache.getfont("font.ttf", int(((rect[2]-rect[0])/tmpd.textlength(elop+delo, font=font))*180))
    tbox = tmpd.textbbox((0, 0), elop+delo, font=font)
    tbox = (tbox[2], tbox[3])
    tsx = (((rect[2]-rect[0])-tbox[0])//2)+rect[0]
    tsy = (((rect[3]-rect[1])-tbox[1])//2)+rect[1]
    efont = fontcache.getfont("font.ttf", 180)
    tmpd.text((tsx, tsy), elop, font=efont, fill=elop_color, stroke_width=11, stroke_fill=elop_ocolor)
    tsx += tmpd.textlength(elop, font=font)
    tmpd.text((tsx, tsy), delo, font=font, fill=(255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0))
    img = Image.alpha_composite(img, tmp)
    avgain = 0
    if (winsR) != 0:
        avgain = (100*lossesR+(newstat["score"]-oldstat["score"]+elodecay))/(winsR+lossesR)
    avloss = 0
    if (lossesR) != 0:
        avloss = (100*winsR-(newstat["score"]-oldstat["score"]+elodecay))/(winsR+lossesR)
    winrate = 0
    wrc = (255, 255, 255)
    if (winsR+lossesR+drawsR) != 0:
        winrate = winsR/(winsR+lossesR+drawsR)
        if winrate > 0.5:
            wrc = (160, 255, 160)
        elif winrate < 0.5:
            wrc = (255, 160, 160)
    # the rest
    img = sctext(img, (205, 315, 470, 373), "font.ttf", "Wins:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (205, 401, 470, 538), "font.ttf", str(winsR), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (136, 555, 539, 615), "font.ttf", "Avg gain: "+str(round(avgain, 1)), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (619, 315, 884, 373), "font.ttf", "Losses:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (619, 401, 884, 538), "font.ttf", str(lossesR), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (550, 555, 953, 615), "font.ttf", "Avg loss: "+str(round(avloss, 1)), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (1021, 315, 1286, 373), "font.ttf", "Draws:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (1021, 401, 1286, 538), "font.ttf", str(drawsR), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (952, 555, 1355, 615), "font.ttf", "Lobby DCs: "+str(drawsR-drawsRFull), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (1441, 315, 1731, 373), "font.ttf", "WR:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (1461, 401, 1771, 538), "font.ttf", str(int(round(winrate*100, 1)))+'%', 180, wrc, 9, (0, 0, 0))
    img = sctext(img, (1441, 555, 1731, 615), "font.ttf", "W/L: "+str(round(winsR/max(1, lossesR), 2)), 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (645, 666, 1076, 724), "font.ttf", "Peak Elo:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (685, 752, 1056, 889), "font.ttf", str(peakelo), 180, (255, 255, 255), 9, (0, 0, 0))
    if peakelo == newstat["score"]:
        img = sctext(img, (645, 906, 1076, 966), "font.ttf", "At peak Elo", 54, (255, 255, 255), 5, (0, 0, 0))
    else:
        img = sctext(img, (645, 906, 1076, 966), "font.ttf", str(peakelo-newstat["score"])+" below peak", 54, (255, 255, 255), 5, (0, 0, 0))
    img = sctext(img, (1248, 666, 1759, 724), "font.ttf", "Avg match len: ", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (1248, 752, 1759, 889), "font.ttf", time_round(int(round(playtime/max(1,(winsR+lossesR+drawsR)), 0))), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (97, 1017, 608, 1078), "font.ttf", "Playtime:", 62, (255, 255, 255), 6, (0, 0, 0))
    img = sctext(img, (97, 1106, 608, 1243), "font.ttf", time_round(playtime), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext(img, (850, 1017, 1717, 1078), "font.ttf", "Places gain:", 62, (255, 255, 255), 6, (0, 0, 0))
    oldplace = str(oldstat['place'])
    if oldstat['place'] == 0:
        oldplace = "?"
    img = sctext(img, (850, 1106, 1717, 1243), "font.ttf", "#"+str(oldplace)+u" 🡆 #"+str(newstat["place"]), 180, (255, 255, 255), 9, (0, 0, 0))
    return img

async def genVs(player, oponent, winsp, winso, draws, lbsize, season):
    img = await imgcache.getimg("star_background_horizontal", "misc")
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmp.paste(await genLBEImage(player, lbsize, season), (30, 30))
    img = Image.alpha_composite(img, tmp)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmp.paste(await genLBEImage(oponent, lbsize, season), (30, 252))
    img = Image.alpha_composite(img, tmp)
    wrcp = (255, 255, 255)
    wrco = (255, 255, 255)
    if winsp > winso:
        wrcp = (160, 255, 160)
        wrco = (255, 160, 160)
    if winsp < winso:
        wrco = (160, 255, 160)
        wrcp = (255, 160, 160)
    img = sctext_ncx(img, (1929, 30, 2160, 232), "font.ttf", str(winsp), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext_ncx(img, (1929, 252, 2160, 454), "font.ttf", str(winso), 180, (255, 255, 255), 9, (0, 0, 0))
    img = sctext_ncx(img, (2182, 60, 2353, 130), "font.ttf", str(round(winsp/max(1, winsp+winso+draws)*100))+'%', 105, wrcp, 6, (0, 0, 0))
    img = sctext_ncx(img, (2182, 343, 2353, 423), "font.ttf", str(round(winso/max(1, winsp+winso+draws)*100))+'%', 105, wrco, 6, (0, 0, 0))
    if draws > 0:
        img = sctext_ncx(img, (2175, 165, 2250, 319), "font.ttf", str(draws), 125, (255, 255, 255), 6, (0, 0, 0))
    return img

async def genChooserLB(lblist, lbsize, season):
    img = Image.new("RGBA", (1902, 245*(len(lblist))), (255, 255, 255, 0))
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    nexty = 44
    for i in lblist:
        tmp.paste(await genLBEImage(i, lbsize, season), (26, nexty))
        nexty += 245
    img = Image.alpha_composite(img, tmp)
    return img

async def genNamehistLB(lblist):
    img = Image.new("RGBA", (1474, 245*(len(lblist))+44), (255, 255, 255, 0))
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    nexty = 44
    for i in lblist:
        tmp.paste(await genProfileImage(i), (26, nexty))
        nexty += 245
    img = Image.alpha_composite(img, tmp)
    return img

async def genMiniLB(lblist, mode):
    if mode == "namehistory":
        return await genNamehistLB(lblist)
    img = Image.new("RGBA", (2252, 245*(len(lblist))+44), (255, 255, 255, 0))
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    nexty = 44
    for i in lblist:
        tmp.paste(await genProfileImage(i), (26+447, nexty))
        tmp = sctext(tmp, (36, nexty, 417, nexty+202), "font.ttf", '# '+str(i["__lbplace"]), 150, (255, 255, 255), 9, (0, 0, 0))
        if mode == 'winrate':
            text = str(round(i["__lbprop"]*100))+'%'
        elif mode == 'w/l':
            text = str(round(i["__lbprop"], 2))
        elif mode == 'l/w':
            text = str(round(i["__lbprop"], 2))
        elif mode == 'playtime':
            text = time_round(i["__lbprop"])
        elif mode == 'avg match duration':
            text = time_round(round(i["__lbprop"]))
        else:
            text = str(i["__lbprop"])
        tmp = sctext_ncx(tmp, (1936, nexty, 2252, nexty+202), "font.ttf", text, 180, (255, 255, 255), 9, (0, 0, 0))
        nexty += 245
    img = Image.alpha_composite(img, tmp)
    return img
