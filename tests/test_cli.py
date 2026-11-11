import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "junit_shard_audit.py"
FILE_LIMIT = 2 * 1024 * 1024


def location(shard, case):
    return {"shard": shard, "case": case}


def report(counts, groups=(), cross_shard=0, excess=0):
    return {
        "cases_per_shard": counts,
        "duplicate_group_count": len(groups),
        "cross_shard_group_count": cross_shard,
        "excess_record_count": excess,
        "duplicate_groups": list(groups),
    }


class AuditCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def shard(self, name, xml):
        path = self.directory / name
        path.write_bytes(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
        return path

    def run_audit(self, *args):
        return subprocess.run(
            [sys.executable, "-I", SCRIPT, *args],
            cwd=self.directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    def run_with_closed_output(self, stream, *args):
        read_end, write_end = os.pipe()
        os.close(read_end)
        streams = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        streams[stream] = write_end
        try:
            return subprocess.run(
                [sys.executable, "-I", SCRIPT, *args],
                cwd=self.directory,
                timeout=15,
                **streams,
            )
        finally:
            os.close(write_end)

    def assert_report(self, result, status, expected):
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(json.loads(result.stdout), expected)

    def assert_invalid(self, result, diagnostic):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, f"error {diagnostic}\n")

    def test_empty_suite_and_container(self):
        first = self.shard("one.xml", "<testsuite/>")
        second = self.shard("two.xml", "<testsuites/>")
        self.assert_report(self.run_audit(first, second), 0, report([0, 0]))

    def test_exact_tuple_includes_spaces_case_and_unicode(self):
        shard = self.shard(
            "private-path.xml",
            '<testsuite><testcase classname="Classe" name="café"/>'
            '<testcase classname="Classe" name="café "/>'
            '<testcase classname="Classe" name="Cafe"/>'
            '<testcase classname="classe" name="café"/>'
            '<testcase classname="Classe" name=" "/>'
            '<testcase classname="A|B" name="C"/>'
            '<testcase classname="A" name="B|C"/>'
            '<testcase classname="Classe" name="cafe&#x301;"/></testsuite>',
        )
        self.assert_report(self.run_audit(shard), 0, report([8]))

    def test_document_order_and_group_order_use_first_location(self):
        first = self.shard(
            "private-first.xml",
            '<testsuites><testsuite name="Private suite">'
            '<testcase classname="Z private" name="private-one"/>'
            '<testsuite><testcase classname="A private" name="private-two"/>'
            '<testcase classname="A private" name="private-two"><failure/></testcase>'
            '</testsuite><testcase classname="Z private" name="private-one"><skipped/>'
            '</testcase></testsuite></testsuites>',
        )
        second = self.shard(
            "private-second.xml",
            '<testsuite name="Other suite"><testcase classname="Z private" '
            'name="private-one" file="private/location.py"><error/></testcase></testsuite>',
        )
        self.assert_report(
            self.run_audit(first, second),
            1,
            report(
                [4, 1],
                [[location(1, 1), location(1, 4), location(2, 1)], [location(1, 2), location(1, 3)]],
                cross_shard=1,
                excess=3,
            ),
        )

    def test_repeated_path_is_two_input_shards(self):
        shard = self.shard("one.xml", '<testsuite><testcase classname="X" name="x"/></testsuite>')
        self.assert_report(
            self.run_audit(shard, shard),
            1,
            report([1, 1], [[location(1, 1), location(2, 1)]], cross_shard=1, excess=1),
        )

    def test_ignored_subtrees_do_not_contribute_cases(self):
        shard = self.shard(
            "one.xml",
            '<testsuites xmlns:e="urn:extension"><extension><testsuite>'
            '<testcase/></testsuite></extension><testsuite tests="999">'
            '<e:metadata><testcase/></e:metadata><testcase classname="A" name="B">'
            '<testcase/><failure>private output</failure></testcase><system-out>'
            '<testcase/></system-out></testsuite></testsuites>',
        )
        self.assert_report(self.run_audit(shard), 0, report([1]))

    def test_wrong_root_or_structural_namespace_or_parent_is_rejected(self):
        inputs = (
            "<testcase/>",
            '<testsuite xmlns="urn:unsupported"/>',
            "<testsuites><testcase/></testsuites>",
            "<testsuite><testsuites/></testsuite>",
            '<testsuite xmlns:x="urn:unsupported"><x:testcase/></testsuite>',
        )
        for xml in inputs:
            with self.subTest(xml=xml):
                shard = self.shard("private.xml", xml)
                self.assert_invalid(self.run_audit(shard), "shard=1 unsupported_structure")

    def test_xml_entities_resolve_before_exact_identity_comparison(self):
        shard = self.shard(
            "one.xml",
            '<testsuite><testcase classname="A&amp;B" name="café"/>'
            '<testcase classname="A&#38;B" name="caf&#233;"/></testsuite>',
        )
        self.assert_report(
            self.run_audit(shard), 1, report([2], [[location(1, 1), location(1, 2)]], excess=1)
        )

    def test_missing_or_empty_identity_reports_ordinal_without_partial_json(self):
        good = self.shard("one.xml", "<testsuite/>")
        for attributes in ('name="private"', 'classname="" name="private"', 'classname="private"', 'classname="private" name=""'):
            with self.subTest(attributes=attributes):
                bad = self.shard(
                    "private.xml",
                    '<testsuite><testcase classname="A" name="B"/>'
                    f"<testcase {attributes}/></testsuite>",
                )
                self.assert_invalid(self.run_audit(good, bad), "shard=2 case=2 invalid_identity")

    def test_malformed_xml_is_rejected_even_after_duplicate(self):
        shard = self.shard(
            "private.xml",
            '<testsuite><testcase classname="A" name="B"/>'
            '<testcase classname="A" name="B"/><system-out>private data',
        )
        self.assert_invalid(self.run_audit(shard), "shard=1 invalid_xml")

    def test_utf8_bom_and_case_insensitive_declaration(self):
        shard = self.shard(
            "one.xml",
            '<?xml version="1.0" encoding=\'uTf-8\'?><testsuite>'
            '<testcase classname="Clasé" name="用例"/></testsuite>'.encode("utf-8-sig"),
        )
        self.assert_report(self.run_audit(shard), 0, report([1]))

    def test_utf16_invalid_utf8_and_alternate_declarations_are_rejected(self):
        inputs = (
            "<testsuite/>".encode("utf-16"),
            "<testsuite/>".encode("utf-16-le"),
            b"\xff<testsuite/>",
            b'<?xml version="1.0" encoding="UTF-16"?><testsuite/>',
            b'<?xml version="1.0" encoding="ISO-8859-1"?><testsuite/>',
            b'<?xml version="1.0" encoding="UTF8"?><testsuite/>',
            b'<?xml version="1.0" encoding="unknown-codec"?><testsuite/>',
        )
        for xml in inputs:
            with self.subTest(xml=xml):
                shard = self.shard("private.xml", xml)
                self.assert_invalid(self.run_audit(shard), "shard=1 unsupported_encoding")

    def test_double_utf8_bom_is_invalid_xml(self):
        shard = self.shard("one.xml", "\ufeff<testsuite/>".encode("utf-8-sig"))
        self.assert_invalid(self.run_audit(shard), "shard=1 invalid_xml")

    def test_dtd_and_entity_declarations_are_rejected(self):
        inputs = (
            "<!DOCTYPE testsuite><testsuite/>",
            '<!DOCTYPE testsuite SYSTEM "private.dtd"><testsuite/>',
            '<!DOCTYPE testsuite [<!ENTITY n "private">]><testsuite/>',
            '<!ENTITY n "private"><testsuite/>',
            '<testsuite><!DOCTYPE bogus></testsuite>',
        )
        for xml in inputs:
            with self.subTest(xml=xml):
                shard = self.shard("private.xml", xml)
                self.assert_invalid(self.run_audit(shard), "shard=1 prohibited_declaration")

    def test_declaration_spellings_in_comments_cdata_and_pi_are_inert(self):
        shard = self.shard(
            "one.xml",
            '<?before <!DOCTYPE testsuite>?>'
            '<testsuite><!-- <!ENTITY sample "x"> --><system-out>'
            '<![CDATA[<!DOCTYPE testsuite>]]></system-out></testsuite>',
        )
        self.assert_report(self.run_audit(shard), 0, report([0]))

    def test_file_and_aggregate_byte_caps_are_inclusive(self):
        empty_xml = b"<testsuite/>"
        content = empty_xml.ljust(FILE_LIMIT, b" ")
        exact = self.shard("exact.xml", content)
        oversized = self.shard("oversized-private.xml", content + b" ")
        small = self.shard("small.xml", empty_xml)
        self.assert_report(self.run_audit(*([exact] * 8)), 0, report([0] * 8))
        self.assert_invalid(self.run_audit(*([exact] * 8), small), "shard=9 byte_limit")
        self.assert_invalid(self.run_audit(oversized), "shard=1 byte_limit")

    def test_aggregate_case_cap_bounds_output_without_truncating(self):
        case = b'<testcase classname="A" name="B"/>'
        first = self.shard("one.xml", b"<testsuite>" + case * 9999 + b"</testsuite>")
        second = self.shard("two.xml", b"<testsuite>" + case + b"</testsuite>")
        result = self.run_audit(first, second)
        self.assert_report(
            result, 1, report(
                [9999, 1],
                [[location(1, index) for index in range(1, 10000)] + [location(2, 1)]],
                cross_shard=1,
                excess=9999,
            )
        )
        self.assertLess(len(result.stdout), 300 * 1024)
        self.assert_invalid(self.run_audit(first, second, second), "shard=3 case_limit")

    def test_deep_nested_suites_are_walked_in_document_order(self):
        shard = self.shard(
            "one.xml",
            "<testsuite>" * 1500 + '<testcase classname="A" name="B"/>' + "</testsuite>" * 1500,
        )
        self.assert_report(self.run_audit(shard), 0, report([1]))

    def test_argument_counts_options_and_double_dash(self):
        shard = self.shard("-hidden.xml", "<testsuite/>")
        self.assert_report(self.run_audit(*([shard] * 32)), 0, report([0] * 32))
        self.assert_invalid(self.run_audit(*([shard] * 33)), "expected 1 to 32 shard paths")
        self.assert_invalid(self.run_audit(), "expected 1 to 32 shard paths")
        self.assert_invalid(self.run_audit("--private-option"), "unknown option")
        self.assert_report(self.run_audit("--", shard.name), 0, report([0]))

    def test_help_does_not_read_input(self):
        result = self.run_audit("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SHARD.xml", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_help_with_closed_stdout_returns_invalid_status(self):
        result = self.run_with_closed_output("stdout", "--help")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.returncode, 2)

    def test_report_with_closed_stdout_returns_invalid_status(self):
        shard = self.shard("one.xml", "<testsuite/>")
        result = self.run_with_closed_output("stdout", shard)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.returncode, 2)

    def test_invalid_input_with_closed_stderr_returns_invalid_status(self):
        result = self.run_with_closed_output("stderr", "private-missing.xml")
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.returncode, 2)

    def test_missing_nonregular_and_nonlocal_paths_are_rejected(self):
        for path in (self.directory, "private-missing.xml", "//server/private.xml", "https://example.test/private.xml", "-"):
            with self.subTest(path=path):
                self.assert_invalid(self.run_audit(path), "shard=1 invalid_input")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires a POSIX FIFO")
    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        fifo = self.directory / "private.xml"
        os.mkfifo(fifo)
        self.assert_invalid(self.run_audit(fifo), "shard=1 invalid_input")
