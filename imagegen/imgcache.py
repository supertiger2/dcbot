import io
import os
import requests

from dotenv import load_dotenv

from PIL import Image

def getimg(url, itype):
    try:
        if not url in img_cache:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
            im = Image.open(requests.get(url, headers=headers, stream=True).raw)
            if itype == "border":
                res = Image.new("RGBA", (1422, 202), (255, 255, 255, 0))
                im = im.resize((444, 202), Image.Resampling.BICUBIC)
                mid = (im.size[0])//2
                midim = im.crop((mid, 0, mid+1, im.size[1]-1))
                for i in range(res.size[0]):
                    res.paste(midim, (i, 0))
                res.paste(im.crop((0, 0, mid, im.size[1]-1)), (0, 0))
                res.paste(im.crop((mid+1, 0, im.size[0]-1, im.size[1]-1)), (res.size[0]-((im.size[0]-1)-(mid+1)), 0))
                im = res
            if itype == "medal":
                im = im.resize((126, 158), Image.Resampling.LANCZOS)
            if ("prestige" in url) and (itype=="banner"):
                tmp = Image.new("RGBA", (1419, 178), (255, 255, 255, 0))
                im = im.rotate(-45, resample=Image.BICUBIC)
                for i in range(7):
                    tmp.paste(im, (i*(200)+50, 14))
                im = Image.alpha_composite(img_cache["prestige_banner_gradient"], tmp)
                im = Image.alpha_composite(im, img_cache["prestige_banner_stripes"])
            if itype=="pfp":
                im = im.resize((148, 148), Image.Resampling.LANCZOS)
                if "prestige" in url:
                    tmp = Image.new("RGBA", (148, 148), (255, 255, 255, 0))
                    tmp = img_cache["rainbow"]
                    im = Image.alpha_composite(tmp, im)
                    trans = Image.new("RGBA", (148, 148), (255, 255, 255, 0))
                    im = Image.composite(im, trans, img_cache["pfp_mask"])
            im.convert("RGBA")
            img_cache[url] = im
        return img_cache[url]
    except:
        if itype == "banner":
            return img_cache["unknown_banner"]
        elif itype == "pfp":
            return img_cache["unknown_pfp"]
        tmp = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        return tmp

global img_cache
try:
    img_cache
except NameError:
    img_cache = {}
    load_dotenv()
    img_cache["unknown_pfp"] = Image.open(os.getenv("IMG_DIR")+"unknown_pfp.png")
    img_cache["unknown_banner"] = Image.open(os.getenv("IMG_DIR")+"unknown_banner.png")
    img_cache["prestige_banner_gradient"] = Image.open(os.getenv("IMG_DIR")+"prestige_banner_gradient.png")
    img_cache["prestige_banner_stripes"] = Image.open(os.getenv("IMG_DIR")+"prestige_banner_stripes.png")
    img_cache["pfp_outline"] = Image.open(os.getenv("IMG_DIR")+"pfp_outline.png")
    img_cache["rainbow"] = Image.open(os.getenv("IMG_DIR")+"rainbow.png")
    img_cache["pfp_mask"] = Image.open(os.getenv("IMG_DIR")+"pfp_mask.png")
    im = Image.open(os.getenv("IMG_DIR")+"star_background.png")
    im = im.resize((1902, 958), Image.Resampling.LANCZOS)
    img_cache["star_background"] = im
    im = Image.open(os.getenv("IMG_DIR")+"star_background.png")
    im = im.resize((2369, 1266), Image.Resampling.LANCZOS)
    im = im.crop((0, 0, 2369, 484))
    img_cache["star_background_horizontal"] = im
