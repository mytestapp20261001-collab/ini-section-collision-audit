import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(HERE.name.replace("-", "_"), HERE / "tool.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

class CommonTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "tool.py"), *args], cwd=HERE,
                              capture_output=True, text=True, timeout=10)
    def test_cli_pass(self):
        result = self.cli("examples/" + PASS, *ARGS)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")
        self.assertEqual(result.stderr, "")
    def test_cli_fail(self):
        result = self.cli("examples/" + FAIL, *ARGS)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "fail")
    def test_cli_malformed(self):
        result = self.cli("examples/" + MALFORMED, *ARGS)
        self.assertEqual(result.returncode, MALFORMED_CODE, result.stdout + result.stderr)
        self.assertIn(json.loads(result.stdout)["status"], ("fail", "error"))
    def test_cli_missing_file(self):
        result = self.cli("nonexistent-input", *ARGS)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], "unreadable_utf8_input")
    def test_cli_invalid_arguments_are_redacted(self):
        result = self.cli("--unrecognized-secret-value")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], "invalid_arguments")
        self.assertNotIn("unrecognized-secret-value", result.stdout + result.stderr)
    def test_cli_help(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
    def test_cli_stability(self):
        a = self.cli("examples/" + FAIL, *ARGS)
        b = self.cli("examples/" + FAIL, *ARGS)
        self.assertEqual(a.stdout, b.stdout)
    def test_file_limit_and_utf8(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"x" * (tool.MAX_BYTES + 1))
            with self.assertRaises(tool.InputError):
                tool.read_text(path)
            path.write_bytes(b"\xff")
            with self.assertRaises(UnicodeDecodeError):
                tool.read_text(path)
    def test_json_parser_safety(self):
        for text in ('{"x":1,"x":2}', '[NaN]', '[' * 130 + '0' + ']' * 130):
            with self.subTest(text=text[:20]), self.assertRaises(tool.InputError):
                tool.parse_json(text)
    def test_report_cap_preserves_count(self):
        report = tool.Report("test")
        for i in range(101):
            report.add("sample", record=i)
        result = report.finish()
        self.assertEqual(len(result["findings"]), 100)
        self.assertEqual(result["summary"]["finding_count"], 101)
        self.assertTrue(result["findings_truncated"])

    def test_adversarial_cli_and_read_only_corpus(self):
        samples = ['', 'null', 'true', '0', '[]', '{}', '[null]', '[true]', '[1]',
                   '["NaN"]', '[{}]', '[[]]', '{"x":1,"x":2}',
                   '[1e99999999999999999999999999]', '[NaN]', '[Infinity]',
                   '"\\ud800"', '["\\ud800"]', '{', '[', '["a","b"]',
                   '[1e-99999999999999999999999999]']
        before = {path: path.read_bytes() for path in (HERE / 'examples').iterdir()}
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / 'input.txt'
            for sample in samples:
                with self.subTest(sample=sample):
                    path.write_text(sample, encoding='utf-8')
                    result = self.cli(str(path), *ARGS)
                    self.assertIn(result.returncode, (0, 1, 2), result.stderr)
                    self.assertEqual(result.stderr, '')
                    self.assertIn(json.loads(result.stdout)['status'], ('pass','fail','error'))
                    self.assertEqual(path.read_text(encoding='utf-8'), sample)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

PASS = 'pass.ini'
FAIL = 'fail.ini'
MALFORMED = 'malformed.ini'
MALFORMED_CODE = 2
ARGS = []

class AuditTests(unittest.TestCase):
    def test_case_sensitive_default(self): self.assertEqual(tool.audit('[A]\nX=1\nx=2\n[a]\nx=3')['status'],'pass')
    def test_key_casefold(self):
        result=tool.audit('[x]\nStraße=1\nSTRASSE=2',key_case='fold')
        self.assertEqual(result['findings'][0]['code'],'duplicate_key')
    def test_section_casefold(self): self.assertEqual(tool.audit('[A]\nx=1\n[a]\nx=2',section_case='fold')['summary']['finding_count'],2)
    def test_duplicate_section_accumulates_keys(self):
        result=tool.audit('[a]\nx=1\n[a]\nx=2')
        self.assertEqual(result['findings'][1]['first_line'],2)
    def test_comments_and_delimiters(self):
        result=tool.audit('# comment\n; comment\n[a]\nx: a=b\ny= # literal\nz=')
        self.assertEqual(result['summary']['key_assignments'],3)
    def test_interpolation_is_not_evaluated(self):
        self.assertEqual(tool.audit('[a]\nx=%(missing)s')['status'],'pass')
    def test_no_default_inheritance(self):
        self.assertEqual(tool.audit('[DEFAULT]\nx=1\n[a]\nx=2')['status'],'pass')
    def test_multiline_rejected(self):
        with self.assertRaises(tool.InputError): tool.audit('[a]\nx=1\n continuation')
    def test_malformed(self):
        for text in ('','[]','[a] #comment','[a]\n=empty','outside=1','[a]\nno delimiter'):
            with self.assertRaises(tool.InputError): tool.audit(text)
    def test_count_limit(self):
        previous=tool.MAX_RECORDS
        try:
            tool.MAX_RECORDS=1
            with self.assertRaises(tool.InputError): tool.audit('[a]\nx=1')
        finally: tool.MAX_RECORDS=previous
    def test_values_redacted(self):
        self.assertNotIn('SUPERSECRET',json.dumps(tool.audit('[a]\nx=SUPERSECRET\nx=other')))

    def test_full_line_limit_accepts_terminal_lf(self):
        text = '[x]\n' + '# comment\n' * 49998 + 'key=value'
        for ending in ('', '\n'):
            with self.subTest(ending=repr(ending)):
                self.assertEqual(tool.audit(text + ending)['status'], 'pass')

    def test_line_limit_counts_real_blank_lines(self):
        text = '[x]\n' + '\n' * 49999
        self.assertEqual(tool.audit(text)['status'], 'pass')
        with self.assertRaisesRegex(tool.InputError, 'line_count_limit'):
            tool.audit(text + '\n')

    def test_terminal_crlf_counts_once(self):
        text = '[x]\r\n' + '# comment\r\n' * 49998 + 'key=value\r\n'
        self.assertEqual(tool.audit(text)['status'], 'pass')

if __name__ == '__main__': unittest.main()
