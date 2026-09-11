from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.database import get_db
from app.services.knowledge_base_service import KnowledgeBaseService
from app.schemas.knowledge_base import (
    KnowledgeBaseQueryRequest,
    KnowledgeBaseQueryResponse,
    KnowledgeBaseIndexRequest,
    KnowledgeBaseIndexResponse,
    KnowledgeBaseStatsResponse,
)
from app.models.knowledge_base import KnowledgeBaseEmbedding, KnowledgeSourceType
from app.core.auth import get_current_user, require_organization_access
from app.models.user import User
from app.models.project import Project

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


@router.post("/query", response_model=KnowledgeBaseQueryResponse)
async def query_knowledge_base(
    request: KnowledgeBaseQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organization_access),
):
    """
    Query the institutional knowledge base using natural language.
    Returns an answer with cited sources from delay reasons, productivity benchmarks,
    glossary mappings, WBS nodes, and project summaries.
    """
    # Get organization_id from user
    organization_id = current_user.organization_id

    # If project_id provided, verify access
    if request.project_id:
        project = db.query(Project).filter(
            Project.id == request.project_id,
            Project.organization_id == organization_id
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )

    # Convert source_types strings to enum
    source_types = None
    if request.source_types:
        source_types = [KnowledgeSourceType(st) for st in request.source_types]

    # Query the knowledge base
    service = KnowledgeBaseService(db)
    sources = service.query(
        query_text=request.query,
        organization_id=organization_id,
        project_id=request.project_id,
        source_types=source_types,
        top_k=request.top_k,
    )

    # Generate answer from sources
    result = service.generate_answer(request.query, sources)

    return KnowledgeBaseQueryResponse(
        answer=result["answer"],
        sources=result["sources"],
        confidence=result["confidence"],
    )


@router.post("/index", response_model=KnowledgeBaseIndexResponse)
async def index_knowledge_base(
    request: KnowledgeBaseIndexRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organization_access),
):
    """
    Build or rebuild the knowledge base embeddings from institutional memory sources.
    Sources include: delay reasons, productivity benchmarks, glossary mappings,
    WBS nodes, project summaries, and closed project summaries.
    """
    organization_id = current_user.organization_id

    if request.project_id:
        project = db.query(Project).filter(
            Project.id == request.project_id,
            Project.organization_id == organization_id
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )

    service = KnowledgeBaseService(db)
    counts = service.index_all_sources(organization_id, request.project_id)

    scope = f"project {request.project_id}" if request.project_id else "all projects"
    return KnowledgeBaseIndexResponse(
        counts=counts,
        message=f"Successfully indexed knowledge base for {scope}",
    )


@router.get("/stats", response_model=KnowledgeBaseStatsResponse)
async def get_knowledge_base_stats(
    project_id: Optional[int] = Query(None, description="Optional project ID to filter stats"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_organization_access),
):
    """Get statistics about the knowledge base embeddings."""
    organization_id = current_user.organization_id

    query = db.query(
        KnowledgeBaseEmbedding.source_type,
        func.count(KnowledgeBaseEmbedding.id)
    ).filter(
        KnowledgeBaseEmbedding.organization_id == organization_id
    )

    if project_id:
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.organization_id == organization_id
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )
        query = query.filter(KnowledgeBaseEmbedding.project_id == project_id)

    by_source_type = dict(query.group_by(KnowledgeBaseEmbedding.source_type).all())

    # By project
    project_query = db.query(
        KnowledgeBaseEmbedding.project_id,
        func.count(KnowledgeBaseEmbedding.id)
    ).filter(
        KnowledgeBaseEmbedding.organization_id == organization_id,
        KnowledgeBaseEmbedding.project_id.isnot(None)
    ).group_by(KnowledgeBaseEmbedding.project_id).all()

    project_names = {p.id: p.name for p in db.query(Project).filter(
        Project.organization_id == organization_id
    ).all()}

    by_project = {
        project_names.get(pid, f"Project {pid}"): count
        for pid, count in project_query
    }

    total = sum(by_source_type.values())

    return KnowledgeBaseStatsResponse(
        total_embeddings=total,
        by_source_type={st.value: count for st, count in by_source_type.items()},
        by_project=by_project,
        organization_id=organization_id,
    )


@router.get("/sources", response_model=List[str])
async def list_source_types(
    current_user: User = Depends(get_current_user),
):
    """List available knowledge source types for filtering."""
    return [st.value for st in KnowledgeSourceType]