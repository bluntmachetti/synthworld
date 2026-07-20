from __future__ import annotations

import pytest

_MAX_QUARANTINES = 5
_quarantined_tests: dict[str, str] = {}
_unexplained_skips: set[str] = set()


def pytest_configure(config: pytest.Config) -> None:
    _quarantined_tests.clear()
    _unexplained_skips.clear()
    config.addinivalue_line(
        "markers",
        "quarantine(issue): allow a documented skip linked to an issue",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config
    for item in items:
        quarantine = item.get_closest_marker("quarantine")
        if quarantine is None:
            continue
        issue = quarantine.kwargs.get("issue")
        if not isinstance(issue, str) or not issue.strip():
            raise pytest.UsageError(
                f"{item.nodeid}: quarantine requires a non-empty issue"
            )
        _quarantined_tests[item.nodeid] = issue

    if len(_quarantined_tests) > _MAX_QUARANTINES:
        raise pytest.UsageError(
            f"quarantine cap exceeded: {len(_quarantined_tests)}/{_MAX_QUARANTINES}"
        )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped and report.nodeid not in _quarantined_tests:
        _unexplained_skips.add(report.nodeid)


def pytest_sessionfinish(
    session: pytest.Session,
    exitstatus: int | pytest.ExitCode,
) -> None:
    del exitstatus
    if _unexplained_skips:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        formatted = "\n".join(f"  - {nodeid}" for nodeid in sorted(_unexplained_skips))
        print(f"\nUnexplained skipped tests are forbidden:\n{formatted}")
    if _quarantined_tests:
        print(f"\nQuarantined tests: {len(_quarantined_tests)}/{_MAX_QUARANTINES}")
