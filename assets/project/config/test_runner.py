"""The project test runner: the egress guard for every test run.

Set `TEST_RUNNER = "config.test_runner.ProjectTestRunner"` in the test settings.
Reference data that every environment has is seeded by `post_migrate` handlers
of the owning apps, which Django also runs for the test database.
"""

from __future__ import annotations

from typing import Any

from django.test.runner import DiscoverRunner

from config.test_egress import install_egress_guard


class ProjectTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs: Any) -> None:
        super().setup_test_environment(**kwargs)
        install_egress_guard()
