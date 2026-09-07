"""Performance Reviewer — 性能审查。"""

from pathlib import Path

from app.engine.reviewers.base import BaseReviewer


class PerformanceReviewer(BaseReviewer):
    name = "performance_reviewer"

    def __init__(self):
        super().__init__()
        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "performance.j2"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")
