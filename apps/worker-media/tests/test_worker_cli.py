from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from lumi_worker_media.queue_contracts import QUEUE_BY_JOB_KIND
from lumi_worker_media.worker_cli import worker_argv


class WorkerMediaCliTests(unittest.TestCase):
    def test_default_worker_argv_consumes_declared_media_queues(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            argv = worker_argv()

        self.assertEqual(argv[0], "worker")
        self.assertIn("--loglevel=INFO", argv)
        self.assertIn("--concurrency=4", argv)
        self.assertIn("--hostname=worker-media@%h", argv)
        queue_arg = next(item for item in argv if item.startswith("--queues="))
        self.assertEqual(
            queue_arg,
            "--queues=" + ",".join(dict.fromkeys(QUEUE_BY_JOB_KIND.values())),
        )

    def test_worker_concurrency_is_bounded(self) -> None:
        for value in ("0", "33", "not-a-number"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {"LUMI_WORKER_MEDIA_CONCURRENCY": value},
                    clear=True,
                ):
                    with self.assertRaises(RuntimeError):
                        worker_argv()

    def test_worker_log_level_is_allowlisted(self) -> None:
        with patch.dict(
            os.environ,
            {"LUMI_WORKER_MEDIA_LOG_LEVEL": "trace"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "LOG_LEVEL_INVALID"):
                worker_argv()

    def test_worker_runtime_tunables_are_applied(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LUMI_WORKER_MEDIA_CONCURRENCY": "8",
                "LUMI_WORKER_MEDIA_LOG_LEVEL": "warning",
            },
            clear=True,
        ):
            argv = worker_argv()
        self.assertIn("--concurrency=8", argv)
        self.assertIn("--loglevel=WARNING", argv)


if __name__ == "__main__":
    unittest.main()
