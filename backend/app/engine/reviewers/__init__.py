"""Reviewer 注册表。"""

from app.engine.reviewers.base import BaseReviewer, ReviewerContext
from app.engine.reviewers.style import StyleReviewer
from app.engine.reviewers.security import SecurityReviewer
from app.engine.reviewers.performance import PerformanceReviewer

REVIEWER_REGISTRY = {
    "style_reviewer": StyleReviewer(),
    "security_reviewer": SecurityReviewer(),
    "performance_reviewer": PerformanceReviewer(),
}

__all__ = ["BaseReviewer", "ReviewerContext", "REVIEWER_REGISTRY"]
