
from PIL import Image, ImageDraw

def create_gradient_image(x, y):
    img = Image.new('RGBA', (x, y))
    draw = ImageDraw.Draw(img)
    start_color = (255, 0, 0)
    end_color = (0, 0, 255)
    for i in range(y):
        r = int(start_color[0] + (end_color[0] - start_color[0]) * i / y)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * i / y)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * i / y)
        color = (r, g, b)
        draw.line([(0, i), (x, i)], fill=color)
    return img
