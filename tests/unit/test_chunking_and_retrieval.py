import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.rag.chunking import DocumentChunker
from backend.app.rag.contracts import DocumentType, NormalizedDocument
from backend.app.rag.embeddings import (
    DeterministicFakeEncoder,
    SemanticIndex,
    SentenceTransformerEncoder,
)
from backend.app.rag.index import LexicalIndex
from backend.app.rag.ingestion import RepositoryIngestor
from backend.app.rag.pipeline import RepositoryIndexer
from backend.app.rag.retrieval import HybridRetriever, RetrievalLogger


def document(
    text: str,
    *,
    source_path: str = "README.md",
    language: str | None = None,
    document_type: DocumentType = DocumentType.DOCUMENT,
) -> NormalizedDocument:
    return NormalizedDocument(
        id=f"doc-{source_path}",
        source_path=source_path,
        source_filename=Path(source_path).name,
        mime_type="text/plain",
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        converter_name="test",
        converter_version="1",
        markdown=text,
        document_type=document_type,
        language=language,
    )


def test_chunk_contract_rejects_unsafe_paths_and_reversed_locations() -> None:
    valid = DocumentChunker(max_chars=1_000).chunk(document("evidence"))[0]

    with pytest.raises(ValidationError):
        type(valid).model_validate({**valid.model_dump(), "source_path": "../secret.txt"})
    with pytest.raises(ValidationError):
        type(valid).model_validate({**valid.model_dump(), "line_start": 5, "line_end": 4})


def test_markdown_chunking_preserves_heading_locations_and_hashes() -> None:
    source = "Intro\n# First\nalpha\nbeta\n## Second\ngamma"

    chunks = DocumentChunker(max_chars=128).chunk(document(source))

    assert [(chunk.line_start, chunk.line_end) for chunk in chunks] == [(1, 1), (2, 4), (5, 6)]
    assert chunks[1].text == "# First\nalpha\nbeta"
    assert chunks[1].content_hash == hashlib.sha256(chunks[1].text.encode()).hexdigest()
    assert chunks[1].index_version == "day2-v1"


def test_python_chunking_records_qualified_symbols_and_exact_lines() -> None:
    source = '''import time

class RetryPolicy:
    """Bounded retry policy."""

    @staticmethod
    def delay(attempt: int) -> float:
        return attempt * 0.1

def execute() -> None:
    pass
'''

    chunks = DocumentChunker(max_chars=1_000).chunk(
        document(
            source, source_path="retry.py", language="python", document_type=DocumentType.SOURCE
        )
    )
    by_symbol = {chunk.symbol: chunk for chunk in chunks}

    assert by_symbol["RetryPolicy"].line_start == 3
    assert by_symbol["RetryPolicy"].line_end == 8
    assert by_symbol["RetryPolicy.delay"].line_start == 6
    assert by_symbol["RetryPolicy.delay"].line_end == 8
    assert by_symbol["execute"].line_start == 10
    assert by_symbol["execute"].line_end == 11
    assert by_symbol["<module>"].text == "import time"


def test_lexical_fts5_and_semantic_indexes_return_typed_ranked_results() -> None:
    chunks = DocumentChunker(max_chars=1_000).chunk(
        document("# Retry\nBound payment retry attempts to three.", source_path="retry.md")
    ) + DocumentChunker(max_chars=1_000).chunk(
        document("# Queue\nWorker queue capacity is finite.", source_path="queue.md")
    )
    lexical = LexicalIndex()
    lexical.index(chunks)
    semantic = SemanticIndex(DeterministicFakeEncoder())
    semantic.index(chunks)

    lexical_results = lexical.search("payment retry")
    semantic_results = semantic.search("payment retry")

    assert lexical_results[0].chunk.source_path == "retry.md"
    assert lexical_results[0].rank == 1
    assert semantic_results[0].chunk.source_path == "retry.md"
    assert semantic_results[0].rank == 1
    lexical.close()


def test_index_upsert_does_not_duplicate_fts_rows() -> None:
    chunk = DocumentChunker(max_chars=1_000).chunk(document("retry retry retry"))[0]
    lexical = LexicalIndex()

    lexical.index([chunk])
    lexical.index([chunk])

    assert len(lexical.search("retry")) == 1
    lexical.close()


def test_hybrid_merge_deduplicates_reranks_and_logs_scores_with_redaction() -> None:
    chunks = DocumentChunker(max_chars=1_000).chunk(
        document(
            "def test_retry_exhaustion():\n    assert retry(4) == 3",
            source_path="tests/test_retry.py",
            language="python",
            document_type=DocumentType.TEST,
        )
    ) + DocumentChunker(max_chars=1_000).chunk(
        document("Retries are discussed here.", source_path="notes.md")
    )
    lexical = LexicalIndex()
    lexical.index(chunks)
    semantic = SemanticIndex(DeterministicFakeEncoder())
    semantic.index(chunks)
    log = RetrievalLogger(max_entries=2)
    retriever = HybridRetriever(lexical, semantic, retrieval_logger=log)

    results = retriever.search(
        "api_key=supersecret retry regression test", top_k=2, prefer_tests=True
    )

    assert len({result.chunk.id for result in results}) == len(results)
    assert results[0].chunk.document_type == DocumentType.TEST
    assert "test_role" in results[0].reasons
    assert log.entries[0].candidates[0].chunk_id == results[0].chunk.id
    assert log.entries[0].candidates[0].final_rank == 1
    assert "supersecret" not in log.entries[0].query
    assert "[REDACTED]" in log.entries[0].query
    lexical.close()


def test_fake_encoder_is_stable_and_network_free() -> None:
    first = DeterministicFakeEncoder(32).encode(["retry limit"])[0]
    second = DeterministicFakeEncoder(32).encode(["retry limit"])[0]

    assert first == second
    assert len(first) == 32
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


def test_sentence_transformer_adapter_defaults_to_local_files_only(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Encoded:
        def tolist(self) -> list[list[float]]:
            return [[1.0, 0.0]]

    class FakeModel:
        def __init__(self, name: str, **kwargs: object) -> None:
            captured["name"] = name
            captured["kwargs"] = kwargs

        def get_sentence_embedding_dimension(self) -> int:
            return 2

        def encode(self, texts: list[str], **kwargs: object) -> Encoded:
            captured["texts"] = texts
            captured["encode_kwargs"] = kwargs
            return Encoded()

    import backend.app.rag.embeddings as embeddings

    monkeypatch.setattr(
        embeddings.importlib,
        "import_module",
        lambda name: type("Module", (), {"SentenceTransformer": FakeModel}),
    )

    encoder = SentenceTransformerEncoder("local/model")

    assert encoder.encode(["query"]) == [[1.0, 0.0]]
    assert captured["kwargs"] == {"local_files_only": True}
    assert captured["encode_kwargs"] == {
        "normalize_embeddings": True,
        "show_progress_bar": False,
    }


def test_repository_indexer_builds_both_indexes(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "runbook.md").write_text("# Retries\nBound retries to three.", encoding="utf-8")
    lexical = LexicalIndex()
    semantic = SemanticIndex(DeterministicFakeEncoder())
    indexer = RepositoryIndexer(
        RepositoryIngestor(tmp_path, repository),
        DocumentChunker(max_chars=1_000),
        lexical,
        semantic,
    )

    result = indexer.build()

    assert result.documents_indexed == 1
    assert result.chunks_indexed == 1
    assert result.chunk_ids
    assert lexical.search("retries")[0].chunk.id == result.chunk_ids[0]
    assert semantic.search("retries")[0].chunk.id == result.chunk_ids[0]
    lexical.close()


def test_gold_evidence_recall_at_5_fixture() -> None:
    case_root = Path(__file__).parents[1] / "fixtures" / "gold_retrieval"
    fixture_root = case_root / "repository"
    ground_truth = json.loads((case_root / "ground_truth.json").read_text(encoding="utf-8"))
    ingested = RepositoryIngestor(fixture_root.parent, fixture_root).ingest()
    chunks = [
        chunk
        for source in ingested.documents
        for chunk in DocumentChunker(max_chars=1_000).chunk(source)
    ]
    lexical = LexicalIndex()
    lexical.index(chunks)
    semantic = SemanticIndex(DeterministicFakeEncoder())
    semantic.index(chunks)
    results = HybridRetriever(lexical, semantic).search(ground_truth["query"], top_k=5)

    retrieved_paths = {result.chunk.source_path for result in results}
    assert set(ground_truth["gold_evidence_paths"]) & retrieved_paths
    lexical.close()
