import io
import os
import requests
import sys
import collections

from dotenv import load_dotenv
from io import BytesIO

from PIL import Image

async def getimg(url, itype):
    global cache_size
    #print(cache_size, flush=True)
    if url in local_imgs:
        return local_imgs[url]
    try:
        while cache_size > 60:
            dlr = img_cache.popitem(last=False)
            cache_size -= 1
        if not url in img_cache:
            if url in unanimateMap:
                url = unanimateMap[url]
            elif "animated" in url:
                if itype == "border":
                    return local_imgs["unknown_border"].copy()
                if itype == "banner":
                    return local_imgs["unknown_banner"].copy()
                if itype == "pfp":
                    return local_imgs["unknown_pfp"].copy()
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
            im = Image.open(BytesIO(requests.get(url, headers=headers).content))
            if itype == "border":
                res = Image.new("RGBA", (1422, 202), (255, 255, 255, 0))
                im = im.resize((444, 202), Image.Resampling.BICUBIC)
                mid = (im.size[0])//24
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
                im = Image.alpha_composite(local_imgs["prestige_banner_gradient"], tmp)
                im = Image.alpha_composite(im, local_imgs["prestige_banner_stripes"])
            if itype=="pfp":
                im = im.resize((148, 148), Image.Resampling.LANCZOS)
                if "prestige" in url:
                    tmp = Image.new("RGBA", (148, 148), (255, 255, 255, 0))
                    tmp = local_imgs["rainbow"]
                    im = Image.alpha_composite(tmp, im)
                    trans = Image.new("RGBA", (148, 148), (255, 255, 255, 0))
                    im = Image.composite(im, trans, local_imgs["pfp_mask"])
            im.convert("RGBA")
            cache_size += 1
            img_cache[url] = im
        img_cache.move_to_end(url)
        res = img_cache[url].copy()
        return res
    except:
        if itype == "border":
            return local_imgs["unknown_border"].copy()
        if itype == "banner":
            return local_imgs["unknown_banner"].copy()
        elif itype == "pfp":
            return local_imgs["unknown_pfp"].copy()
        tmp = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        return tmp.copy()

global img_cache
global cache_size
try:
    img_cache
    cache_size
except NameError:
    img_cache = collections.OrderedDict()
    cache_size = 0
    local_imgs = {}
    load_dotenv()
    # load the fallback "unknown" cosmetics
    local_imgs["unknown_pfp"] = Image.open(os.getenv("IMG_DIR")+"unknown_pfp.png")
    local_imgs["unknown_banner"] = Image.open(os.getenv("IMG_DIR")+"unknown_banner.png")
    im = Image.open(os.getenv("IMG_DIR")+"unknown_border.png")
    res = Image.new("RGBA", (1422, 202), (255, 255, 255, 0))
    im = im.resize((444, 202), Image.Resampling.BICUBIC)
    mid = (im.size[0])//24
    midim = im.crop((mid, 0, mid+1, im.size[1]-1))
    for i in range(res.size[0]):
        res.paste(midim, (i, 0))
    res.paste(im.crop((0, 0, mid, im.size[1]-1)), (0, 0))
    res.paste(im.crop((mid+1, 0, im.size[0]-1, im.size[1]-1)), (res.size[0]-((im.size[0]-1)-(mid+1)), 0))
    local_imgs["unknown_border"] = res
    # load images for making the prestige cosmetics
    local_imgs["prestige_banner_gradient"] = Image.open(os.getenv("IMG_DIR")+"prestige_banner_gradient.png")
    local_imgs["prestige_banner_stripes"] = Image.open(os.getenv("IMG_DIR")+"prestige_banner_stripes.png")
    local_imgs["rainbow"] = Image.open(os.getenv("IMG_DIR")+"rainbow.png")
    # load the generic images needed for rendering profiles
    local_imgs["pfp_outline"] = Image.open(os.getenv("IMG_DIR")+"pfp_outline.png")
    local_imgs["pfp_mask"] = Image.open(os.getenv("IMG_DIR")+"pfp_mask.png")
    # load the backgrounds
    im = Image.open(os.getenv("IMG_DIR")+"star_background.png")
    im = im.resize((1902, 958), Image.Resampling.LANCZOS)
    local_imgs["star_background"] = im
    im = Image.open(os.getenv("IMG_DIR")+"star_background.png")
    im = im.resize((2599, 1309), Image.Resampling.LANCZOS)
    im = im.crop((0, 0, 1902, 1309))
    local_imgs["star_background_extended"] = im
    im = Image.open(os.getenv("IMG_DIR")+"star_background.png")
    im = im.resize((2369, 1266), Image.Resampling.LANCZOS)
    im = im.crop((0, 0, 2369, 484))
    local_imgs["star_background_horizontal"] = im
    unanimateMap = {
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/f8e25e1cbab0858ae174fc4580ef5698_banner_border_fireworks.png': 'unknown_banner',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/396f61df7dccf50ef2a990534bd685f6_border_flame.png': 'unknown_banner',

        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/8a43d43d67400d4e9c1b7feb76fe3309_rooftop_run_animated_banner.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/b8ca60a813a29f416057249ec11a9d2a_rooftop_run_banner.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/d743b40e9e4a2fcfde20a0f9bddc3c95_avatar_north_by_north_ace_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/c466790335f2794e54fbc1aae6dacc81_avatar_north_by_north_ace.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/14b8354275f834b46edf882b2336308b_avatar_waterskiing_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/1edf44e3608c4ee922441f375c3c6baa_avatar_waterskiing.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/2fe5562a1b0343032706e12950e1a235_banner_openingceremony_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/326205b8b59a426d3c217f62b37afaaf_banner_openingceremony.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/314898bc2154dd5ca6193d5278b2db5c_banner_thunderoftheguns_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/7fd7e4a06750ecff0c5acc3c6bf2ca29_banner_thunderoftheguns.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/c64ba52a0da95beb8863924e73d0b13a_banner_moment_of_quiet_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/046fe8df0801e28a161696df0a66a502_banner_moment_of_quiet.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/a726abb8a061d0d02a5e271b083499c9_avatar_specpops_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/84cdae022260d946e6eb644b69e12aa0_avatar_specpops.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/f16998f1fa5f32f7fe0e7d1b866de8ed_winter_wonder_animated_avatar.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/4c4c652af014e781cb8c7c4173669272_winter_wonder_avatar.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/107bc5b17eb8b1cd1c1f085a8f43d75e_banner_wildwest_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/881c241cb5e7874877854b0a1bdaecd6_banner_wildwest.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/80d90515208819ddac1b37cc20c7d0bc_avatar_superbrooding_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/1613fcae7569c7ce5891c2566f0f5255_avatar_superbrooding.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/a53bff15c6ff5f00c794eee876523b91_cobra_in_the_grass_animated_banner.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/269832fa305d5680e33c33e6d7f1d6df_cobra_in_the_grass_banner.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/a42a71360ec19a4a5058f3dbf5b77d7c_avatar_humpty_monkey_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/222726c339fa8c81f39bbf2b3029450e_avatar_humpty_monkey.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/dd1ee9a86e0ad4ac2484158ac59ceb16_avatar_phoenixfire_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/28ad54ef6b54c0bf6b53e4b6796ea828_avatar_phoenixfire.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/920f1def57a0f194d430b2e2679ab6ad_banner_assemblyline_animated.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/3904689eee1a08388200c160ed2f9aa7_banner_assemblyline.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/dff704eda8e03dbe7af40f6fb33ce882_animated_avatar_bloonhunt.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/a7a284b2e3d97185deb2b1b98bf83cf7_avatar_bloonhunt.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/29ecc2c974fb8f4240594c458643c6a6_rideemcowboy_animatedavatar.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/e3a0d72377a0cc2f26873adc75236ce3_rideemcowboy_avatar.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/3bd5103f7e01b75c73447c50ac319404_animated_banner_dockparty.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/cfe6b4bffcfee323e0a5e3af05f5fa2a_banner_dockparty.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/193d96918034e4d02a8eb9773fc64337_animatedbanner_itsaghost.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/ee554cacd21b5bc1070e3b17cd17e405_banner_itsaghost.png',
        'https://static-api.nkstatic.com/appdocs/4/assets/opendata/c06104f1b6a2e461d09544a98bbc4014_animatedbanner_originstory.png': 'https://static-api.nkstatic.com/appdocs/4/assets/opendata/79a40a0609aa56082fe6ee94c8dba20d_banner_originstory.png'
    }
