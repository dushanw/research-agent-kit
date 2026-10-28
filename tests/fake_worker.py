#!/usr/bin/env python3
"""Deterministic CLI fixtures. Never a real model or an authentication test."""
import json
from pathlib import Path
import sys
name, *args = sys.argv[1:]
if '--help' in args:
    print('--print --model --mode --output-format --sandbox --trust --output-schema --output-last-message --skip-git-repo-check --ignore-user-config --ignore-rules --append-system-prompt-file --setting-sources --strict-mcp-config --mcp-config --settings --tools')
    raise SystemExit(0)
if '--version' in args:
    print('FAKE ' + name + ' 0.0.0')
    raise SystemExit(0)
if args == ['models']:
    print('fake-independent\nfake-other')
    raise SystemExit(0)
if name == 'claude':
    print('RESEARCHFLOW_OK')
    raise SystemExit(0)
mode_file = Path(sys.argv[0]).parent / 'mode.json'
mode = json.loads(mode_file.read_text()) if mode_file.exists() else {}
# Test-specific behavior can be selected through a sibling mode.json copy.
if mode.get('exit'):
    raise SystemExit(7)
if name == 'agent':
    if mode.get('malformed'):
        print('not JSON')
    else:
        print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                          'result': 'FAKE review: test a known answer, negative values, constant inputs and NaN. This is a fixture, not a model opinion.',
                          'model': args[args.index('--model')+1]}))
else:
    packet = sys.stdin.read()
    final = Path(args[args.index('--output-last-message')+1])
    verdict = {'summary': 'FAKE review of a synthetic fixture; no live model was called.',
               'evidence_sufficient': True, 'findings': []}
    if mode.get('high'):
        verdict['findings'] = [{'severity':'high','file':'stats.py','problem':'Synthetic blocker','evidence':'Injected failure case'}]
    if mode.get('missing'):
        raise SystemExit(0)
    final.write_text(json.dumps(verdict) if not mode.get('malformed') else '{}')
    print(json.dumps(verdict))
