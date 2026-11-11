# junit-shard-audit

[简体中文](#简体中文) · [Research](RESEARCH.md) · [Tests](TESTING.md)

Find repeated JUnit `(classname, name)` pairs in local test report shards before sending them to CI or an evaluator. A single run locates duplicates within a shard and across shards. The report uses only counts and ordinal positions, so you can share it without including test names or report paths.

## Install and run

Requires Python 3.11 or later and its standard library. Download or clone this repository and run the script from its root. For use in another project, copy `junit_shard_audit.py`.

Locally verified on Windows with CPython 3.11.15. The POSIX FIFO test is skipped on Windows.

```sh
python -I junit_shard_audit.py examples/shard-a.xml examples/shard-b.xml
```

The example exits with code 1 and writes this single JSON line to stdout.

```json
{"cases_per_shard":[4,2],"duplicate_group_count":2,"cross_shard_group_count":1,"excess_record_count":3,"duplicate_groups":[[{"shard":1,"case":1},{"shard":1,"case":4},{"shard":2,"case":1}],[{"shard":1,"case":2},{"shard":1,"case":3}]]}
```

The first duplicate identity occurs at cases 1 and 4 of the first shard and case 1 of the second shard. The other occurs twice within the first shard.

| Field | Meaning |
| --- | --- |
| `cases_per_shard` | Count for each input path in argument order. |
| `duplicate_group_count` | Number of identities with at least two records. |
| `cross_shard_group_count` | Number of duplicate groups spanning two or more argument positions. |
| `excess_record_count` | Sum of `group size - 1` across duplicate groups. |
| `duplicate_groups` | Ordinal locations sorted by shard then case, with groups sorted by their first location. |

Both ordinals start at 1. Case ordinals follow XML document order, including eligible cases inside nested suites. Repeating an input path counts as a separate shard.

| Exit | Stdout | Stderr |
| --- | --- | --- |
| 0 | One JSON line with an empty `duplicate_groups` array | Empty |
| 1 | One JSON line with one or more duplicate groups | Empty |
| 2 | Empty | One diagnostic line |

For example, `python -I junit_shard_audit.py examples/shard-b.xml examples/missing-identity.xml` exits 2 and writes `error shard=2 case=1 invalid_identity` to stderr. Other input diagnostics use `error shard=N CODE`, with `invalid_input`, `byte_limit`, `unsupported_encoding`, `prohibited_declaration`, `invalid_xml`, `unsupported_structure`, or `case_limit`. Argument errors use `error expected 1 to 32 shard paths` or `error unknown option`. Standalone `--help` or `-h` prints help and exits 0.

If writing to the required output stream fails, the CLI exits 2. A stream that closes mid-write can receive a partial line.

## Supported input and limits

- Pass 1–32 local regular-file paths in positional order, with up to 2 MiB per file and 16 MiB total, including any BOM. Use `--` before a path that begins with a dash. The CLI checks the contents as XML regardless of file extension. It rejects stdin and common URL, UNC and Windows device spellings. The operating system resolves links and mounts, so use a trusted local filesystem.
- Each file must be well-formed UTF-8 XML. A single leading UTF-8 BOM is optional. An XML encoding declaration, when present, must be `UTF-8` (case-insensitive). DTD and entity declarations are rejected before XML parsing. XML's built-in and numeric character references are supported.
- The root must be an unnamespaced `<testsuites>` or `<testsuite>`. A `<testsuites>` container accepts suites. Each suite accepts direct cases and nested suites. A namespaced or misplaced `testsuites`, `testsuite`, or `testcase` element directly under a recognized container is rejected. Other child elements, such as `properties`, `system-out`, and extensions, are ignored with their subtrees. The contents of each recognized case are ignored.
- Every counted case needs unnamespaced, nonempty `classname` and `name` attributes. Identity uses the parsed XML attribute values exactly, preserving case, spaces and Unicode distinctions after XML attribute normalization. Suite names, testcase metadata and result children have no role in identity.
- At most 10,000 cases are accepted across all shards. Exceeding a limit is an input error. A valid report includes every duplicate location.

The CLI reads the supplied files as-is and reports identity collisions. The same identity can come from distinct logical tests, repeated execution, or a reporting error. Inspect the producer's metadata to establish the cause.

## 简体中文

在把 JUnit XML 报告交给 CI 或评测器之前，检查分片中重复的 `(classname, name)`。工具同时检查单个分片内和多个分片间的重复。输出只包含计数和序号，便于分享。

### 安装与使用

需要 Python 3.11 或更新版本，使用标准库。下载或克隆仓库，在仓库根目录运行。也可以把 `junit_shard_audit.py` 复制到其他项目。

已在 Windows 上用 CPython 3.11.15 验证。POSIX FIFO 测试在 Windows 上跳过。

```sh
python -I junit_shard_audit.py examples/shard-a.xml examples/shard-b.xml
```

该命令以状态码 1 退出，标准输出为以下一行。

```json
{"cases_per_shard":[4,2],"duplicate_group_count":2,"cross_shard_group_count":1,"excess_record_count":3,"duplicate_groups":[[{"shard":1,"case":1},{"shard":1,"case":4},{"shard":2,"case":1}],[{"shard":1,"case":2},{"shard":1,"case":3}]]}
```

第一组重复出现在第一个分片的第 1、4 条用例和第二个分片的第 1 条用例。另一组在第一个分片内出现两次。

| 字段 | 含义 |
| --- | --- |
| `cases_per_shard` | 按参数顺序记录每个分片的用例数。 |
| `duplicate_group_count` | 出现至少两次的用例标识数量。 |
| `cross_shard_group_count` | 出现在至少两个分片参数位置的重复组数。 |
| `excess_record_count` | 各重复组的记录数减一后求和。 |
| `duplicate_groups` | 组内按分片序号、用例序号排序，各组按首个位置排序。 |

两种序号均从 1 开始。用例按 XML 文档顺序编号，包含嵌套套件中的有效用例。同一路径作为多个参数传入时，各参数位置分别计为一个分片。

| 退出码 | 标准输出 | 标准错误 |
| --- | --- | --- |
| 0 | 一行 JSON，`duplicate_groups` 为空数组 | 空 |
| 1 | 一行 JSON，包含至少一个重复组 | 空 |
| 2 | 空 | 一行诊断 |

例如，运行 `python -I junit_shard_audit.py examples/shard-b.xml examples/missing-identity.xml` 会以 2 退出，诊断为 `error shard=2 case=1 invalid_identity`。其他输入错误采用 `error shard=N CODE` 格式，错误码包括 `invalid_input`、`byte_limit`、`unsupported_encoding`、`prohibited_declaration`、`invalid_xml`、`unsupported_structure`、`case_limit`。参数错误为 `error expected 1 to 32 shard paths` 或 `error unknown option`。单独传入 `--help` 或 `-h` 会显示帮助并以 0 退出。

需要写入的输出流写入失败时，程序以 2 退出。输出流如果在写入过程中关闭，可能只收到一行的部分内容。

### 输入范围与限制

- 按位置传入 1–32 个本地普通文件。每个文件最多 2 MiB，合计最多 16 MiB，包含 BOM。路径以连字符开头时，在其前面加 `--`。程序按 XML 内容解析，不限制文件扩展名。程序拒绝标准输入和常见的 URL、UNC 及 Windows 设备路径写法。链接和挂载点由操作系统解析，请使用可信的本地文件系统。
- 文件必须是格式良好的 UTF-8 XML，允许开头有一个 UTF-8 BOM。编码声明若存在，必须是 `UTF-8`，大小写均可。DTD 和实体声明会在 XML 解析前被拒绝。支持 XML 内置实体引用及数字字符引用。
- 根元素必须是不带命名空间的 `<testsuites>` 或 `<testsuite>`。`<testsuites>` 下可放套件，套件下可直接放用例或嵌套套件。受支持容器的直属子元素如果是带命名空间或位置错误的 `testsuites`、`testsuite`、`testcase`，程序会报错。其他子元素连同其子树会被忽略，例如 `properties`、`system-out` 和扩展元素。用例内部的内容也会被忽略。
- 每条计入的用例都必须有无命名空间且非空的 `classname`、`name`。比较使用 XML 解析后的属性值，保留 XML 属性规范化之后的大小写、空格和 Unicode 差异。套件名、用例元数据和结果元素均不参与标识比较。
- 所有分片合计最多 10,000 条用例。超过任一上限会报输入错误。有效报告列出所有重复位置。

工具读取原始文件并报告标识重复的位置。重复可能来自不同的逻辑用例、多次执行或报告生成问题，具体原因需要结合报告生成器的元数据判断。

## License

[MIT](LICENSE)
