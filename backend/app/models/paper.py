from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(primary_key=True)
    openalex_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date)
    doi: Mapped[str | None] = mapped_column(String(512))
    normalized_doi: Mapped[str | None] = mapped_column(String(512), unique=True)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(200))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    requested: Mapped[int] = mapped_column(Integer)
    saved: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    openalex_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

class PaperTopic(Base):
    __tablename__ = "paper_topics"
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id', ondelete='CASCADE'), primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id', ondelete='CASCADE'), primary_key=True)
    provenance: Mapped[str] = mapped_column(String(40), default='ingestion_query')

class PaperAuthor(Base):
    __tablename__ = "paper_authors"
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id', ondelete='CASCADE'), primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey('authors.id', ondelete='CASCADE'), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[str] = mapped_column(String(40), default='openalex')

class Citation(Base):
    __tablename__ = "paper_citations"
    citing_id: Mapped[int] = mapped_column(ForeignKey('papers.id', ondelete='CASCADE'), primary_key=True)
    cited_openalex_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provenance: Mapped[str] = mapped_column(String(40), default='openalex')


from pgvector.sqlalchemy import Vector
class PaperEmbedding(Base):
    __tablename__ = 'paper_embeddings'
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id',ondelete='CASCADE'),primary_key=True)
    model_name: Mapped[str] = mapped_column(String(255),primary_key=True)
    model_revision: Mapped[str] = mapped_column(String(64),primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64),nullable=False)
    vector: Mapped[object] = mapped_column(Vector(384),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())


class CollectionJob(Base):
    __tablename__='collection_jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(200))
    target: Mapped[int] = mapped_column(Integer)
    processed: Mapped[int] = mapped_column(Integer,default=0)
    next_page: Mapped[int] = mapped_column(Integer,default=1)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())


class Experiment(Base):
    __tablename__ = 'gnn_experiments'
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    dataset_hash: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

class CandidateLink(Base):
    __tablename__ = 'gnn_candidate_links'
    experiment_id: Mapped[int] = mapped_column(ForeignKey('gnn_experiments.id',ondelete='CASCADE'),primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('papers.id'),primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey('papers.id'),primary_key=True)
    rank: Mapped[int] = mapped_column(Integer,nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    popularity_score: Mapped[float | None] = mapped_column(nullable=True)
    popularity_rank: Mapped[int | None] = mapped_column(Integer,nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON,nullable=True)


class ResearchAnalysis(Base):
    __tablename__='research_analyses'
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey('gnn_experiments.id'))
    source_id: Mapped[int] = mapped_column(ForeignKey('papers.id'))
    target_id: Mapped[int] = mapped_column(ForeignKey('papers.id'))
    status: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    synthesis: Mapped[dict | None] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(100),default='deterministic')
    model_name: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())


class GenerationAttempt(Base):
    __tablename__='generation_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey('research_analyses.id'))
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
