"""Dump del PDF degli arrivi a Ancona."""
import pdfplumber
from pathlib import Path

PDF = Path(r"C:\Users\El_Bl\Downloads\A4_A_Ancona.pdf")
OUT = Path(__file__).parent / "ancona_arr_dump.txt"

with pdfplumber.open(str(PDF)) as pdf:
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"Totale pagine: {len(pdf.pages)}\n\n")
        for i, page in enumerate(pdf.pages, 1):
            f.write(f"\n{'=' * 70}\nPAGINA {i}\n{'=' * 70}\n")
            f.write(page.extract_text() or "")
            f.write("\n")
print(f"OK, scritto in {OUT}")
