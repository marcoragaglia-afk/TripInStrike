"""Estrae testo dal PDF A4_P_Ancona.pdf pagina per pagina per analisi."""
import pdfplumber
from pathlib import Path

PDF = Path(r"C:\Users\El_Bl\Downloads\A4_P_Ancona.pdf")

with pdfplumber.open(str(PDF)) as pdf:
    print(f"Totale pagine: {len(pdf.pages)}")
    for i, page in enumerate(pdf.pages, 1):
        print(f"\n{'=' * 70}\nPAGINA {i}\n{'=' * 70}")
        txt = page.extract_text() or ""
        print(txt[:3000])
        if len(txt) > 3000:
            print(f"\n... (troncato, totale {len(txt)} caratteri)")
