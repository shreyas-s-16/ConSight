from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from app.models.knowledge_base import KnowledgeSourceType


class KnowledgeBaseQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    project_id: Optional[int] = Field(None, description="Optional project ID to scope search")
    source_types: Optional[List[KnowledgeSourceType]] = Field(None, description="Optional source types to filter")
    top_k: int = Field(10, ge=1, le=50, description="Number of results to retrieve")


class KnowledgeSourceCitation(BaseModel):
    id: int
    source_type: str
    source_id: int
    content: str
    metadata: Dict[str, Any]
    similarity: float


class KnowledgeBaseQueryResponse(BaseModel):
    answer: str
    sources: List[KnowledgeSourceCitation]
    confidence: float


class KnowledgeBaseIndexRequest(BaseModel):
    project_id: Optional[int] = Field(None, description="Optional project ID to index (None = all projects in org)")


class KnowledgeBaseIndexResponse(BaseModel):
    counts: Dict[str, int]
    message: str


class KnowledgeBaseStatsResponse(BaseModel):
    total_embeddings: int
    by_source_type: Dict[str, int]
    by_project: Dict[str, int]
    organization_id: int