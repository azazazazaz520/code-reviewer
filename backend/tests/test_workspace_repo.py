import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.repos import register_workspace_repo
from app.main import app
from app.models.base import Base, get_db
from app.models.schemas import WorkspaceRepoCreate


class WorkspaceRepoTests(unittest.TestCase):
    def _create_git_workspace(self, path: Path) -> None:
        subprocess.run(
            ["git", "init", "-q", str(path)], check=True, capture_output=True
        )

    def test_register_workspace_repo_reuses_existing_local_repository(self):
        with TemporaryDirectory(prefix="workspace-repo-test-") as temp_dir:
            workspace = Path(temp_dir)
            self._create_git_workspace(workspace)
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(engine)
            session = sessionmaker(bind=engine)()
            try:
                first = register_workspace_repo(
                    WorkspaceRepoCreate(path=str(workspace)), session
                )
                second = register_workspace_repo(
                    WorkspaceRepoCreate(path=str(workspace)), session
                )

                self.assertEqual(first.id, second.id)
                self.assertEqual(Path(first.local_path), workspace.resolve())
                self.assertEqual(first.git_url, "")
            finally:
                session.close()
                engine.dispose()

    def test_workspace_repo_endpoint_accepts_directory_selected_by_frontend(self):
        with TemporaryDirectory(prefix="workspace-api-test-") as temp_dir:
            workspace = Path(temp_dir)
            self._create_git_workspace(workspace)
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine)

            def override_get_db():
                session = session_factory()
                try:
                    yield session
                finally:
                    session.close()

            app.dependency_overrides[get_db] = override_get_db
            try:
                with TestClient(app) as client:
                    response = client.post(
                        "/api/repos/workspace", json={"path": str(workspace)}
                    )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["local_path"], str(workspace.resolve()))
            finally:
                app.dependency_overrides.clear()
                engine.dispose()
