"""
Elabora SFODNO.png: cancella la scritta "FRECCIAROSSA 1000" usando
un colore rosso campionato dalla carrozza pulita.
"""
from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
from statistics import median

SRC = Path(r"C:\Users\El_Bl\Pictures\SFODNO.png")
OUT = Path(__file__).parent / "bg.jpg"

img = Image.open(SRC).convert("RGB")
W, H = img.size
print(f"Originale: {W}x{H}")

# Bounding box scritta (in pixel relativi)
# Visivamente: text "FRECCIAROSSA 1000" è centrato attorno a x=975, y=627
# Largo ~210 px, alto ~25 px
TEXT_X1, TEXT_Y1 = int(W * 0.555), int(H * 0.606)
TEXT_X2, TEXT_Y2 = int(W * 0.715), int(H * 0.640)
print(f"Text box: ({TEXT_X1}, {TEXT_Y1}) - ({TEXT_X2}, {TEXT_Y2})")

# Campiona il rosso "medio" da una zona pulita del treno
# Punti pulitamente rossi: appena sopra il testo e appena sotto
SAMPLES = []
for x_off in (0.3, 0.5, 0.7):
    for y_off in (-0.06, -0.04):  # sopra al testo
        sx = TEXT_X1 + int((TEXT_X2 - TEXT_X1) * x_off)
        sy = TEXT_Y1 + int(H * y_off)
        if 0 <= sx < W and 0 <= sy < H:
            SAMPLES.append(img.getpixel((sx, sy)))
print(f"Campioni rossi: {SAMPLES}")
red = (
    int(median([s[0] for s in SAMPLES])),
    int(median([s[1] for s in SAMPLES])),
    int(median([s[2] for s in SAMPLES])),
)
print(f"Rosso medio scelto: {red}")

# Dipingi un rettangolo del colore rosso medio sopra il testo principale
draw = ImageDraw.Draw(img)
draw.rectangle([TEXT_X1, TEXT_Y1, TEXT_X2, TEXT_Y2], fill=red)

# Smussa i bordi del rettangolo per fonderlo col resto del treno
border = 10
edge_box = (TEXT_X1 - border, TEXT_Y1 - border,
            TEXT_X2 + border, TEXT_Y2 + border)
patch = img.crop(edge_box)
patch = patch.filter(ImageFilter.GaussianBlur(radius=3))
img.paste(patch, (edge_box[0], edge_box[1]))

# Ridimensiona per web
MAX_W = 1920
if W > MAX_W:
    nh = int(H * MAX_W / W)
    img = img.resize((MAX_W, nh), Image.LANCZOS)

img.save(OUT, "JPEG", quality=85, optimize=True, progressive=True)
print(f"Salvata: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
