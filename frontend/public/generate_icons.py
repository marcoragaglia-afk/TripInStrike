"""Genera icone PWA TripInStrike (treno stilizzato su sfondo rosso sciopero)."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent

def make_icon(size: int):
    img = Image.new("RGB", (size, size), "#E31937")  # rosso sciopero
    d = ImageDraw.Draw(img)

    # Cornice "maskable" safe area: usa solo i 4/5 centrali per il contenuto
    pad = size // 10
    inner = size - 2 * pad

    # Treno stilizzato: corpo rettangolare bianco con un solo vagone
    body_w = int(inner * 0.85)
    body_h = int(inner * 0.30)
    body_x = (size - body_w) // 2
    body_y = (size - body_h) // 2 - int(inner * 0.05)

    # Tetto arrotondato
    d.rounded_rectangle(
        [body_x, body_y, body_x + body_w, body_y + body_h],
        radius=size // 18,
        fill="#FFFFFF",
    )

    # Finestrini (3)
    win_count = 3
    win_w = body_w // 5
    win_h = body_h // 2
    gap = (body_w - win_count * win_w) // (win_count + 1)
    for i in range(win_count):
        wx = body_x + gap + i * (win_w + gap)
        wy = body_y + body_h // 5
        d.rectangle([wx, wy, wx + win_w, wy + win_h], fill="#0a0a1e")

    # Linea fronte muso (luce)
    nose_x = body_x + body_w - int(body_w * 0.06)
    d.rectangle(
        [nose_x, body_y + body_h // 3, nose_x + size // 30, body_y + 2 * body_h // 3],
        fill="#FBBF24",  # giallo
    )

    # Ruote
    wheel_r = size // 20
    wheel_y = body_y + body_h
    for x_off in (body_w // 4, 3 * body_w // 4):
        cx = body_x + x_off
        d.ellipse([cx - wheel_r, wheel_y - wheel_r, cx + wheel_r, wheel_y + wheel_r], fill="#0a0a1e")

    # Testo "TIS" piccolo sotto
    try:
        font = ImageFont.truetype("arial.ttf", size // 8)
    except Exception:
        font = ImageFont.load_default()
    text = "TIS"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    d.text(((size - tw) // 2, wheel_y + wheel_r + size // 30), text, fill="#FFFFFF", font=font)

    return img


for sz in (192, 512):
    img = make_icon(sz)
    img.save(OUT / f"icon-{sz}.png")
    print(f"Generata icon-{sz}.png")

# Anche favicon
make_icon(32).save(OUT / "favicon.png")
print("Generata favicon.png")
