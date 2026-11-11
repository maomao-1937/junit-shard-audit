# Tests

From the repository root, run both commands with Python 3.11 or later.

```sh
python -I -m unittest discover -s tests -v
python -I examples/run_examples.py
```

The CLI suite checks exact XML attribute identity, deterministic ordinal order, result element handling, namespace and structure rules, byte and case limits, input errors, and closed output pipes. The FIFO case is POSIX-only. The example runner checks the exit code, stdout and stderr for every fixture invocation in [checks.json](checks.json).

## Run an individual example

| Command | Expected exit |
| --- | --- |
| `python -I junit_shard_audit.py examples/shard-b.xml examples/shard-c.xml` | 0 |
| `python -I junit_shard_audit.py examples/shard-a.xml examples/shard-b.xml` | 1 |
| `python -I junit_shard_audit.py examples/shard-a.xml` | 1 |
| `python -I junit_shard_audit.py examples/shard-b.xml examples/missing-identity.xml` | 2 |
| `python -I junit_shard_audit.py examples/with-doctype.xml` | 2 |
