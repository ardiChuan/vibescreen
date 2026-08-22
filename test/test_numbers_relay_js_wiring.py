#!/usr/bin/env python3
"""Repository-gate contract for the numbers relay JavaScript suites."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class NumbersRelayJsWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = read("test/run.sh")
        workflow = read(".github/workflows/ci.yml")
        self.tokenserver_job = workflow.split("\n  tokenserver:", 1)[1].split(
            "\n  firmware:", 1
        )[0]

    def test_full_runner_runs_each_numbers_relay_suite_once(self) -> None:
        merge_command = "node --test tools/relay/test.mjs"
        runtime_command = "(cd tools/relay && npm ci && npm test)"

        self.assertEqual(self.runner.count(merge_command), 1)
        self.assertEqual(self.runner.count(runtime_command), 1)
        self.assertEqual(
            self.runner.count(
                '"$PYTHON_BIN" test_numbers_relay_js_wiring.py'
            ),
            1,
        )

        node_branch = self.runner.split(
            "elif command -v node >/dev/null 2>&1 && "
            "command -v npm >/dev/null 2>&1; then",
            1,
        )[1].split('elif [ -n "${CI:-}" ]; then', 1)[0]
        self.assertIn(merge_command, node_branch)
        self.assertIn(runtime_command, node_branch)
        self.assertIn('if [ "$SKIP_JS" = 1 ]; then', self.runner)

    def test_ci_runs_each_numbers_relay_suite_once_with_pinned_install(self) -> None:
        self.assertEqual(
            self.tokenserver_job.count("node --test tools/relay/test.mjs"), 1
        )
        self.assertEqual(
            self.tokenserver_job.count("working-directory: tools/relay"), 1
        )
        self.assertEqual(
            self.tokenserver_job.count("run: npm ci && npm test"), 1
        )
        self.assertEqual(
            self.tokenserver_job.count("cache-dependency-path: "
                                       "tools/relay/package-lock.json"),
            1,
        )
        self.assertEqual(self.tokenserver_job.count("actions/setup-node@v4"), 1)
        self.assertEqual(self.tokenserver_job.count("node-version: 22"), 1)

    def test_npm_runtime_suite_does_not_repeat_merge_suite(self) -> None:
        package = json.loads(read("tools/relay/package.json"))

        self.assertEqual(
            package["scripts"]["test"],
            "vitest run --config vitest.config.mjs",
        )
        self.assertEqual(
            package["scripts"]["test:merge"],
            "node --test test.mjs",
        )


if __name__ == "__main__":
    unittest.main()
