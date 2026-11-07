"""Contracts for future research components. No algorithms are implemented in Phase 1."""
from typing import Protocol, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PaperRecord:
    source_id: str
    title: str
    abstract: str | None = None


class PaperSource(Protocol):
    def search(self, query: str, limit: int) -> Sequence[PaperRecord]: ...


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class GraphBuilder(Protocol):
    def build(self, papers: Sequence[PaperRecord]) -> object: ...


class LinkPredictor(Protocol):
    def train(self, graph: object) -> None: ...
    def rank(self, graph: object) -> Sequence[object]: ...


class GapGenerator(Protocol):
    def generate(self, query: str, evidence: Sequence[PaperRecord]) -> Sequence[object]: ...
