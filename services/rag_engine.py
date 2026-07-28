"""Fundamental Engine (RAG) — LlamaIndex + Qdrant + OpenAI.

Membungkus pipeline Section 4 blueprint dalam satu kelas singleton dengan
inisialisasi lazy: import llama_index/qdrant hanya terjadi saat endpoint
RAG benar-benar dipakai, sehingga API dan test suite tetap bisa berjalan
tanpa dependensi berat atau API key.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

DEFAULT_LLM_MODEL = os.getenv("AEGIS_LLM_MODEL", "gpt-4o")
DEFAULT_EMBED_MODEL = os.getenv("AEGIS_EMBED_MODEL", "text-embedding-3-small")
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "financial_reports")


class RAGEngine:
    """RAG laporan keuangan: ingest PDF -> vector store -> tanya jawab."""

    def __init__(self) -> None:
        self._index: Optional[Any] = None
        self._storage_context: Optional[Any] = None
        self._initialized = False
        self.ingested_files: list[str] = []

    # ------------------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        """True jika minimal satu dokumen sudah ter-ingest."""
        return self._index is not None

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your-openai-api-key-here":
            raise RuntimeError(
                "OPENAI_API_KEY belum diset. Isi environment variable atau file .env "
                "sebelum memakai fitur RAG."
            )

        # Komponen RAG sengaja opsional agar pemasangan fitur utama tetap
        # ringan. Bila belum terpasang, pesannya harus langsung memberi tahu
        # cara memperbaikinya — bukan melempar ImportError yang membingungkan.
        try:
            from llama_index.core import Settings, StorageContext
            from llama_index.core.node_parser import SentenceSplitter
            from llama_index.embeddings.openai import OpenAIEmbedding
            from llama_index.llms.openai import OpenAI
            from llama_index.vector_stores.qdrant import QdrantVectorStore
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "Fitur baca laporan PDF membutuhkan komponen tambahan yang belum "
                "terpasang. Jalankan:\n\n"
                "    pip install -r requirements-rag.txt\n\n"
                "Seluruh fitur lain (saham, emas, makro, uji mundur, riwayat) "
                f"tetap berjalan normal tanpa ini. Detail: {exc}"
            ) from exc

        Settings.llm = OpenAI(model=DEFAULT_LLM_MODEL, api_key=api_key, temperature=0.1)
        Settings.embed_model = OpenAIEmbedding(model=DEFAULT_EMBED_MODEL, api_key=api_key)
        Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)

        qdrant_url = os.getenv("QDRANT_URL", "").strip()
        client = QdrantClient(url=qdrant_url) if qdrant_url else QdrantClient(location=":memory:")
        vector_store = QdrantVectorStore(client=client, collection_name=DEFAULT_COLLECTION)
        self._storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self._initialized = True

    # ------------------------------------------------------------------
    def ingest_pdf(self, file_path: str, file_name: str) -> int:
        """Proses satu PDF ke vector store. Mengembalikan jumlah halaman."""
        self._ensure_initialized()

        from llama_index.core import SimpleDirectoryReader, VectorStoreIndex  # noqa: F401

        documents = SimpleDirectoryReader(input_files=[file_path]).load_data()
        for doc in documents:
            doc.metadata["file_name"] = file_name

        if self._index is None:
            self._index = VectorStoreIndex.from_documents(
                documents, storage_context=self._storage_context, show_progress=True
            )
        else:
            for doc in documents:
                self._index.insert(doc)

        self.ingested_files.append(file_name)
        return len(documents)

    # ------------------------------------------------------------------
    def query(self, question: str, top_k: int = 3) -> tuple[str, list[dict]]:
        """Tanya jawab atas dokumen yang sudah di-ingest."""
        if self._index is None:
            raise RuntimeError("Belum ada dokumen. Upload PDF terlebih dahulu.")

        query_engine = self._index.as_query_engine(
            similarity_top_k=top_k, response_mode="compact"
        )
        response = query_engine.query(question)
        sources = [
            {
                "content": node.node.get_content(),
                "page_label": node.node.metadata.get("page_label", "N/A"),
                "file_name": node.node.metadata.get("file_name", "Unknown"),
                "score": float(node.score) if node.score is not None else 0.0,
            }
            for node in response.source_nodes
        ]
        return str(response), sources

    # ------------------------------------------------------------------
    def fundamental_score(self, ticker: str) -> Optional[dict]:
        """Minta LLM menilai kesehatan fundamental 0-100 dari dokumen ter-ingest.

        Mengembalikan None jika tidak ada dokumen atau jawaban tidak bisa diparse.
        """
        if self._index is None:
            return None

        prompt = (
            f"Berdasarkan laporan keuangan yang tersedia untuk {ticker}, nilai "
            "kesehatan fundamental perusahaan pada skala 0-100 dengan "
            "mempertimbangkan profitabilitas (ROE, margin), leverage (DER), "
            "pertumbuhan pendapatan/laba, dan arus kas. Jawab HANYA dalam format: "
            "SCORE: <angka 0-100> | RATIONALE: <1-2 kalimat>."
        )
        try:
            answer, _ = self.query(prompt, top_k=5)
            match = re.search(r"SCORE\s*:\s*(\d{1,3}(?:\.\d+)?)", answer, re.IGNORECASE)
            if not match:
                return None
            score = max(0.0, min(100.0, float(match.group(1))))
            rationale_match = re.search(r"RATIONALE\s*:\s*(.+)", answer, re.IGNORECASE | re.DOTALL)
            rationale = rationale_match.group(1).strip() if rationale_match else answer.strip()
            return {"score": round(score, 2), "rationale": rationale, "source": "rag"}
        except Exception:
            return None


# Singleton yang dipakai API
rag_engine = RAGEngine()
