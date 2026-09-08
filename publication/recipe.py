"""Centrally authored, allowlisted six-stage GitHub trial exporter. No Git writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

def sha(data):
    return hashlib.sha256(data).hexdigest()

def export(source, output):
    demo = source / 'prototypes/skeletons/skeleton-1'
    recipe = Path(__file__).read_bytes()
    head = subprocess.check_output(['git', '-c', f'safe.directory={source.as_posix()}', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    profiles = json.loads((demo / 'evolution/profiles.json').read_text())
    workflow_path = next((source / '.github/workflows').glob('*.yml'))
    workflow = workflow_path.read_text().replace('prototypes/skeletons/skeleton-1/', '')
    workflow = workflow.replace('      - uses: actions/upload-artifact@v4', '      - name: Publish coverage summary\n        if: always()\n        run: python tools/ci_summary.py\n      - uses: actions/upload-artifact@v4')
    for number in range(1, 7):
        stage = output / f'stage-{number}'
        if stage.exists():
            raise ValueError(f'Destination already exists: {stage}')
        selected = profiles['profiles'][:number]
        files = {}
        hashes = {}
        def take(relative):
            data = (demo / relative).read_bytes()
            files[relative] = data.replace(b'\r\n', b'\n')
            hashes['prototypes/skeletons/skeleton-1/' + relative] = sha(data)
        for relative in ['tools/evolution.py', 'tools/evolution_scaffold.py', 'tools/test_evolution.py', 'tools/parity.py', 'tools/test_parity.py', 'evolution/templates/Adapter.cs', 'evolution/templates/adapter.rs', 'evolution/fixtures/corpus.json']:
            take(relative)
        harness = files['tools/evolution.py'].decode('utf-8')
        harness = harness.replace("cellbase=('horizontal','3.3.0')", "cellbase=('horizontal',json.loads((ROOT/'evolution/profiles.json').read_text())['profiles'][-1]['version'])")
        harness = harness.replace('Not all 24 adapters built; coverage incomplete', 'Not all required adapters built; coverage incomplete')
        files['tools/evolution.py'] = harness.encode()
        files['evolution/profiles.json'] = (json.dumps({**profiles, 'profiles': selected}, indent=2)+'\n').encode()
        hashes['prototypes/skeletons/skeleton-1/evolution/profiles.json'] = sha((demo/'evolution/profiles.json').read_bytes())
        for profile in selected:
            version = profile['version']
            for layout in ['horizontal','vertical']:
                base = demo/layout/version
                for path in base.rglob('*'):
                    if path.is_file() and not any(p in {'bin','obj','target','__pycache__','reports'} for p in path.relative_to(base).parts):
                        take(path.relative_to(demo).as_posix())
        files['tools/ci_summary.py'] = SUMMARY.encode()
        files['.github/workflows/evolution.yml'] = workflow.encode()
        files['.gitignore'] = b'**/bin/\n**/obj/\n**/target/\n**/__pycache__/\nreports/\n'
        files['.gitattributes'] = b'* text eol=lf\n'
        files['publication/recipe.py'] = recipe
        version = selected[-1]['version']
        date = selected[-1]['date']
        rows = '\n'.join(f"| {p['version']} | {p['date']} | {p['adds']} |" for p in selected)
        files['README.md'] = f'''# Reconstructed C# / Rust table trial

Stage {number}/6: **{version}**, demonstration date **{date}**.
These dates and versions are simulated, not verified historical releases.
Git commit timestamps record the actual publication time.

| Version | Demonstration month | Added capability |
|---|---|---|
{rows}

This stage contains {number*4} independent C#/Rust bindings in horizontal and
vertical layouts, with {number*4*number*4} required directed source-to-target pairs.
GitHub Actions runs 16 environments: Linux/Windows, .NET 8/10, Debug/Release,
and Rust 1.85/stable. Each environment uses 1,000 valid and 1,000 invalid seeded
inputs, fixed golden cases, return trips, available-version chains and mutation checks.
Cross-version pairs use accepted fixed fixture outputs; random cases exercise
local normalization and same-version language/layout parity.

## Run and inspect

Install Python 3.10+, .NET 8 SDK/runtime and Rust 1.85+ with a linker.

```sh
python tools/evolution_scaffold.py --check
python -m unittest discover -s tools -p 'test_*.py'
python tools/evolution.py --samples 1000
python tools/ci_summary.py
```

Open Actions, select this commit's run, then select an environment job. Its
summary shows expected/executed pairs, assertions, failures, seed and toolchains.
Download the environment artifact for summary.json, coverage.json, junit.xml,
failures.json, compatibility-losses.json and build logs. Missing coverage fails CI.
Change --seed to reproduce or explore inputs; failures.json records expected/actual
values and available input context. Build failures may be reported in failures.json
before a per-build log exists. Hosted status must be checked; this README claims no pass.

## Ownership and scope

Generated from the private central source. Changes belong in that source and
must be regenerated. publication/provenance.json records source identity and
input hashes; publication/recipe.py is the exact exporter. Run it with
--source PRIVATE_CHECKOUT --output NEW_DIRECTORY to regenerate all stages.
The recipe generates files locally and performs no Git operations that change state.

This tests reconstructed JSON table interchange and normalization. It does not
certify production bindings, XLSX fidelity, formula evaluation or browser rendering.
Private heritage, internal documents and Git history are not part of this export.
'''.encode()
        hashes[workflow_path.relative_to(source).as_posix()] = sha(workflow_path.read_bytes())
        provenance = {'schema':1, 'reconstructed':True, 'stage':number, 'version':version, 'demonstration_date':date, 'source_commit':head, 'source_capture':'working-tree bytes verified by input hashes; exporter is a new central file', 'recipe_sha256':sha(recipe), 'source_files_sha256':hashes, 'files_sha256':{k:sha(v) for k,v in files.items()}}
        files['publication/provenance.json'] = (json.dumps(provenance,indent=2)+'\n').encode()
        for relative,data in files.items():
            target = stage/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
        print(f'{stage}: {len(files)} files, {number*4} bindings, {(number*4)**2} directed pairs')

SUMMARY = r'''"""Verify actual pair coverage and publish an Actions job summary."""
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
report = root/'reports/evolution'
profiles = json.loads((root/'evolution/profiles.json').read_text())['profiles']
bindings = [f"{layout}/{p['version']}/{language}" for layout in ['horizontal','vertical'] for p in profiles for language in ['csharp','rust']]
expected = {a+' -> '+b for a in bindings for b in bindings}
actual = {}
summary = {}
error = None
try:
    summary = json.loads((report/'summary.json').read_text())
    for _, case in ET.iterparse(report/'junit.xml', events=['end']):
        if case.tag != 'testcase':
            continue
        if case.get('classname') == 'all-version-pairs':
            pair = case.get('name').rsplit('/',1)[0]
            cell = actual.setdefault(pair, {'checks':0,'failures':0})
            cell['checks'] += 1
            cell['failures'] += int(case.find('failure') is not None)
        case.clear()
except Exception as exc:
    error = str(exc)
missing = sorted(expected-set(actual))
unexpected = sorted(set(actual)-expected)
passed = not error and not missing and not unexpected and summary.get('failures') == 0
coverage = {'expected_pairs':len(expected),'executed_pairs':len(actual),'missing':missing,'unexpected':unexpected,'pairs':actual,'passed':passed,'error':error,'commit':os.getenv('GITHUB_SHA')}
report.mkdir(parents=True,exist_ok=True)
(report/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
text = '\n'.join(['## Compatibility results',f"Commit: {os.getenv('GITHUB_SHA','local')}",f"Stage: {profiles[-1]['version']} ({profiles[-1]['date']}, simulated)",f"Result: {'PASS' if passed else 'FAIL'}",f"Directed pairs: {len(actual)}/{len(expected)}; missing: {len(missing)}",f"Assertions: {summary.get('checks','unavailable')}; failures: {summary.get('failures','unavailable')}",f"Seed: {summary.get('seed','unavailable')}",'```json',json.dumps(summary,indent=2),'```','Download this job artifact for individual checks, pair coverage and failure details.'])+'\n'
print(text)
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as stream:
        stream.write(text)
raise SystemExit(0 if passed else 1)
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    export(args.source.resolve(), args.output.resolve())
