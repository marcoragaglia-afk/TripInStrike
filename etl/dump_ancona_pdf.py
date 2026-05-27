"""Dump completo del PDF Ancona in un file di testo."""
import pdfplumber
from pathlib import Path

PDF = Path(r"C:\Users\El_Bl\Downloads\A4_P_Ancona.pdf")
OUT = Path(__file__).parent / "ancona_pdf_dump.txt"

with pdfplumber.open(str(PDF)) as pdf:
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"Totale pagine: {len(pdf.pages)}\n\n")
        for i, page in enumerate(pdf.pages, 1):
            f.write(f"\n{'=' * 70}\nPAGINA {i}\n{'=' * 70}\n")
            txt = page.extract_text() or ""
            f.write(txt)
            f.write("\n")

print(f"Dump scritto in {OUT}")
print(f"Size: {OUT.stat().st_size} bytes")
