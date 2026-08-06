import unittest

from app.services.review_log import ReviewLogBuffer


class _FakeSession:
    def __init__(self) -> None:
        self.entries = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def add_all(self, entries) -> None:
        self.entries.extend(entries)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


class ReviewLogBufferTests(unittest.TestCase):
    def test_flushes_after_batch_size_without_using_workflow_session(self):
        sessions: list[_FakeSession] = []

        def create_session() -> _FakeSession:
            session = _FakeSession()
            sessions.append(session)
            return session

        buffer = ReviewLogBuffer(
            "task-1",
            batch_size=2,
            flush_interval=60,
            session_factory=create_session,
        )
        buffer.append(step="planning", level="info", message="one")
        self.assertEqual(sessions, [])

        buffer.append(step="planning", level="info", message="two")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].commit_count, 1)
        self.assertEqual([entry.message for entry in sessions[0].entries], ["one", "two"])
        self.assertTrue(sessions[0].closed)

    def test_flushes_when_interval_has_elapsed(self):
        now = [100.0]
        sessions: list[_FakeSession] = []

        def create_session() -> _FakeSession:
            session = _FakeSession()
            sessions.append(session)
            return session

        buffer = ReviewLogBuffer(
            "task-1",
            batch_size=10,
            flush_interval=5,
            session_factory=create_session,
            clock=lambda: now[0],
        )
        buffer.append(step="load_pr", level="info", message="one")
        now[0] = 105.1
        buffer.append(step="load_pr", level="info", message="two")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(sessions[0].entries), 2)


if __name__ == "__main__":
    unittest.main()
