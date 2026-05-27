import re

STOP_RE = re.compile(
    r"([A-ZÀÈÉÌÒÙ][\w\s\.\-'`]+?)\s+"
    r"(\d{1,2}\.\d\s?\d?)"
    r"(?:\*+)?"
    r"\s*-\s*"
)

body = "Rimini 4.07 - Bologna Centrale 5.02 - Modena 5.24 - Reggio Emilia 5.39 - Parma 5.54 - Pia cenza 6.26 - "
print("Body:", repr(body))
print("\nMatches:")
for m in STOP_RE.finditer(body):
    print(f"  station={m.group(1)!r}, time={m.group(2)!r}")
