from parse_timetable import parse_timetable

results = parse_timetable({'9304', '9512', '533', '3904'}, max_pages=400)
for num, stops in sorted(results.items()):
    print(f'\nTreno {num} ({len(stops)} fermate):')
    for s in stops[:14]:
        arr = s.arrival or '-'
        dep = s.departure or '-'
        print(f'  {s.sequence:2d}. {s.station:35s}  arr={arr:6s}  dep={dep}')
