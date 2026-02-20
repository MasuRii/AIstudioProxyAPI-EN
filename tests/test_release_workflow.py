"""
Tests for the GitHub Actions release workflow configuration.

Required test category notes:
- Concurrency/timing: Not applicable for static YAML validation.
- Performance: Not applicable for static configuration checks.
- Security-focused: Not applicable; no auth or security logic is executed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _read_release_workflow() -> str:
    """Read the release workflow file with explicit error handling."""
    try:
        return WORKFLOW_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        pytest.fail(f"Release workflow not found at {WORKFLOW_PATH}: {exc}")


def _load_release_workflow_yaml() -> dict:
    """Parse the release workflow YAML and fail with context on errors."""
    content = _read_release_workflow()
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        pytest.fail(f"Invalid YAML syntax in {WORKFLOW_PATH}: {exc}")
    if not isinstance(data, dict):
        pytest.fail("Release workflow YAML did not parse into a mapping")
    return data


def _extract_step_block(content: str, step_name: str) -> str:
    """Extract a step block by name from the workflow text."""
    marker = f"      - name: {step_name}"
    start = content.find(marker)
    if start == -1:
        pytest.fail(f"Step '{step_name}' was not found in release workflow")

    next_step = content.find("\n      - name:", start + len(marker))
    if next_step == -1:
        return content[start:]
    return content[start:next_step]


class TestReleaseWorkflow:
    """Release workflow validation tests."""

    def test_yaml_syntax_is_valid_and_has_jobs(self) -> None:
        """Happy path: YAML parses and includes expected top-level keys."""
        # Arrange
        # Act
        data = _load_release_workflow_yaml()

        # Assert
        assert data, "Release workflow YAML should not be empty"
        assert "jobs" in data, "Release workflow should define jobs"

    def test_stable_changelog_uses_github_username_and_fallback_author(self) -> None:
        """Boundary: stable changelog should use GitHub username lookup with fallback."""
        # Arrange
        content = _read_release_workflow()
        stable_step = _extract_step_block(content, "Generate changelog")

        # Act
        has_commit_api_lookup = (
            'gh api "repos/${{ github.repository }}/commits/$commit_sha"' in stable_step
        )
        has_jq_username_extract = "jq -r '.author.login // empty'" in stable_step
        has_github_mention_format = "by @${github_username}" in stable_step
        has_git_fallback_format = "by ${git_author}" in stable_step
        has_old_direct_git_format = "- %s by %an (%h)" in stable_step

        # Assert
        assert has_commit_api_lookup, (
            "Stable changelog must query the GitHub commit API per commit SHA"
        )
        assert has_jq_username_extract, (
            "Stable changelog must extract '.author.login // empty' with jq"
        )
        assert has_github_mention_format, (
            "Stable changelog must format GitHub-linked authors as '@username'"
        )
        assert has_git_fallback_format, (
            "Stable changelog must fall back to git author name without '@'"
        )
        assert not has_old_direct_git_format, (
            "Stable changelog must not use direct git author formatting '- %s by %an (%h)'"
        )

    def test_nightly_changes_use_github_username_and_fallback_author(self) -> None:
        """Boundary: nightly changes should use GitHub username lookup with fallback."""
        # Arrange
        content = _read_release_workflow()
        nightly_step = _extract_step_block(content, "Generate recent changes")

        # Act
        has_commit_api_lookup = (
            'gh api "repos/${{ github.repository }}/commits/$commit_sha"'
            in nightly_step
        )
        has_jq_username_extract = "jq -r '.author.login // empty'" in nightly_step
        has_github_mention_format = "by @${github_username}" in nightly_step
        has_git_fallback_format = "by ${git_author}" in nightly_step
        has_old_direct_git_format = "- %s by %an (%h)" in nightly_step

        # Assert
        assert has_commit_api_lookup, (
            "Nightly changes must query the GitHub commit API per commit SHA"
        )
        assert has_jq_username_extract, (
            "Nightly changes must extract '.author.login // empty' with jq"
        )
        assert has_github_mention_format, (
            "Nightly changes must format GitHub-linked authors as '@username'"
        )
        assert has_git_fallback_format, (
            "Nightly changes must fall back to git author name without '@'"
        )
        assert not has_old_direct_git_format, (
            "Nightly changes must not use direct git author formatting '- %s by %an (%h)'"
        )

    def test_nightly_changelog_uses_latest_stable_tag_range(self) -> None:
        """Happy path: nightly changelog should use latest stable tag range."""
        # Arrange
        content = _read_release_workflow()
        nightly_step = _extract_step_block(content, "Generate recent changes")

        # Act
        has_latest_stable_tag_lookup = (
            "git tag --sort=-v:refname | grep -E '^v[0-9]+\\.[0-9]+\\.[0-9]+$'"
            in nightly_step
        )
        has_range_log = (
            'git log --pretty=format:"%H" "${LATEST_STABLE_TAG}..HEAD"' in nightly_step
        )
        has_fixed_ten_commit_log = 'git log --pretty=format:"%H" -10' in nightly_step

        # Assert
        assert has_latest_stable_tag_lookup, (
            "Nightly changelog must find latest stable tag using semantic version pattern"
        )
        assert has_range_log, (
            "Nightly changelog must use git log ${LATEST_STABLE_TAG}..HEAD range"
        )
        assert not has_fixed_ten_commit_log, (
            "Nightly changelog must not use a fixed -10 commit range"
        )

    def test_nightly_changelog_fallback_when_no_stable_tag(self) -> None:
        """Null/empty: nightly changelog should fall back when no stable tag exists."""
        # Arrange
        content = _read_release_workflow()
        nightly_step = _extract_step_block(content, "Generate recent changes")

        # Act
        has_fallback_log = 'git log --pretty=format:"%H" -20' in nightly_step
        has_fallback_note = (
            "_No stable release tag found. Showing last 20 commits (first release scenario)._"
            in nightly_step
        )

        # Assert
        assert has_fallback_log, (
            "Nightly changelog must fall back to the last 20 commits when no stable tag exists"
        )
        assert has_fallback_note, (
            "Nightly changelog must include a fallback note when no stable tag exists"
        )

    def test_nightly_changelog_includes_range_note(self) -> None:
        """Boundary: nightly changelog should include range and fallback notes."""
        # Arrange
        content = _read_release_workflow()
        nightly_step = _extract_step_block(content, "Generate recent changes")

        # Act
        has_range_note = "_Changes since ${LATEST_STABLE_TAG}_" in nightly_step
        has_fallback_note = (
            "_No stable release tag found. Showing last 20 commits (first release scenario)._"
            in nightly_step
        )

        # Assert
        assert has_range_note, (
            "Nightly changelog must include a 'Changes since vX.Y.Z' note"
        )
        assert has_fallback_note, (
            "Nightly changelog must include a fallback note when no stable tag exists"
        )

    def test_docs_guides_links_are_not_broken(self) -> None:
        """Invalid/malformed: docs/guides links must resolve to files."""
        # Arrange
        content = _read_release_workflow()
        pattern = re.compile(r"docs/guides/[A-Za-z0-9._/-]+")

        # Act
        referenced_paths = pattern.findall(content)

        # Assert
        if not referenced_paths:
            return

        for raw_path in referenced_paths:
            sanitized = raw_path.rstrip(").,;\"' ")
            full_path = REPO_ROOT / sanitized
            assert full_path.exists(), f"Broken documentation link: {sanitized}"

    def test_contributor_acknowledgement_uses_thank_you_message(self) -> None:
        """Error condition: workflow must include the thank-you contributor message."""
        # Arrange
        content = _read_release_workflow()

        # Act
        thank_you_occurrences = len(
            re.findall(r"\*\*Thank you to all contributors!\*\*", content)
        )

        # Assert
        assert thank_you_occurrences >= 2, (
            "Contributor acknowledgement must include '**Thank you to all contributors!**' "
            "in both stable and nightly release sections"
        )

    def test_contributor_list_generation_is_removed(self) -> None:
        """Error condition: contributor list files should not be generated in workflow."""
        # Arrange
        content = _read_release_workflow()

        # Act
        has_stable_contributors_file = "CONTRIBUTORS.md" in content
        has_nightly_contributors_file = "NIGHTLY_CONTRIBUTORS.md" in content

        # Assert
        assert not has_stable_contributors_file, (
            "Stable release workflow must not generate CONTRIBUTORS.md"
        )
        assert not has_nightly_contributors_file, (
            "Nightly release workflow must not generate NIGHTLY_CONTRIBUTORS.md"
        )

    def test_readme_reference_exists_for_installation_instructions(self) -> None:
        """Null/empty: README reference should exist for installation guidance."""
        # Arrange
        content = _read_release_workflow()

        # Act
        has_installation_section = "## Installation" in content
        has_readme_reference = "README.md" in content

        # Assert
        assert has_installation_section, (
            "Release body should include an Installation section"
        )
        assert has_readme_reference, (
            "Release body should reference README.md for installation instructions"
        )
