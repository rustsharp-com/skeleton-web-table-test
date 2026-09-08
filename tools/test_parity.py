import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import parity


class RunnerTests(unittest.TestCase):
    def test_strict_values(self):
        self.assertFalse(parity.same({'value': True}, {'value': 1}))
        self.assertFalse(parity.same([1], [1, 2]))
        self.assertTrue(parity.same({'b': 2, 'a': 1}, {'a': 1, 'b': 2}))
        for value in ['NaN', '{"a":1,"a":2}', '1 trailing']:
            with self.assertRaises(ValueError):
                parity.read_json(value)

    def scenario(self, *, mismatch=False, missing=False, crash=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'parity.json').write_text(json.dumps(dict(layouts=['horizontal'], versions=['1.0.0'], framework='net9.0', compatible_cases=['one'])))
            adapter = root / 'horizontal/1.0.0/smoke'
            for folder in ['fixtures', 'expected']:
                (adapter / folder).mkdir(parents=True)
            if not missing:
                (adapter / 'fixtures/one.json').write_text('1')
                (adapter / 'expected/one.json').write_text('{"value":-1}')
            def execute(command, *, data=None):
                if crash:
                    raise RuntimeError('adapter or build failed')
                return json.dumps({'value': 99 if mismatch else -1}) if data else ''
            with patch.object(parity, 'execute', side_effect=execute), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = parity.run(root, root / 'reports')
            report = ET.parse(root / 'reports/junit.xml').getroot()
            return status, int(report.get('failures'))

    def test_matching_results_pass(self):
        self.assertEqual(self.scenario(), (0, 0))

    def test_both_languages_wrong_still_fail(self):
        status, failures = self.scenario(mismatch=True)
        self.assertEqual(status, 1)
        self.assertGreater(failures, 0)

    def test_empty_fixtures_fail(self):
        self.assertEqual(self.scenario(missing=True)[0], 1)

    def test_execution_failure_is_reported(self):
        self.assertEqual(self.scenario(crash=True)[0], 1)


if __name__ == '__main__':
    unittest.main()
