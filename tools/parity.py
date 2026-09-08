#!/usr/bin/env python3
"""Build and compare the scaffold smoke adapters. No domain parity is claimed."""
import argparse
import itertools
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def execute(command, *, data=None):
    result = subprocess.run(command, input=data, text=True, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f'{command!r}\n{result.stdout}\n{result.stderr}')
    return result.stdout


def same(left, right):
    # Strict JSON comparison: booleans must not compare equal to integers.
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def read_json(value):
    def invalid(value):
        raise ValueError(f'Non-finite JSON number: {value}')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(value, parse_constant=invalid, object_pairs_hook=unique)


def run(root, report):
    config = read_json((root / 'parity.json').read_text())
    suite = ET.Element('testsuite', name='infrastructure-smoke')
    outputs = {}
    failures = 0

    def check(name, action):
        nonlocal failures
        case = ET.SubElement(suite, 'testcase', name=name, classname='scaffold.parity')
        try:
            action()
        except Exception as error:
            failures += 1
            ET.SubElement(case, 'failure', message=str(error)[:1000]).text = str(error)
            print(f'FAIL {name}: {error}', file=sys.stderr)

    def equal(a, b):
        if not same(a, b):
            raise AssertionError(f'{a!r} != {b!r}')

    layouts, versions = config['layouts'], config['versions']
    if not layouts or not versions or not config['compatible_cases']:
        raise ValueError('Layouts, versions and compatible cases must not be empty')
    for layout, version in itertools.product(layouts, versions):
        base = root / layout / version
        def cell():
            csharp = base / 'csharp' if layout == 'vertical' else base
            rust = base / 'rust' if layout == 'vertical' else base
            execute(['dotnet', 'build', str(csharp / 'RFX.slnx'), '-c', 'Release'])
            cargo = os.environ.get('CARGO') or shutil.which('cargo') or 'cargo'
            execute([cargo, 'test', '--manifest-path', str(rust / 'Cargo.toml'), '--workspace'])
            adapter = base / 'smoke'
            execute(['dotnet', 'build', str(adapter / 'csharp/Smoke.csproj'), '-c', 'Release'])
            execute([cargo, 'build', '--manifest-path', str(adapter / 'rust/Cargo.toml'), '--release'])
            dll = adapter / 'csharp/bin/Release' / config['framework'] / 'Smoke.dll'
            binary = adapter / 'rust/target/release' / ('smoke.exe' if os.name == 'nt' else 'smoke')
            fixtures = sorted((adapter / 'fixtures').glob('*.json'))
            expected = sorted((adapter / 'expected').glob('*.json'))
            if not fixtures or {p.name for p in fixtures} != {p.name for p in expected}:
                raise ValueError('Missing fixtures or unmatched expected results')
            for fixture in fixtures:
                data = fixture.read_text()
                read_json(data)
                wanted = read_json((adapter / 'expected' / fixture.name).read_text())
                values = {}
                for language, command in [('csharp', ['dotnet', str(dll)]), ('rust', [str(binary)])]:
                    value = read_json(execute(command, data=data))
                    outputs[f'{layout}/{version}/{language}/{fixture.stem}'] = value
                    values[language] = value
                    check(f'{layout}/{version}/{language}/{fixture.stem}/expected', lambda v=value, w=wanted: equal(v, w))
                check(f'{layout}/{version}/{fixture.stem}/language', lambda v=values: equal(v['csharp'], v['rust']))
        check(f'{layout}/{version}/build-and-run', cell)

    for case in config['compatible_cases']:
        # These named cases explicitly promise compatibility across every configured cell.
        keys = [f'{l}/{v}/{lang}/{case}' for l, v, lang in itertools.product(layouts, versions, ['csharp', 'rust'])]
        for key in keys[1:]:
            check(f'compatibility/{keys[0]}={key}', lambda k=key, first=keys[0]: equal(outputs[first], outputs[k]))
    suite.set('tests', str(len(suite)))
    suite.set('failures', str(failures))
    report.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(report / 'junit.xml', encoding='utf-8', xml_declaration=True)
    (report / 'results.json').write_text(json.dumps(outputs, indent=2) + '\n')
    print(f'{len(suite)} checks; {failures} failures. Infrastructure smoke tests only.')
    return 1 if failures else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.exit(run(root, args.report or root / 'reports'))
