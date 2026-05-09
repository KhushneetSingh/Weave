"""
WebSearchTool — stub that generates realistic fake search results.

Returns a list of dicts with url, snippet, and relevance_score
based on query keywords.
"""

from __future__ import annotations

import hashlib
import random

from app.schemas.tools import ToolResult
from app.tools.base import BaseTool


# Pre-built snippets keyed by broad topic categories
_FAKE_RESULTS_DB: dict[str, list[dict]] = {
    "ai": [
        {"url": "https://arxiv.org/abs/2301.00234", "snippet": "Recent advances in artificial intelligence have shown that transformer-based architectures achieve state-of-the-art performance across multiple benchmarks.", "relevance_score": 0.95},
        {"url": "https://en.wikipedia.org/wiki/Artificial_intelligence", "snippet": "Artificial intelligence (AI) is the simulation of human intelligence processes by machines, especially computer systems.", "relevance_score": 0.90},
        {"url": "https://openai.com/research", "snippet": "OpenAI conducts fundamental research in AI with the goal of ensuring artificial general intelligence benefits all of humanity.", "relevance_score": 0.85},
        {"url": "https://deepmind.google/research", "snippet": "DeepMind's research covers areas from protein folding to reinforcement learning, pushing the boundaries of AI capabilities.", "relevance_score": 0.82},
        {"url": "https://ai.meta.com/blog/", "snippet": "Meta AI publishes research on large language models, computer vision, and embodied AI systems.", "relevance_score": 0.78},
    ],
    "retrieval": [
        {"url": "https://arxiv.org/abs/2005.11401", "snippet": "Retrieval-Augmented Generation (RAG) combines retrieval mechanisms with generative models to produce more accurate and grounded responses.", "relevance_score": 0.97},
        {"url": "https://www.pinecone.io/learn/retrieval-augmented-generation/", "snippet": "RAG is a technique that enhances LLM outputs by fetching relevant documents from a knowledge base before generation.", "relevance_score": 0.93},
        {"url": "https://docs.llamaindex.ai/en/stable/", "snippet": "LlamaIndex provides a framework for connecting custom data sources to large language models via retrieval pipelines.", "relevance_score": 0.88},
        {"url": "https://python.langchain.com/docs/tutorials/rag/", "snippet": "LangChain's RAG tutorial demonstrates how to build a retrieval-augmented generation pipeline with vector stores.", "relevance_score": 0.85},
    ],
    "machine_learning": [
        {"url": "https://scikit-learn.org/stable/", "snippet": "scikit-learn provides simple and efficient tools for predictive data analysis built on NumPy, SciPy, and matplotlib.", "relevance_score": 0.91},
        {"url": "https://pytorch.org/tutorials/", "snippet": "PyTorch is an open-source machine learning framework that accelerates the path from research prototyping to production deployment.", "relevance_score": 0.89},
        {"url": "https://www.tensorflow.org/", "snippet": "TensorFlow is an end-to-end open-source platform for machine learning with a comprehensive ecosystem of tools.", "relevance_score": 0.87},
    ],
    "default": [
        {"url": "https://en.wikipedia.org/wiki/Main_Page", "snippet": "Wikipedia is a free online encyclopedia that anyone can edit, covering millions of articles across all fields of knowledge.", "relevance_score": 0.60},
        {"url": "https://stackoverflow.com/", "snippet": "Stack Overflow is the largest online community for developers to learn, share knowledge, and build careers.", "relevance_score": 0.55},
        {"url": "https://github.com/", "snippet": "GitHub is where developers collaborate on code, manage projects, and build software together.", "relevance_score": 0.50},
    ],
}

_TOPIC_KEYWORDS = {
    "ai": {"ai", "artificial", "intelligence", "llm", "language", "model", "gpt", "neural", "deep", "learning", "transformer"},
    "retrieval": {"retrieval", "rag", "augmented", "generation", "vector", "embedding", "search", "document", "chunk"},
    "machine_learning": {"machine", "ml", "training", "classification", "regression", "supervised", "unsupervised"},
}


class WebSearchTool(BaseTool):
    """Stub web search — returns realistic fake results based on query keywords."""

    name: str = "web_search"
    timeout_seconds: float = 10.0

    async def _execute(self, input: dict) -> ToolResult:
        query: str = input.get("query", "").strip()
        if not query:
            return self.on_empty()

        # Determine topic from keywords
        query_words = set(query.lower().split())
        best_topic = "default"
        best_overlap = 0
        for topic, keywords in _TOPIC_KEYWORDS.items():
            overlap = len(query_words & keywords)
            if overlap > best_overlap:
                best_overlap = overlap
                best_topic = topic

        results = list(_FAKE_RESULTS_DB.get(best_topic, _FAKE_RESULTS_DB["default"]))

        # Add a query-specific result
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        results.insert(0, {
            "url": f"https://research.example.com/paper/{query_hash}",
            "snippet": f"A comprehensive study addressing: {query[:100]}. This paper examines the key concepts and recent developments in this area.",
            "relevance_score": 0.96,
        })

        # Shuffle slightly and limit to 3-5 results
        random.shuffle(results)
        results = results[:random.randint(3, min(5, len(results)))]

        # Sort by relevance descending
        results.sort(key=lambda r: r["relevance_score"], reverse=True)

        return ToolResult(
            tool_name=self.name,
            status="success",
            data=results,
        )
