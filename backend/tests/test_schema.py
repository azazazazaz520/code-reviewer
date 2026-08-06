import unittest
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, inspect, text

from app.models.base import ensure_schema


class SchemaMigrationTest(unittest.TestCase):
    def test_legacy_sqlite_schema_adds_repository_and_review_task_fields(self):
        with TemporaryDirectory(prefix="schema-test-") as temp_dir:
            database_url = f"sqlite:///{temp_dir}/legacy.db"
            legacy_engine = create_engine(database_url)
            try:
                with legacy_engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            CREATE TABLE repositories (
                                id VARCHAR(36) PRIMARY KEY,
                                name VARCHAR(200) NOT NULL,
                                git_url VARCHAR(1000),
                                local_path VARCHAR(1000),
                                created_at DATETIME
                            )
                            """
                        )
                    )
                    connection.execute(
                        text(
                            """
                            CREATE TABLE review_tasks (
                                id VARCHAR(36) PRIMARY KEY,
                                repo_id VARCHAR(36) NOT NULL,
                                status VARCHAR(30) NOT NULL,
                                created_at DATETIME
                            )
                            """
                        )
                    )

                ensure_schema(legacy_engine)

                inspector = inspect(legacy_engine)
                repository_columns = {
                    column["name"] for column in inspector.get_columns("repositories")
                }
                review_task_columns = {
                    column["name"] for column in inspector.get_columns("review_tasks")
                }
                self.assertTrue(
                    {
                        "default_branch",
                        "last_synced_at",
                        "sync_status",
                        "sync_error",
                    }.issubset(repository_columns)
                )
                self.assertTrue(
                    {
                        "archived_at",
                        "source_type",
                        "workspace_target",
                        "workspace_stats_json",
                    }.issubset(review_task_columns)
                )
            finally:
                legacy_engine.dispose()
