#!/usr/bin/env python3
"""Trusted runner entry; task code is still arbitrary code, not OS-sandboxed.

Run from an approved disposable source copy. Import our stdlib dependencies
before inserting target source onto sys.path. Capture structured test counts.
"""
import argparse
import contextlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import sys
import unittest
import xml.etree.ElementTree as ET

def main():
    p = argparse.ArgumentParser()
    p.add_argument('kind', choices=['environment', 'unittest', 'pytest', 'example'])
    p.add_argument('--root')
    p.add_argument('--tests', default='tests')
    p.add_argument('--output')
    p.add_argument('--script')
    p.add_argument('args', nargs='*')
    a = p.parse_args()
    if a.kind == 'environment':
        value = {"python": sys.version, "executable": sys.executable, "prefix": sys.prefix,
                 "packages": sorted((d.metadata.get('Name', '?'), d.version) for d in importlib.metadata.distributions())}
        print(json.dumps(value, sort_keys=True))
        return 0
    root = Path(a.root).resolve()
    sys.path.insert(0, str(root))
    if a.kind == 'example':
        sys.argv = [str(root / a.script), *a.args]
        runpy.run_path(str(root / a.script), run_name='__main__')
        return 0
    if a.kind == 'unittest':
        class Result(unittest.TextTestResult):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.ids = []
            def startTest(self, test):
                self.ids.append(test.id())
                super().startTest(test)
        suite = unittest.defaultTestLoader.discover(str(root / a.tests), top_level_dir=str(root))
        r = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
        output = {"tests": r.testsRun, "failures": len(r.failures), "errors": len(r.errors),
                  "skipped": len(r.skipped), "expected_failures": len(r.expectedFailures),
                  "unexpected_successes": len(r.unexpectedSuccesses), "test_ids": r.ids}
        code = 0 if r.wasSuccessful() else 1
    else:
        import pytest
        xml = str(Path(a.output).with_suffix('.xml'))
        code = int(pytest.main([str(root / a.tests), '-q', '-p', 'no:cacheprovider', '-o', 'xfail_strict=true', '--junitxml=' + xml]))
        tree = ET.parse(xml)
        cases = tree.findall('.//testcase')
        output = {"tests": len(cases), "failures": sum(c.find('failure') is not None for c in cases),
                  "errors": sum(c.find('error') is not None for c in cases),
                  "skipped": sum(c.find('skipped') is not None for c in cases),
                  "expected_failures": 0, "unexpected_successes": 0,
                  "test_ids": [c.get('classname', '') + '.' + c.get('name', '') for c in cases]}
    Path(a.output).write_text(json.dumps(output, indent=2) + '\n')
    return code

if __name__ == '__main__':
    sys.exit(main())
