import json
from pathlib import Path
from stats import normalize
out = Path('outputs')
out.mkdir(exist_ok=True)
(out / 'result.json').write_text(json.dumps({'input': [2, 4, 6], 'normalized': normalize([2, 4, 6])}, indent=2) + '\n')
print('Result: outputs/result.json')
