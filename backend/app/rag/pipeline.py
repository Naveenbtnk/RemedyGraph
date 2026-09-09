"""Repository-to-index orchestration without audit workflow or model calls."""

from backend.app.rag.chunking import DocumentChunker
from backend.app.rag.contracts import RepositoryIndexResult
from backend.app.rag.embeddings import SemanticIndex
from backend.app.rag.index import LexicalIndex
from backend.app.rag.ingestion import RepositoryIngestor


class RepositoryIndexer:
    """Build the Day 2 lexical and vector indexes from one safe ingestion pass."""

    def __init__(
        self,
        ingestor: RepositoryIngestor,
        chunker: DocumentChunker,
        lexical: LexicalIndex,
        semantic: SemanticIndex,
    ) -> None:
        self.ingestor = ingestor
        self.chunker = chunker
        self.lexical = lexical
        self.semantic = semantic

    def build(self) -> RepositoryIndexResult:
        ingestion = self.ingestor.ingest()
        chunks = [
            chunk for document in ingestion.documents for chunk in self.chunker.chunk(document)
        ]
        self.lexical.index(chunks)
        self.semantic.index(chunks)
        return RepositoryIndexResult(
            documents_indexed=len(ingestion.documents),
            chunks_indexed=len(chunks),
            chunk_ids=[chunk.id for chunk in chunks],
            failures=ingestion.failures,
            skipped=ingestion.skipped,
            total_bytes=ingestion.total_bytes,
        )
