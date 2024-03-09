import io
import os

from PIL import Image, ImageDraw, ImageFont

import imagegen.fontcache as fontcache

def sctext(img, rect, fontname, text, fontsize, text_color, outline_size, outline_color):
    #fontsize = min(fontsize, rect[3]-rect[1])
    font = fontcache.getfont(fontname, fontsize)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmpd = ImageDraw.Draw(tmp)
    if tmpd.textlength(text, font=font) > rect[2]-rect[0]:
        font = fontcache.getfont(fontname, int(((rect[2]-rect[0])/tmpd.textlength(text, font=font))*fontsize))
    tbox = tmpd.textbbox((0, 0), text, font=font)
    tbox = (tbox[2], tbox[3])
    tsx = (((rect[2]-rect[0])-tbox[0])//2)+rect[0]
    tsy = (((rect[3]-rect[1])-tbox[1])//2)+rect[1]
    tmpd.text((tsx, tsy), text, font=font, fill=text_color, stroke_width=outline_size, stroke_fill=outline_color)
    img = Image.alpha_composite(img, tmp)
    return img

def sctext_ncx(img, rect, fontname, text, fontsize, text_color, outline_size, outline_color):
    #fontsize = min(fontsize, rect[3]-rect[1])
    font = fontcache.getfont(fontname, fontsize)
    tmp = Image.new("RGBA", img.size, (255, 255, 255, 0))
    tmpd = ImageDraw.Draw(tmp)
    if tmpd.textlength(text, font=font) > rect[2]-rect[0]:
        font = fontcache.getfont(fontname, int(((rect[2]-rect[0])/tmpd.textlength(text, font=font))*fontsize))
    tbox = tmpd.textbbox((0, 0), text, font=font)
    tbox = (tbox[2], tbox[3])
    tsx = rect[0]
    tsy = (((rect[3]-rect[1])-tbox[1])//2)+rect[1]
    tmpd.text((tsx, tsy), text, font=font, fill=text_color, stroke_width=outline_size, stroke_fill=outline_color)
    img = Image.alpha_composite(img, tmp)
    return img

def time_round(time):
    sec = time%60
    time = time//60
    min = time%60
    time = time//60
    hr = time%24
    time = time//24
    day = time
    if day > 0:
        return f"{day}d {hr}h"
    if hr > 0:
        return f"{hr}h {min}m"
    if min > 0:
        return f"{min}m {sec}s"
    return f"{sec}s"
