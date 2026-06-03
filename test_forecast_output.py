import urllib.request, json

r = urllib.request.urlopen('http://localhost:5001/api/forecasts')
d = json.loads(r.read())

print(f"{'Subsector':40s} {'Hz':3s} {'Base':>8s} {'Bull':>8s} {'Bear':>8s} {'Conf':>6s}")
print("-" * 75)
for f in d['forecasts']:
    sub = f.get('subsector', f.get('sector', '?'))
    hz = f['horizon']
    base = f['base_case_return']
    bull = f['bull_case_return']
    bear = f['bear_case_return']
    conf = f['confidence_score']
    print(f"{sub:40s} {hz:3s} {base:+7.1f}% {bull:+7.1f}% {bear:+7.1f}% {conf:5.2f}")

print(f"\nTotal forecasts: {len(d['forecasts'])}")
