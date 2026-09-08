import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import evolution


class EvolutionHarnessTests(unittest.TestCase):
    def test_booleans_are_not_numbers(self):
        self.assertNotEqual(evolution.semantic(True),evolution.semantic(1))
        self.assertEqual(evolution.semantic(1),evolution.semantic(1.0))
        self.assertNotEqual(evolution.semantic([1,2]),evolution.semantic([2,1]))

    def test_fixed_golden_policy_is_consistent(self):
        cases=json.loads((evolution.ROOT/'evolution/fixtures/corpus.json').read_text(encoding='utf-8'))
        for c in cases:
            for level,wanted in enumerate(c['expected']):
                if wanted.get('ok'):
                    self.assertEqual(evolution.project(c['table'],level),wanted,(c['id'],level))

    def test_nested_loss_is_not_root_preservation(self):
        value={'futureRoot':{'v':1},'columns':[{'header':'A','widthExpr':{'value':120}}]}
        out=evolution.project(value,3)
        self.assertEqual(out['lost'],['/columns/0/widthExpr'])
        self.assertEqual(out['table']['futureRoot'],{'v':1})
        self.assertEqual(evolution.project(value,5)['table'],value)
        self.assertNotIn('widthExpr',evolution.project(out['table'],5)['table']['columns'][0])

    def test_seed_reproduces_valid_and_invalid_cases(self):
        a=list(evolution.random_cases(123,5));b=list(evolution.random_cases(123,5))
        self.assertEqual(a,b);self.assertEqual(len(a),10)
        self.assertNotEqual(a,list(evolution.random_cases(124,5)))
        self.assertFalse(a[1]['expected'][5]['ok'])

    def test_truncated_adapter_output_is_a_failure(self):
        with patch.object(evolution,'command',return_value='{}\n'):
            with self.assertRaises(AssertionError):evolution.batch(['unused'],['{}','{}'])

    def test_malformed_adapter_output_is_a_failure(self):
        with patch.object(evolution,'command',return_value='not-json\n'):
            with self.assertRaises(ValueError):evolution.batch(['unused'],['{}'])

    def test_shared_wrong_answer_fails_golden(self):
        with tempfile.TemporaryDirectory()as tmp, contextlib.redirect_stdout(io.StringIO()):
            r=evolution.Report(Path(tmp))
            for lang in ['csharp','rust']:r.check('golden',lang,{'ok':True},{'ok':False,'error':'cell-type'})
            self.assertEqual(r.finish({}),1)
            self.assertEqual(ET.parse(Path(tmp)/'junit.xml').getroot().get('failures'),'2')

    def test_missing_generation_fails_and_writes_report(self):
        with tempfile.TemporaryDirectory()as tmp, patch.object(evolution,'sync',return_value=['missing']), patch.object(evolution,'command',return_value='test-toolchain'), contextlib.redirect_stdout(io.StringIO()):
            args=argparse.Namespace(report=Path(tmp),seed=1,samples=1,framework='net8.0',configuration='Release')
            self.assertEqual(evolution.run(args),1)
            self.assertTrue((Path(tmp)/'failures.json').exists())


if __name__=='__main__':unittest.main()
