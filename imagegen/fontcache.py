import io
import os
import requests

from dotenv import load_dotenv

from PIL import ImageFont

def getfont(name, size):
    if not (name, size) in font_cache:
        font = ImageFont.truetype(os.getenv("IMG_DIR")+name, size)
        font_cache[(name, size)] = font
    return font_cache[(name, size)]

global font_cache
try:
    font_cache
except NameError:
    font_cache = {}
