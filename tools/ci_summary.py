"""Verify actual pair coverage and publish an Actions job summary."""
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
