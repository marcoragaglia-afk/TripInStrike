"""
Elabora il mockup TripInStrike: cancella la scritta "FRECCIAROSSA 1000"
con tecnica content-aware basata su patches adiacenti.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from pathlib import Path

SRC = Path(r"C:\Users\El_Bl\Downloads\image-1779965835028.webp")
OUT = Path(__file__).parent / "bg.jpg"

img = Image.open(SRC).convert("RGB")
W, H = img.size
print(f"Originale: {W}x{H}")

# Crop: parte destra a partire dal 42% (rimuove logo)
right = img.crop((int(W * 0.42), 0, W, H))
RW, RH = right.size
print(f"Croppata: {RW}x{RH}")

# Bounding box scritta FRECCIAROSSA 1000 (basata su ispezione visiva del mockup)
TEXT_BOX = (int(RW * 0.30), int(RH * 0.51), int(RW * 0.58), int(RH * 0.60))
print(f"Text box: {TEXT_BOX}")

# Approccio content-aware: usiamo la fascia SOPRA come "patch" da sovrapporre
# alla fascia del testo. Il treno ha una banda rossa uniforme sopra le scritte,
# quindi copiando una striscia di sopra in giù mascheriamo il testo.
def inpaint_strip(src_img, box, source_offset_y):
    """Copia una striscia da (box_x, box_y - offset) → (box_x, box_y)."""
    x1, y1, x2, y2 = box
    h = y2 - y1
    # Prendi una striscia di altezza h da source_y
    source_y = y1 - source_offset_y
    strip = src_img.crop((x1, source_y, x2, source_y + h))
    # Applica blur leggero per smussare il join
    strip = strip.filter(ImageFilter.GaussianBlur(radius=1))
    src_img.paste(strip, (x1, y1))

# Copia una striscia dalla fascia immediatamente sopra il testo
inpaint_strip(right, TEXT_BOX, source_offset_y=int(RH * 0.10))

# Smussa il bordo del rettangolo applicato (overlap di blur)
border = 8
x1, y1, x2, y2 = TEXT_BOX
edge_box = (x1 - border, y1 - border, x2 + border, y2 + border)
patch = right.crop(edge_box)
patch = patch.filter(ImageFilter.GaussianBlur(radius=2))
right.paste(patch, (edge_box[0], edge_box[1]))

# Resize per web
MAX_W = 1920
if RW > MAX_W:
    nh = int(RH * MAX_W / RW)
    right = right.resize((MAX_W, nh), Image.LANCZOS)

# Salva
right.save(OUT, "JPEG", quality=82, optimize=True, progressive=True)
print(f"Salvata: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
