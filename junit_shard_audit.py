"""Find duplicate testcase identities in local JUnit XML shards."""

import json
import os
import posixpath
import re
import stat
import sys
from xml.parsers import expat


MAX_SHARDS = 32
MAX_SHARD_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_CASES = 10_000
STRUCTURE = {"testsuites", "testsuite", "testcase"}
ALLOWED_CHILDREN = {
    "testsuites": {"testsuite"},
    "testsuite": {"testsuite", "testcase"},
}
MARKUP_START = re.compile(rb"<!--|<!\[CDATA\[|<\?|<!DOCTYPE|<!ENTITY")
OPAQUE_END = {b"<!--": b"-->", b"<![CDATA[": b"]]>", b"<?": b"?>"}
DEVICE = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]")
NATIVE_ROOTS = {"??", "device", "dosdevices", "global??", "systemroot", "globalroot"}
USAGE = """usage: python -I junit_shard_audit.py [--] SHARD.xml [SHARD.xml ...]

Audit 1 to 32 local JUnit XML shards for duplicate (classname, name) pairs.
Exit 0 for no collisions, 1 for collisions, or 2 for invalid input.
"""


class InvalidShard(ValueError):
    """An input error with a diagnostic that contains no input text."""


def check_path(path):
    spelling = path.replace("\\", "/")
    if not spelling or spelling == "-" or spelling.startswith("//") or spelling.endswith("/"):
        raise InvalidShard("invalid_input")
    if any(ord(char) < 32 for char in spelling):
        raise InvalidShard("invalid_input")
    if spelling.startswith("/"):
        for version in (spelling, posixpath.normpath(spelling)):
            root = version[1:].partition("/")[0].rstrip(" .").lower()
            if root in NATIVE_ROOTS:
                raise InvalidShard("invalid_input")
    tail = spelling[2:] if re.match(r"^[A-Za-z]:/", spelling) else spelling
    if ":" in tail:
        raise InvalidShard("invalid_input")
    for part in tail.split("/"):
        if part in {"", ".", ".."}:
            continue
        stem = part.partition(".")[0].rstrip(" ").upper()
        if part.endswith((" ", ".")) or DEVICE.fullmatch(stem):
            raise InvalidShard("invalid_input")


def check_file(info, limit):
    if not stat.S_ISREG(info.st_mode):
        raise InvalidShard("invalid_input")
    if info.st_size > limit:
        raise InvalidShard("byte_limit")


def read_shard(path, limit):
    check_path(path)
    check_file(os.stat(path), limit)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        check_file(os.fstat(descriptor), limit)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
    finally:
        os.close(descriptor)
    if len(data) > limit:
        raise InvalidShard("byte_limit")
    return data


def check_xml_bytes(data):
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidShard("unsupported_encoding") from None
    if b"\x00" in data:
        raise InvalidShard("unsupported_encoding")

    # XML declaration markers in comments, CDATA, and PIs are literal text.
    match = MARKUP_START.search(data)
    while match is not None:
        closing = OPAQUE_END.get(match.group())
        if closing is None:
            raise InvalidShard("prohibited_declaration")
        end = data.find(closing, match.end())
        if end == -1:
            raise InvalidShard("invalid_xml")
        match = MARKUP_START.search(data, end + len(closing))


def record_cases(data, shard, remaining_cases, identities):
    check_xml_bytes(data)
    contexts = []
    case = 0

    def start_element(tag, attrs):
        nonlocal case
        if not contexts:
            if tag not in ALLOWED_CHILDREN:
                raise InvalidShard("unsupported_structure")
            contexts.append(tag)
            return

        parent = contexts[-1]
        if parent not in ALLOWED_CHILDREN or tag.rpartition("}")[2] not in STRUCTURE:
            contexts.append(None)
            return
        if tag not in ALLOWED_CHILDREN[parent]:
            raise InvalidShard("unsupported_structure")
        contexts.append(tag)
        if tag == "testcase":
            case += 1
            if case > remaining_cases:
                raise InvalidShard("case_limit")
            classname, name = attrs.get("classname"), attrs.get("name")
            if not classname or not name:
                raise InvalidShard(f"case={case} invalid_identity")
            identities.setdefault((classname, name), []).append((shard, case))

    def check_declaration(_version, encoding, _standalone):
        if encoding is not None and encoding.lower() != "utf-8":
            raise InvalidShard("unsupported_encoding")

    parser = expat.ParserCreate(encoding="UTF-8", namespace_separator="}")
    parser.XmlDeclHandler = check_declaration
    parser.StartElementHandler = start_element
    parser.EndElementHandler = lambda _tag: contexts.pop()
    try:
        parser.Parse(data, True)
    except expat.ExpatError:
        raise InvalidShard("invalid_xml") from None
    return case


def audit(paths):
    total_bytes = 0
    total_cases = 0
    cases_per_shard = []
    identities = {}
    for shard, path in enumerate(paths, 1):
        try:
            data = read_shard(path, min(MAX_SHARD_BYTES, MAX_TOTAL_BYTES - total_bytes))
            count = record_cases(data, shard, MAX_CASES - total_cases, identities)
        except OSError:
            raise InvalidShard(f"shard={shard} invalid_input") from None
        except InvalidShard as error:
            raise InvalidShard(f"shard={shard} {error}") from None
        total_bytes += len(data)
        total_cases += count
        cases_per_shard.append(count)

    groups = []
    cross_shard = 0
    excess = 0
    # Dict insertion order is first encounter order. Each location list is already sorted.
    for locations in identities.values():
        if len(locations) < 2:
            continue
        cross_shard += locations[0][0] != locations[-1][0]
        excess += len(locations) - 1
        groups.append([{"shard": shard, "case": case} for shard, case in locations])
    return {
        "cases_per_shard": cases_per_shard,
        "duplicate_group_count": len(groups),
        "cross_shard_group_count": cross_shard,
        "excess_record_count": excess,
        "duplicate_groups": groups,
    }


def emit(descriptor, output, status):
    remaining = memoryview(output.encode("ascii"))
    try:
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                return 2
            remaining = remaining[written:]
    except OSError:
        return 2
    return status


def main(args):
    if args in (["-h"], ["--help"]):
        return emit(1, USAGE, 0)

    separator = args.index("--") if "--" in args else len(args)
    paths = args[:separator] + args[separator + 1:]
    try:
        if any(arg.startswith("-") and arg != "-" for arg in args[:separator]):
            raise InvalidShard("unknown option")
        if not 1 <= len(paths) <= MAX_SHARDS:
            raise InvalidShard(f"expected 1 to {MAX_SHARDS} shard paths")
        report = audit(paths)
    except InvalidShard as error:
        return emit(2, f"error {error}\n", 2)

    output = json.dumps(report, separators=(",", ":")) + "\n"
    return emit(1, output, int(report["duplicate_group_count"] > 0))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
