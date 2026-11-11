# Why audit testcase identities

- GitLab documents that it keeps the first test when names are duplicated and associates unexpectedly low displayed counts with duplicate names. This motivates checking reports before artifact upload. [GitLab unit test reports](https://docs.gitlab.com/ci/testing/unit_test_reports/#test-results-are-missing)
- In October 2023 a Playwright user described a GitLab pipeline that combined results from five browser projects and displayed roughly a fifth of the expected case records. They attributed the reduction to repeated report names and also observed the issue in a run without sharding. This is a historical report from that setup. [Playwright #27665](https://github.com/microsoft/playwright/issues/27665)
- In September 2026 a ProgramBench issue supplied XML showing three records with the same `classname` and `name`. The reporter traced a score of 2/3 for an always-failing test to an evaluator counting two earlier rerun records as passes. [ProgramBench #64](https://github.com/facebookresearch/ProgramBench/issues/64)
- A September 2026 Gradle report shows two distinct parameterized test methods producing identical testcase pairs for shared argument values. [Gradle #39079](https://github.com/gradle/gradle/issues/39079)

The audit defines identity as the exact pair `(classname, name)` and covers both within-file and across-file collisions. Its output describes collisions visible in the supplied XML. The reports above illustrate that collision causes and consumer outcomes can differ. The checked examples use original synthetic fixtures.
