import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.rag.contracts import DocumentType
from backend.app.rag.ingestion import MarkItDownAdapter, RepositoryIngestor
from backend.app.rag.redaction import redact_text
from backend.app.rag.safety import (
    IndexLimits,
    PathSafetyError,
    RepositoryFile,
    RepositoryWalker,
    WorkspaceBoundary,
)


def test_workspace_boundary_rejects_outside_and_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repository = workspace / "repo"
    outside = tmp_path / "outside"
    repository.mkdir(parents=True)
    outside.mkdir()
    boundary = WorkspaceBoundary(workspace)

    assert boundary.repository_root(repository) == repository.resolve()
    with pytest.raises(PathSafetyError):
        boundary.repository_root(outside)
    with pytest.raises(PathSafetyError):
        boundary.file(repository / ".." / ".." / "outside" / "secret.txt", repository)


def test_walker_ignores_secrets_dependencies_binaries_and_applies_limits(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (repository / "second.md").write_text("small\n", encoding="utf-8")
    (repository / ".env").write_text("TOKEN=not-indexed\n", encoding="utf-8")
    (repository / "secrets.yaml").write_text("token: not-indexed\n", encoding="utf-8")
    (repository / "photo.png").write_bytes(b"\x89PNG\x00")
    (repository / "large.txt").write_text("x" * 101, encoding="utf-8")
    dependencies = repository / "node_modules"
    dependencies.mkdir()
    (dependencies / "package.js").write_text("ignored", encoding="utf-8")
    git_dir = repository / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("ignored", encoding="utf-8")
    report_dir = repository / ".remedygraph"
    report_dir.mkdir()
    (report_dir / "report.json").write_text('{"ignored": true}', encoding="utf-8")

    report = RepositoryWalker(
        tmp_path, IndexLimits(max_file_bytes=100, max_index_bytes=1_000, max_files=1)
    ).walk(repository)

    assert [file.source_path for file in report.files] == ["app.py"]
    assert report.total_bytes == (repository / "app.py").stat().st_size
    assert report.skipped["secret_file"] == 2
    assert report.skipped["ignored_extension"] == 1
    assert report.skipped["oversized_file"] == 1
    assert report.skipped["ignored_directory"] == 3
    assert report.skipped["max_files"] == 1


def test_walker_applies_total_index_byte_limit(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "first.txt").write_bytes(b"12345678")
    (repository / "second.txt").write_bytes(b"abcdefgh")

    report = RepositoryWalker(
        tmp_path, IndexLimits(max_file_bytes=10, max_index_bytes=10, max_files=10)
    ).walk(repository)

    assert [file.source_path for file in report.files] == ["first.txt"]
    assert report.total_bytes == 8
    assert report.skipped["max_index_bytes"] == 1


def test_walker_skips_symlink_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    link = repository / "linked.txt"
    link.write_text("placeholder", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path.name == "linked.txt" or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    report = RepositoryWalker(tmp_path).walk(repository)

    assert report.files == []
    assert report.skipped["symlink"] == 1


def test_native_ingestion_preserves_metadata_and_redacts_secrets(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    raw = b"# Runbook\r\napi_key = super-secret\r\n"
    source = repository / "runbook.md"
    source.write_bytes(raw)

    report = RepositoryIngestor(tmp_path, repository).ingest()

    assert report.failures == []
    assert len(report.documents) == 1
    document = report.documents[0]
    assert document.source_filename == "runbook.md"
    assert document.source_path == "runbook.md"
    assert document.mime_type == "text/markdown"
    assert document.sha256 == hashlib.sha256(raw).hexdigest()
    assert document.converter_name == "native-text"
    assert document.converter_version == "1"
    assert document.document_type == DocumentType.DOCUMENT
    assert "super-secret" not in document.markdown
    assert "[REDACTED]" in document.markdown
    assert "\r" not in document.markdown


def test_multiline_private_key_redaction_preserves_source_line_count() -> None:
    source = "before\n-----BEGIN PRIVATE KEY-----\nabc\ndef\n-----END PRIVATE KEY-----\nafter"

    redacted = redact_text(source)

    assert "abc" not in redacted
    assert redacted.count("\n") == source.count("\n")
    assert redacted.splitlines()[-1] == "after"


def test_markitdown_uses_local_conversion_with_plugins_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    source = repository / "incident.pdf"
    source.write_bytes(b"%PDF fixture")
    captured: dict[str, object] = {}

    class FakeMarkItDown:
        def __init__(self, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def convert_local(self, path: str) -> object:
            captured["path"] = path
            return SimpleNamespace(markdown="# Converted\npassword: hidden", text_content=None)

    import backend.app.rag.ingestion as ingestion

    monkeypatch.setattr(
        ingestion.importlib,
        "import_module",
        lambda name: SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    adapter = MarkItDownAdapter(tmp_path, repository, converter_version="0.test")
    file = RepositoryFile(source.resolve(), "incident.pdf", source.stat().st_size)

    document = adapter.normalize(file)

    assert captured["kwargs"] == {
        "enable_plugins": False,
        "docintel_endpoint": None,
        "cu_endpoint": None,
        "llm_client": None,
        "llm_model": None,
    }
    assert captured["path"] == str(source.resolve())
    assert document.converter_name == "microsoft-markitdown"
    assert document.converter_version == "0.test"
    assert document.source_filename == "incident.pdf"
    assert document.mime_type == "application/pdf"
    assert "hidden" not in document.markdown


def test_conversion_failure_is_bounded_and_does_not_abort_ingestion(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "good.txt").write_text("usable evidence", encoding="utf-8")
    (repository / "broken.docx").write_bytes(b"not a real document")

    class FailingConverter:
        def convert_local(self, path: str) -> object:
            raise RuntimeError(f"sensitive converter detail for {path}")

    report = RepositoryIngestor(
        tmp_path,
        repository,
        markitdown_factory=FailingConverter,
        markitdown_version="test",
    ).ingest()

    assert [document.source_path for document in report.documents] == ["good.txt"]
    assert len(report.failures) == 1
    assert report.failures[0].source_path == "broken.docx"
    assert report.failures[0].reason == "MarkItDown conversion failed: RuntimeError"
    assert str(repository) not in report.failures[0].reason


def test_unsupported_markitdown_formats_are_not_walked(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    for name in ("archive.zip", "recording.mp3", "sheet.xlsx"):
        (repository / name).write_bytes(b"ignored")

    report = RepositoryWalker(tmp_path).walk(repository)

    assert report.files == []
    assert sum(report.skipped.values()) == 3
