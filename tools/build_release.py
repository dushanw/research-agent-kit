#!/usr/bin/env python3
"""Refresh the checksummed file inventory after an intentional source change.
The installer subsequently tests the complete staged copy before activation.
"""
import ast
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
module = ast.parse((root / 'rf' / '__init__.py').read_text())
version = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign) and any(getattr(t, 'id', '') == 'VERSION' for t in n.targets))
files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts and '__MACOSX' not in p.parts and p.name not in {'RELEASE.json', '.DS_Store'} and not p.name.startswith('._')}
(root / 'RELEASE.json').write_text(json.dumps({'format': 1, 'version': version, 'files': files}, indent=2) + '\n')
print(f'Inventory built: {len(files)} files, version {version}. Run tests and install.py; do not edit installed releases in place.')
