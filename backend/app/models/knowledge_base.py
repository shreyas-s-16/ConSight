from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from pgvector.sqlalchemy import Vector
import enum


class KnowledgeSourceType(str, enum.Enum):
    DELAY_REASON = "DELAY_REASON"
    PRODUCTIVITY_BENCHMARK = "PRODUCTIVITY_BENCHMARK"
    GLOSSARY_MAPPING = "GLOSSARY_MAPPING"
    WBS_NODE = "WBS_NODE"
    PROJECT_SUMMARY = "PROJECT_SUMMARY"
    CLOSED_PROJECT_SUMMARY = "CLOSED_PROJECT_SUMMARY"


class KnowledgeBaseEmbedding(Base):
    __tablename__ = "knowledge_base_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    source_type = Column(SQLEnum(KnowledgeSourceType), nullable=False, index=True)
    source_id = Column(Integer, nullable=False, index=True)
    content_text = Column(Text, nullable=False)
    content_metadata = Column(Text, nullable=True)
    embedding = Column(Vector(384), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization = relationship("Organization", backref="knowledge_embeddings")
    project = relationship("Project", backref="knowledge_embeddings")

    __table_args__ = (
        Index("ix_knowledge_base_embeddings_org_source", "organization_id", "source_type"),
        Index("ix_knowledge_base_embeddings_project_source", "project_id", "source_type"),
        Index("ix_knowledge_base_embeddings_source_lookup", "source_type", "source_id", unique=True),
    )