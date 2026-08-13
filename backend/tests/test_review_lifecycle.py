import unittest
import uuid

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.reviews import (
    archive_review,
    delete_review,
    get_review_status,
    list_reviews_with_archive,
    restore_review,
)
from app.models.base import Base
from app.models.repo import Repo, ReviewLog, ReviewReport, ReviewTask


class ReviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.repo = Repo(
            id=str(uuid.uuid4()),
            name="test-repo",
            git_url="https://example.test/test-repo.git",
            local_path="C:/tmp/test-repo",
        )
        self.task = ReviewTask(
            id=str(uuid.uuid4()),
            repo_id=self.repo.id,
            review_type="local",
            status="done",
        )
        self.session.add_all([self.repo, self.task])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_archive_hides_record_and_restore_reveals_it(self):
        archive_review(self.task.id, self.session)

        self.assertEqual(list_reviews_with_archive(self.repo.id, False, self.session), [])
        archived = list_reviews_with_archive(self.repo.id, True, self.session)
        self.assertEqual(len(archived), 1)
        self.assertIsNotNone(archived[0].archived_at)

        restore_review(self.task.id, self.session)

        active = list_reviews_with_archive(self.repo.id, False, self.session)
        self.assertEqual(len(active), 1)
        self.assertIsNone(active[0].archived_at)

    def test_running_review_cannot_be_archived_or_deleted(self):
        self.task.status = "running"
        self.session.commit()

        with self.assertRaises(HTTPException) as archive_error:
            archive_review(self.task.id, self.session)
        with self.assertRaises(HTTPException) as delete_error:
            delete_review(self.task.id, self.session)

        self.assertEqual(archive_error.exception.status_code, 409)
        self.assertEqual(delete_error.exception.status_code, 409)

    def test_delete_removes_task_and_report(self):
        report = ReviewReport(
            task_id=self.task.id,
            summary="summary",
            risk_level="low",
            findings_json="[]",
            stats_json="{}",
        )
        self.session.add(report)
        log = ReviewLog(task_id=self.task.id, step="generate_report", message="done")
        self.session.add(log)
        self.session.commit()
        log_id = log.id

        delete_review(self.task.id, self.session)

        self.assertIsNone(self.session.get(ReviewTask, self.task.id))
        self.assertIsNone(self.session.get(ReviewReport, report.id))
        self.assertIsNone(self.session.get(ReviewLog, log_id))

    def test_status_response_includes_repository_context(self):
        report = ReviewReport(
            task_id=self.task.id,
            summary="summary",
            risk_level="high",
            findings_json="[]",
            stats_json="{}",
        )
        self.session.add(report)
        self.session.commit()

        response = get_review_status(self.task.id, self.session)

        self.assertEqual(response.repo_name, "test-repo")
        self.assertEqual(response.risk_level, "high")


if __name__ == "__main__":
    unittest.main()
