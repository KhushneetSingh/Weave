"""
RAGAgent — Retrieval-Augmented Generation with FAISS and multi-hop retrieval.

Uses sentence-transformers (all-MiniLM-L6-v2) for embedding and FAISS for
vector search. 15 hardcoded AI-topic documents. Two-hop retrieval with
minimum 4 chunks total.
"""

from __future__ import annotations

import json
from typing import ClassVar

import faiss
import numpy as np

from app.agents.base import BaseAgent
from app.schemas.context import AgentOutput, Citation, SharedContext

# ── Hardcoded AI-topic knowledge base ────────────────────────────────────────

_DOCUMENTS: list[dict[str, str]] = [
    {"id": "doc_01", "text": "Retrieval-Augmented Generation (RAG) is a technique that combines information retrieval with text generation. It first retrieves relevant documents from a knowledge base, then feeds those documents as context to a language model to generate more accurate and grounded responses."},
    {"id": "doc_02", "text": "Vector databases store embeddings — dense numerical representations of text — and enable fast similarity search. Popular vector databases include Pinecone, Weaviate, Milvus, and Chroma. They are essential components of modern RAG pipelines."},
    {"id": "doc_03", "text": "Transformers are a neural network architecture introduced in the 2017 paper 'Attention Is All You Need'. They use self-attention mechanisms to process sequences in parallel, making them much faster than RNNs for long sequences."},
    {"id": "doc_04", "text": "Large Language Models (LLMs) like GPT-4, Claude, and Llama are trained on massive text corpora. They learn statistical patterns in language and can generate coherent text, answer questions, and perform reasoning tasks."},
    {"id": "doc_05", "text": "Fine-tuning is the process of adapting a pre-trained model to a specific task or domain by training it on a smaller, task-specific dataset. This is more efficient than training from scratch and often yields better results for specialized applications."},
    {"id": "doc_06", "text": "Prompt engineering is the art of crafting effective input prompts to get desired outputs from language models. Techniques include few-shot examples, chain-of-thought prompting, and system instructions."},
    {"id": "doc_07", "text": "Embeddings are dense vector representations of text that capture semantic meaning. Similar texts have similar embedding vectors. Models like all-MiniLM-L6-v2 and text-embedding-ada-002 are commonly used for generating embeddings."},
    {"id": "doc_08", "text": "FAISS (Facebook AI Similarity Search) is a library for efficient similarity search of dense vectors. It supports exact and approximate nearest neighbor search, and can handle billions of vectors with GPU acceleration."},
    {"id": "doc_09", "text": "Multi-agent systems consist of multiple AI agents that collaborate to solve complex tasks. Each agent specializes in a specific capability, and an orchestrator coordinates their interactions and resolves conflicts between their outputs."},
    {"id": "doc_10", "text": "Hallucination in AI refers to when a language model generates information that is factually incorrect or not grounded in the provided context. RAG helps reduce hallucination by providing relevant source documents as context."},
    {"id": "doc_11", "text": "Chunking is the process of splitting large documents into smaller, semantically meaningful pieces for retrieval. Strategies include fixed-size chunks, sentence-based splitting, and recursive character splitting with overlap."},
    {"id": "doc_12", "text": "Reinforcement Learning from Human Feedback (RLHF) is a technique used to align language models with human preferences. A reward model is trained on human comparisons, then used to fine-tune the language model via reinforcement learning."},
    {"id": "doc_13", "text": "The attention mechanism allows models to focus on different parts of the input when producing each part of the output. Self-attention computes relationships between all positions in a sequence, enabling the model to capture long-range dependencies."},
    {"id": "doc_14", "text": "Tokenization is the process of converting text into tokens — the basic units that language models process. Common tokenizers include BPE (Byte Pair Encoding), WordPiece, and SentencePiece. The choice of tokenizer affects model performance and vocabulary size."},
    {"id": "doc_15", "text": "Evaluation of RAG systems involves measuring retrieval quality (precision, recall, MRR) and generation quality (faithfulness, relevance, coherence). Automated metrics and human evaluation are both used to assess end-to-end performance."},
]

# ── Lazy-loaded FAISS index + embedder ───────────────────────────────────────

_faiss_index: faiss.IndexFlatL2 | None = None
_embedder: object | None = None
_doc_texts: list[str] = [d["text"] for d in _DOCUMENTS]
_doc_ids: list[str] = [d["id"] for d in _DOCUMENTS]


def _get_embedder():
    """Lazy-load the sentence-transformers model."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_faiss_index() -> faiss.IndexFlatL2:
    """Lazy-load the FAISS index, building it on first call."""
    global _faiss_index
    if _faiss_index is None:
        embedder = _get_embedder()
        embeddings = embedder.encode(_doc_texts, convert_to_numpy=True)
        dim = embeddings.shape[1]
        _faiss_index = faiss.IndexFlatL2(dim)
        _faiss_index.add(embeddings.astype(np.float32))
    return _faiss_index


def _retrieve(query: str, top_k: int = 2) -> list[tuple[str, str, float]]:
    """Embed *query* and retrieve top-k (doc_id, text, distance) tuples."""
    embedder = _get_embedder()
    index = _get_faiss_index()
    q_vec = embedder.encode([query], convert_to_numpy=True).astype(np.float32)
    distances, indices = index.search(q_vec, top_k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if 0 <= idx < len(_doc_texts):
            results.append((_doc_ids[idx], _doc_texts[idx], float(dist)))
    return results


# ── RAG Agent ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a knowledgeable AI assistant. Answer the user's question using ONLY
the retrieved context chunks provided below. If the context does not contain
enough information, say so.

For every claim in your answer, cite the chunk IDs that support it.

Return ONLY a JSON object:
{
  "answer": "your detailed answer here",
  "citations": [
    {"claim": "specific claim text", "chunk_ids": ["doc_01", "doc_03"]}
  ]
}
"""


class RAGAgent(BaseAgent):
    """RAG agent with FAISS-based multi-hop retrieval."""

    agent_id: str = "rag"
    max_budget: int = 2000
    system_prompt: str = _SYSTEM_PROMPT

    _retrieved_chunks: ClassVar[list[tuple[str, str, float]]] = []

    def _build_messages(self, context: SharedContext) -> list[dict]:
        # ── Multi-hop retrieval ──────────────────────────────────────
        # Hop 1: retrieve top-2 chunks from the original query
        hop1 = _retrieve(context.query, top_k=2)

        # Hop 2: form a second query from hop-1 results, retrieve 2 more
        hop1_text = " ".join(text for _, text, _ in hop1)
        second_query = f"{context.query} {hop1_text[:200]}"
        hop2 = _retrieve(second_query, top_k=2)

        # Deduplicate while preserving order
        seen: set[str] = set()
        all_chunks: list[tuple[str, str, float]] = []
        for chunk in hop1 + hop2:
            if chunk[0] not in seen:
                seen.add(chunk[0])
                all_chunks.append(chunk)

        # Ensure at least 4 chunks
        if len(all_chunks) < 4:
            extras = _retrieve(context.query, top_k=6)
            for chunk in extras:
                if chunk[0] not in seen:
                    seen.add(chunk[0])
                    all_chunks.append(chunk)
                if len(all_chunks) >= 4:
                    break

        self.__class__._retrieved_chunks = all_chunks

        # Format chunks for the prompt
        chunk_text = "\n\n".join(
            f"[{cid}] {text}" for cid, text, _ in all_chunks
        )

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Context chunks:\n{chunk_text}\n\nQuestion: {context.query}"},
        ]

    def _parse_output(self, parsed: dict, context: SharedContext) -> AgentOutput:
        answer = parsed.get("answer", parsed.get("raw", "No answer generated."))
        raw_citations = parsed.get("citations", [])

        citations: list[Citation] = []
        for c in raw_citations:
            citations.append(
                Citation(
                    claim=c.get("claim", ""),
                    chunk_ids=c.get("chunk_ids", []),
                    agent_id=self.agent_id,
                )
            )

        return AgentOutput(
            agent_id=self.agent_id,
            content=answer,
            confidence=0.85,
            citations=citations,
        )
