import threading
import unittest

from app.engine.execution import ReviewBudgetExceeded, ReviewExecutionBudget
from app.engine.review_units import build_review_units, parse_diff_hunks, reviewer_handles_file
from app.engine.tools.context import TaskToolCache


class ReviewUnitTests(unittest.TestCase):
    def test_groups_adjacent_hunks_and_keeps_complete_diff_text(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -10,2 +10,3 @@\n"
            " old\n+new\n"
            "@@ -40,1 +41,2 @@\n"
            " old2\n+new2\n"
        )

        hunks = parse_diff_hunks(diff)
        units = build_review_units(diff, ["src/app.py"], "rev-1")

        self.assertEqual(len(hunks), 2)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["hunk_ids"], ["src/app.py#1", "src/app.py#2"])
        self.assertEqual(units[0]["diff"], hunks[0].text + hunks[1].text)

    def test_unit_ids_are_stable_and_related_files_are_scoped(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n"
        )
        first = build_review_units(
            diff,
            ["src/app.py", "src/helpers.py"],
            "rev-1",
            context_candidates=["lib/other.py", "lib/dependency.py"],
        )
        second = build_review_units(
            diff,
            ["src/app.py", "src/helpers.py"],
            "rev-1",
            context_candidates=["lib/other.py", "lib/dependency.py"],
        )

        self.assertEqual(first, second)
        self.assertEqual(first[0]["files"], ["src/app.py", "src/helpers.py", "lib/other.py", "lib/dependency.py"])

    def test_reviewer_scope_matches_file_category(self):
        self.assertTrue(reviewer_handles_file("style_reviewer", "src/app.py"))
        self.assertFalse(reviewer_handles_file("style_reviewer", "update/windows.json"))
        self.assertTrue(reviewer_handles_file("security_reviewer", "config/app.yml"))
        self.assertFalse(reviewer_handles_file("performance_reviewer", "src/app.ts"))

    def test_unit_includes_enclosing_symbol_context_when_source_is_available(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -3,1 +3,1 @@\n-old\n+new\n"
        )
        units = build_review_units(
            diff,
            ["src/app.py"],
            "rev-1",
            file_context={
                "src/app.py": (
                    "1|class Service:\n"
                    "2|    def run(self):\n"
                    "3|        return new\n"
                    "4|\n"
                    "5|    def stop(self):\n"
                    "6|        return None\n"
                ),
            },
        )

        self.assertEqual(units[0]["context_start_line"], 2)
        self.assertEqual(units[0]["context_end_line"], 4)
        self.assertEqual(units[0]["symbol_context"]["name"], "run")


class TaskToolCacheTests(unittest.TestCase):
    def test_caches_success_and_error_results(self):
        cache = TaskToolCache()
        calls = []

        def load():
            calls.append("called")
            return "Error: file not found"

        first, first_hit = cache.get_or_load("rev", "ReadFile", {"file": "a.py"}, load)
        second, second_hit = cache.get_or_load("rev", "ReadFile", {"file": "a.py"}, load)

        self.assertEqual(first, second)
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(calls, ["called"])
        self.assertEqual(
            cache.stats(),
            {
                "tool_calls": 1,
                "tool_requests": 2,
                "cache_hits": 1,
                "cache_misses": 1,
                "read_file_requests": 2,
                "read_file_cache_hits": 1,
                "read_file_cache_misses": 1,
                "read_file_errors": 1,
            },
        )

    def test_concurrent_same_key_runs_loader_once(self):
        cache = TaskToolCache()
        calls = []
        barrier = threading.Barrier(2)

        def load():
            calls.append("called")
            return "content"

        results = []

        def read():
            barrier.wait(timeout=2)
            results.append(cache.get_or_load("rev", "ReadFile", {"file": "a.py"}, load))

        threads = [threading.Thread(target=read) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        self.assertEqual(calls, ["called"])
        self.assertEqual([value[0] for value in results], ["content", "content"])


class ReviewBudgetTests(unittest.TestCase):
    def test_rejects_calls_after_primary_budget(self):
        budget = ReviewExecutionBudget(max_primary_calls=1, max_duration_seconds=60)
        budget.reserve_primary_call()
        with self.assertRaises(ReviewBudgetExceeded):
            budget.reserve_primary_call()
        self.assertEqual(budget.primary_calls, 1)


if __name__ == "__main__":
    unittest.main()
