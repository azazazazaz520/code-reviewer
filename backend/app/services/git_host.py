"""Git hosting provider adapters used by repository and PR workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests

from app.config import settings


class GitHostError(RuntimeError):
    """A supported Git host could not serve the requested resource."""


@dataclass(frozen=True)
class GitRepositoryRef:
    provider: str
    host: str
    owner: str
    name: str
    api_base_url: str
    token: str

    @property
    def label(self) -> str:
        return "Gitee" if self.provider == "gitee" else "GitHub"

    def api_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "code-reviewer"}
        if self.provider == "github" and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        return headers

    def api_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        result = dict(params or {})
        if self.provider == "gitee" and self.token:
            result["access_token"] = self.token
        return result

    def api_url(self, path: str) -> str:
        return f"{self.api_base_url}/repos/{quote(self.owner)}/{quote(self.name)}{path}"

    def clone_url(self, git_url: str) -> str:
        """Add the configured token only for HTTPS clone URLs."""
        if not self.token or not git_url.startswith(("http://", "https://")):
            return git_url

        parsed = urlparse(git_url)
        encoded_token = quote(self.token, safe="")
        if self.provider == "gitee":
            username, password = "oauth2", encoded_token
        else:
            username, password = encoded_token, ""
        auth = username if not password else f"{username}:{password}"
        host = parsed.hostname or self.host
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{auth}@{host}{port}{parsed.path}"


def parse_git_repository(git_url: str) -> GitRepositoryRef:
    """Parse GitHub/Gitee HTTPS and SCP-style SSH repository URLs."""
    value = git_url.strip().rstrip("/")
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", maxsplit=1)
    else:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")

    host = host.lower()
    provider_by_host = {"github.com": "github", "gitee.com": "gitee"}
    provider = provider_by_host.get(host)
    if not provider:
        raise GitHostError(f"暂不支持该 Git 托管平台: {host or git_url}")

    parts = [part for part in path.removesuffix(".git").split("/") if part]
    if len(parts) != 2:
        raise GitHostError(f"无法从 git_url 解析 {provider.title()} owner/repo: {git_url}")

    token = settings.github_token if provider == "github" else settings.gitee_token
    api_base_url = "https://api.github.com" if provider == "github" else "https://gitee.com/api/v5"
    return GitRepositoryRef(
        provider=provider,
        host=host,
        owner=parts[0],
        name=parts[1],
        api_base_url=api_base_url,
        token=token,
    )


def get_open_pulls(git_url: str) -> list[dict[str, Any]]:
    repository = parse_git_repository(git_url)
    response = _get_json(
        repository,
        "/pulls",
        params={"state": "open", "per_page": 20, "sort": "updated", "direction": "desc"},
    )
    if not isinstance(response, list):
        raise GitHostError("PR 列表响应格式不正确")
    return response


def get_pull(git_url: str, pr_number: int) -> dict[str, Any]:
    repository = parse_git_repository(git_url)
    response = _get_json(repository, f"/pulls/{pr_number}")
    if not isinstance(response, dict):
        raise GitHostError("PR 详情响应格式不正确")
    return response


def get_pull_files(git_url: str, pr_number: int) -> list[dict[str, Any]]:
    repository = parse_git_repository(git_url)
    response = _get_json(repository, f"/pulls/{pr_number}/files")
    if not isinstance(response, list):
        raise GitHostError("PR 文件列表响应格式不正确")
    return response


def get_pull_diff(git_url: str, pr_number: int) -> str:
    repository = parse_git_repository(git_url)
    if repository.provider == "gitee":
        files = get_pull_files(git_url, pr_number)
        chunks: list[str] = []
        for item in files:
            filename = item.get("filename") or ""
            patch = item.get("patch") or ""
            if not filename or not patch:
                continue
            chunks.append(f"diff --git a/{filename} b/{filename}\n{patch}")
        return "\n".join(chunks) or "(no changes)"

    headers = repository.api_headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    try:
        response = requests.get(
            repository.api_url(f"/pulls/{pr_number}"),
            headers=headers,
            params=repository.api_params(),
            timeout=30,
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        raise GitHostError(f"{repository.label} PR diff 请求失败: {exc}") from exc


def pull_sha(pull: dict[str, Any], side: str) -> str:
    value = pull.get(side) or {}
    sha = value.get("sha") or value.get("commit_id")
    if not isinstance(sha, str) or not sha:
        raise GitHostError(f"PR 元数据缺少 {side}.sha")
    return sha


def _get_json(
    repository: GitRepositoryRef,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    try:
        response = requests.get(
            repository.api_url(path),
            headers=repository.api_headers(),
            params=repository.api_params(params),
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise GitHostError(f"{repository.label} Token 无效或没有访问权限")
        response.raise_for_status()
        return response.json()
    except GitHostError:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise GitHostError(f"{repository.label} API 请求失败: {exc}") from exc
