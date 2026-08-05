"""Performance Reviewer — 性能审查。"""

from pathlib import Path

from app.engine.reviewers.base import BaseReviewer, ReviewerContext


class PerformanceReviewer(BaseReviewer):
    name = "performance_reviewer"
    required_tools = ["ReadFile", "GetHubNodes", "GetImpactRadius"]

    def __init__(self):
        super().__init__()
        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "performance.j2"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def review(self, context: ReviewerContext) -> list[dict]:
        llm_output = self._call_llm(context)
        return self._parse_findings_with_repair(llm_output, context)
