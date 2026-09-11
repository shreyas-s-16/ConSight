from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from app.models.knowledge_base import KnowledgeBaseEmbedding, KnowledgeSourceType
from app.models.delay_reason import DelayReason, DelayCategory
from app.models.productivity_benchmark import ProductivityBenchmark
from app.models.glossary_mapping import GlossaryMapping
from app.models.wbs_node import WBSNode
from app.models.project import Project
from app.models.organization import Organization
from app.core.config import settings
import json
import logging

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """Abstract embedding provider - can use sentence-transformers or external API."""

    def __init__(self):
        self._model = None
        self._model_name = "all-MiniLM-L6-v2"

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                logger.info(f"Loaded embedding model: {self._model_name}")
            except ImportError:
                logger.warning("sentence-transformers not available, using mock embeddings")
                self._model = "mock"

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._load_model()
        if self._model == "mock":
            import random
            return [[random.uniform(-1, 1) for _ in range(384)] for _ in texts]
        return self._model.encode(texts).tolist()

    def embed_single(self, text: str) -> List[float]:
        return self.embed([text])[0]


class KnowledgeBaseService:
    """RAG service for institutional memory queries."""

    def __init__(self, db: Session):
        self.db = db
        self.embedding_provider = EmbeddingProvider()
        self.top_k = 10
        self.similarity_threshold = 0.3

    def build_source_text(self, source_type: KnowledgeSourceType, obj: Any) -> Tuple[str, Dict[str, Any]]:
        """Build searchable text content from a source object."""
        metadata = {"source_type": source_type.value, "source_id": obj.id}

        if source_type == KnowledgeSourceType.DELAY_REASON:
            delay: DelayReason = obj
            content = (
                f"Delay Category: {delay.category.value}. "
                f"Description: {delay.description}. "
                f"Impact: {delay.impact_days} days. "
                f"Critical Path: {delay.is_critical_path}. "
            )
            if delay.wbs_node:
                content += f"Activity: {delay.wbs_node.activity_name} ({delay.wbs_node.activity_code}). "
                content += f"Discipline: {delay.wbs_node.discipline}. "
                metadata.update({
                    "activity_code": delay.wbs_node.activity_code,
                    "activity_name": delay.wbs_node.activity_name,
                    "discipline": delay.wbs_node.discipline,
                    "wbs": delay.wbs_node.wbs,
                    "category": delay.category.value,
                    "impact_days": delay.impact_days,
                    "is_critical_path": delay.is_critical_path,
                })

        elif source_type == KnowledgeSourceType.PRODUCTIVITY_BENCHMARK:
            bench: ProductivityBenchmark = obj
            content = (
                f"Productivity Benchmark for {bench.discipline}. "
                f"Activity Type: {bench.activity_type}. "
                f"Unit: {bench.unit}. "
                f"Planned Duration: {bench.planned_duration_days} days. "
                f"Actual Duration: {bench.actual_duration_days} days. "
                f"Productivity Rate: {bench.productivity_rate}. "
                f"Sample Size: {bench.sample_size}. "
            )
            metadata.update({
                "discipline": bench.discipline,
                "activity_type": bench.activity_type,
                "unit": bench.unit,
                "planned_duration_days": bench.planned_duration_days,
                "actual_duration_days": bench.actual_duration_days,
                "productivity_rate": bench.productivity_rate,
                "sample_size": bench.sample_size,
            })

        elif source_type == KnowledgeSourceType.GLOSSARY_MAPPING:
            glossary: GlossaryMapping = obj
            content = (
                f"Glossary Mapping. "
                f"Source Term: {glossary.source_term}. "
                f"Standardized Term: {glossary.standardized_term}. "
            )
            if glossary.discipline:
                content += f"Discipline: {glossary.discipline}. "
            if glossary.context:
                content += f"Context: {glossary.context}. "
            metadata.update({
                "source_term": glossary.source_term,
                "standardized_term": glossary.standardized_term,
                "discipline": glossary.discipline,
                "context": glossary.context,
            })

        elif source_type == KnowledgeSourceType.WBS_NODE:
            wbs: WBSNode = obj
            content = (
                f"WBS Activity: {wbs.activity_name} ({wbs.activity_code}). "
                f"Discipline: {wbs.discipline}. "
                f"WBS Code: {wbs.wbs}. "
                f"Level: {wbs.level}. "
                f"Planned: {wbs.planned_start} to {wbs.planned_finish}. "
            )
            if wbs.actual_start:
                content += f"Actual Start: {wbs.actual_start}. "
            if wbs.actual_finish:
                content += f"Actual Finish: {wbs.actual_finish}. "
            metadata.update({
                "activity_code": wbs.activity_code,
                "activity_name": wbs.activity_name,
                "discipline": wbs.discipline,
                "wbs": wbs.wbs,
                "level": wbs.level,
                "planned_start": str(wbs.planned_start),
                "planned_finish": str(wbs.planned_finish),
                "actual_start": str(wbs.actual_start) if wbs.actual_start else None,
                "actual_finish": str(wbs.actual_finish) if wbs.actual_finish else None,
                "is_milestone": wbs.is_milestone,
            })

        elif source_type == KnowledgeSourceType.PROJECT_SUMMARY:
            project: Project = obj
            org = self.db.query(Organization).filter(Organization.id == project.organization_id).first()
            content = (
                f"Project Summary: {project.name} ({project.code}). "
                f"Organization: {org.name if org else 'Unknown'}. "
                f"Location: {project.location or 'Not specified'}. "
                f"Duration: {project.start_date} to {project.end_date}. "
            )
            metadata.update({
                "project_name": project.name,
                "project_code": project.code,
                "organization_name": org.name if org else None,
                "location": project.location,
                "start_date": str(project.start_date) if project.start_date else None,
                "end_date": str(project.end_date) if project.end_date else None,
            })

        elif source_type == KnowledgeSourceType.CLOSED_PROJECT_SUMMARY:
            project: Project = obj
            org = self.db.query(Organization).filter(Organization.id == project.organization_id).first()
            delays = self.db.query(DelayReason).filter(DelayReason.project_id == project.id).all()
            delay_summary = {}
            for d in delays:
                delay_summary[d.category.value] = delay_summary.get(d.category.value, 0) + d.impact_days

            content = (
                f"Closed Project Summary: {project.name} ({project.code}). "
                f"Organization: {org.name if org else 'Unknown'}. "
                f"Location: {project.location or 'Not specified'}. "
                f"Duration: {project.start_date} to {project.end_date}. "
                f"Total Delay Days: {sum(d.impact_days for d in delays)}. "
                f"Delay Breakdown: {json.dumps(delay_summary)}. "
            )
            metadata.update({
                "project_name": project.name,
                "project_code": project.code,
                "organization_name": org.name if org else None,
                "location": project.location,
                "start_date": str(project.start_date) if project.start_date else None,
                "end_date": str(project.end_date) if project.end_date else None,
                "total_delay_days": sum(d.impact_days for d in delays),
                "delay_breakdown": delay_summary,
            })

        else:
            content = str(obj)
            metadata = {"source_type": source_type.value, "source_id": obj.id}

        return content, metadata

    def index_all_sources(self, organization_id: int, project_id: Optional[int] = None) -> Dict[str, int]:
        """Index all institutional memory sources into the knowledge base."""
        counts = {}

        # Index Delay Reasons
        delay_query = self.db.query(DelayReason).filter(
            DelayReason.project_id == project_id
        ) if project_id else self.db.query(DelayReason).join(Project).filter(
            Project.organization_id == organization_id
        )
        delays = delay_query.all()
        counts["delay_reasons"] = self._index_objects(
            KnowledgeSourceType.DELAY_REASON, delays, organization_id, project_id
        )

        # Index Productivity Benchmarks
        bench_query = self.db.query(ProductivityBenchmark).filter(
            ProductivityBenchmark.project_id == project_id
        ) if project_id else self.db.query(ProductivityBenchmark).filter(
            ProductivityBenchmark.organization_id == organization_id
        )
        benchmarks = bench_query.all()
        counts["productivity_benchmarks"] = self._index_objects(
            KnowledgeSourceType.PRODUCTIVITY_BENCHMARK, benchmarks, organization_id, project_id
        )

        # Index Glossary Mappings
        glossary_query = self.db.query(GlossaryMapping).filter(
            GlossaryMapping.project_id == project_id
        ) if project_id else self.db.query(GlossaryMapping).filter(
            GlossaryMapping.organization_id == organization_id
        )
        glossary = glossary_query.all()
        counts["glossary_mappings"] = self._index_objects(
            KnowledgeSourceType.GLOSSARY_MAPPING, glossary, organization_id, project_id
        )

        # Index WBS Nodes
        wbs_query = self.db.query(WBSNode).filter(
            WBSNode.project_id == project_id
        ) if project_id else self.db.query(WBSNode).join(Project).filter(
            Project.organization_id == organization_id
        )
        wbs_nodes = wbs_query.all()
        counts["wbs_nodes"] = self._index_objects(
            KnowledgeSourceType.WBS_NODE, wbs_nodes, organization_id, project_id
        )

        # Index Project Summaries
        project_query = self.db.query(Project).filter(
            Project.id == project_id
        ) if project_id else self.db.query(Project).filter(
            Project.organization_id == organization_id
        )
        projects = project_query.all()
        counts["project_summaries"] = self._index_objects(
            KnowledgeSourceType.PROJECT_SUMMARY, projects, organization_id, project_id
        )

        # Index Closed Project Summaries (inactive projects)
        closed_projects = self.db.query(Project).filter(
            Project.organization_id == organization_id,
            Project.is_active == False
        ).all()
        counts["closed_project_summaries"] = self._index_objects(
            KnowledgeSourceType.CLOSED_PROJECT_SUMMARY, closed_projects, organization_id, None
        )

        self.db.commit()
        logger.info(f"Indexed knowledge base for org {organization_id}, project {project_id}: {counts}")
        return counts

    def _index_objects(
        self,
        source_type: KnowledgeSourceType,
        objects: List[Any],
        organization_id: int,
        project_id: Optional[int],
    ) -> int:
        """Index a list of objects of a given source type."""
        if not objects:
            return 0

        texts = []
        metadatas = []
        source_ids = []

        for obj in objects:
            content, metadata = self.build_source_text(source_type, obj)
            texts.append(content)
            metadatas.append(metadata)
            source_ids.append(obj.id)

        embeddings = self.embedding_provider.embed(texts)

        indexed = 0
        for i, (source_id, embedding, content, metadata) in enumerate(
            zip(source_ids, embeddings, texts, metadatas)
        ):
            existing = self.db.query(KnowledgeBaseEmbedding).filter(
                KnowledgeBaseEmbedding.source_type == source_type,
                KnowledgeBaseEmbedding.source_id == source_id,
            ).first()

            if existing:
                existing.embedding = embedding
                existing.content_text = content
                existing.content_metadata = json.dumps(metadata)
                existing.updated_at = func.now()
            else:
                embedding_record = KnowledgeBaseEmbedding(
                    organization_id=organization_id,
                    project_id=project_id,
                    source_type=source_type,
                    source_id=source_id,
                    content_text=content,
                    content_metadata=json.dumps(metadata),
                    embedding=embedding,
                )
                self.db.add(embedding_record)
            indexed += 1

        return indexed

    def query(
        self,
        query_text: str,
        organization_id: int,
        project_id: Optional[int] = None,
        source_types: Optional[List[KnowledgeSourceType]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Query the knowledge base using semantic search."""
        query_embedding = self.embedding_provider.embed_single(query_text)

        # Check if we're using PostgreSQL (supports pgvector) or SQLite
        is_postgres = self.db.bind.dialect.name == 'postgresql'

        if is_postgres:
            # PostgreSQL: use pgvector similarity search
            filter_clauses = " AND ".join([
                "organization_id = :org_id",
                *(["project_id = :proj_id"] if project_id else []),
                *([f"source_type IN :source_types"] if source_types else []),
            ])

            params = {"org_id": organization_id, "query_embedding": query_embedding}
            if project_id:
                params["proj_id"] = project_id
            if source_types:
                params["source_types"] = tuple(st.value for st in source_types)

            sql = f"""
                SELECT id, source_type, source_id, content_text, content_metadata,
                       1 - (embedding <=> :query_embedding) as similarity
                FROM knowledge_base_embeddings
                WHERE {filter_clauses}
                ORDER BY embedding <=> :query_embedding
                LIMIT :top_k
            """

            result = self.db.execute(text(sql), {**params, "top_k": top_k}).fetchall()
        else:
            # SQLite: fall back to keyword-based filtering since pgvector not available
            # Fetch all matching records and do simple text matching in Python
            query_lower = query_text.lower()
            query_words = set(query_lower.split())

            db_query = self.db.query(KnowledgeBaseEmbedding).filter(
                KnowledgeBaseEmbedding.organization_id == organization_id
            )
            if project_id:
                db_query = db_query.filter(KnowledgeBaseEmbedding.project_id == project_id)
            if source_types:
                db_query = db_query.filter(KnowledgeBaseEmbedding.source_type.in_(source_types))

            all_results = db_query.limit(top_k * 3).all()

            # Simple keyword overlap scoring
            scored_results = []
            for row in all_results:
                content_lower = row.content_text.lower()
                content_words = set(content_lower.split())
                overlap = len(query_words & content_words)
                if overlap > 0:
                    scored_results.append((overlap, row))

            scored_results.sort(key=lambda x: x[0], reverse=True)
            result = [row for _, row in scored_results[:top_k]]

        sources = []
        for row in result:
            if is_postgres:
                similarity = row.similarity
            else:
                similarity = 0.5  # Default similarity for keyword-based results
            if similarity < self.similarity_threshold:
                continue

            metadata = {}
            if row.content_metadata:
                try:
                    metadata = json.loads(row.content_metadata)
                except json.JSONDecodeError:
                    pass

            sources.append({
                "id": row.id,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "content": row.content_text,
                "metadata": metadata,
                "similarity": float(similarity),
            })

        return sources

    def generate_answer(
        self,
        query: str,
        sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate an answer from retrieved sources using LLM."""
        if not sources:
            return {
                "answer": "I couldn't find relevant information in the institutional knowledge base to answer your question.",
                "sources": [],
                "confidence": 0.0,
            }

        # Build context from sources
        context_parts = []
        for i, src in enumerate(sources, 1):
            meta = src.get("metadata", {})
            citation = f"[{i}] {src['source_type']}"
            if "activity_code" in meta:
                citation += f" - {meta['activity_code']}"
            if "discipline" in meta:
                citation += f" ({meta['discipline']})"
            if "project_name" in meta:
                citation += f" - Project: {meta['project_name']}"

            context_parts.append(f"{citation}\n{src['content']}")

        context = "\n\n---\n\n".join(context_parts)

        # For now, use a template-based answer since we may not have LLM configured
        # In production, this would call the LLM provider
        answer = self._generate_template_answer(query, sources)

        return {
            "answer": answer,
            "sources": [
                {
                    "id": i + 1,
                    "source_type": src["source_type"],
                    "source_id": src["source_id"],
                    "content": src["content"][:500] + "..." if len(src["content"]) > 500 else src["content"],
                    "metadata": src["metadata"],
                    "similarity": src["similarity"],
                }
                for i, src in enumerate(sources)
            ],
            "confidence": min(sum(s["similarity"] for s in sources) / len(sources), 1.0) if sources else 0.0,
        }

    def _generate_template_answer(self, query: str, sources: List[Dict[str, Any]]) -> str:
        """Generate a structured answer from sources without LLM (fallback)."""
        query_lower = query.lower()

        # Categorize the query type
        if any(kw in query_lower for kw in ["delay", "delayed", "slippage", "behind schedule"]):
            return self._answer_delay_query(query, sources)
        elif any(kw in query_lower for kw in ["productivity", "rate", "performance", "benchmark", "efficiency"]):
            return self._answer_productivity_query(query, sources)
        elif any(kw in query_lower for kw in ["glossary", "term", "definition", "means", "stands for"]):
            return self._answer_glossary_query(query, sources)
        elif any(kw in query_lower for kw in ["activity", "wbs", "task", "schedule"]):
            return self._answer_activity_query(query, sources)
        elif any(kw in query_lower for kw in ["project", "summary", "overview", "closed"]):
            return self._answer_project_query(query, sources)
        else:
            return self._answer_general_query(query, sources)

    def _answer_delay_query(self, query: str, sources: List[Dict[str, Any]]) -> str:
        delay_sources = [s for s in sources if s["source_type"] == "DELAY_REASON"]
        if not delay_sources:
            return f"Based on the institutional knowledge base, I found {len(sources)} relevant documents but no specific delay records matching your query."

        total_delays = len(delay_sources)
        total_days = sum(s["metadata"].get("impact_days", 0) for s in delay_sources)
        categories = {}
        for s in delay_sources:
            cat = s["metadata"].get("category", "UNKNOWN")
            categories[cat] = categories.get(cat, 0) + 1

        top_category = max(categories.items(), key=lambda x: x[1])[0] if categories else "N/A"

        answer = (
            f"Found {total_delays} delay records with a total impact of {total_days} days. "
            f"The most common delay category is {top_category} ({categories.get(top_category, 0)} occurrences).\n\n"
        )

        # Add specific examples
        answer += "Key delay records:\n"
        for i, src in enumerate(delay_sources[:5], 1):
            meta = src["metadata"]
            answer += (
                f"  {i}. {meta.get('activity_code', 'N/A')} - {meta.get('category', 'UNKNOWN')}: "
                f"{meta.get('impact_days', 0)} days - {src['content'][:200]}...\n"
            )

        return answer

    def _answer_productivity_query(self, query: str, sources: List[Dict[str, Any]]) -> str:
        bench_sources = [s for s in sources if s["source_type"] == "PRODUCTIVITY_BENCHMARK"]
        if not bench_sources:
            return f"Based on the institutional knowledge base, I found {len(sources)} relevant documents but no specific productivity benchmarks matching your query."

        disciplines = {}
        for s in bench_sources:
            disc = s["metadata"].get("discipline", "UNKNOWN")
            if disc not in disciplines:
                disciplines[disc] = []
            disciplines[disc].append(s["metadata"])

        answer = f"Found productivity benchmarks across {len(disciplines)} disciplines:\n\n"
        for disc, benches in disciplines.items():
            avg_rate = sum(b.get("productivity_rate", 0) for b in benches if b.get("productivity_rate")) / len(benches)
            answer += (
                f"  **{disc}**: {len(benches)} activity types, "
                f"avg productivity rate: {avg_rate:.1%}\n"
            )

        return answer

    def _answer_glossary_query(self, query: str, sources: List[Dict[str, Any]]) -> str:
        glossary_sources = [s for s in sources if s["source_type"] == "GLOSSARY_MAPPING"]
        if not glossary_sources:
            return f"Based on the institutional knowledge base, I found {len(sources)} relevant documents but no glossary mappings matching your query."

        answer = f"Found {len(glossary_sources)} glossary mappings:\n\n"
        for i, src in enumerate(glossary_sources[:10], 1):
            meta = src["metadata"]
            answer += (
                f"  {i}. **{meta.get('source_term', 'N/A')}** → "
                f"{meta.get('standardized_term', 'N/A')}"
            )
            if meta.get("discipline"):
                answer += f" ({meta['discipline']})"
            answer += "\n"

        return answer

    def _answer_activity_query(self, query: str, sources: List[Dict[str, Any]]) -> str:
        wbs_sources = [s for s in sources if s["source_type"] == "WBS_NODE"]
        if not wbs_sources:
            return f"Based on the institutional knowledge base, I found {len(sources)} relevant documents but no WBS activities matching your query."

        answer = f"Found {len(wbs_sources)} WBS activities:\n\n"
        for i, src in enumerate(wbs_sources[:10], 1):
            meta = src["metadata"]
            status = "Completed" if meta.get("actual_finish") else ("In Progress" if meta.get("actual_start") else "Not Started")
            answer += (
                f"  {i}. **{meta.get('activity_code', 'N/A')}** - {meta.get('activity_name', 'N/A')}\n"
                f"     Discipline: {meta.get('discipline', 'N/A')}, WBS: {meta.get('wbs', 'N/A')}\n"
                f"     Planned: {meta.get('planned_start')} to {meta.get('planned_finish')}\n"
                f"     Status: {status}\n\n"
            )

        return answer

    def _answer_project_query(self, query: str, sources: List[Dict[str, Any]]) -> str:
        project_sources = [s for s in sources if s["source_type"] in ("PROJECT_SUMMARY", "CLOSED_PROJECT_SUMMARY")]
        if not project_sources:
            return f"Based on the institutional knowledge base, I found {len(sources)} relevant documents but no project summaries matching your query."

        answer = f"Found {len(project_sources)} project summaries:\n\n"
        for i, src in enumerate(project_sources, 1):
            meta = src["metadata"]
            answer += (
                f"  {i}. **{meta.get('project_name', 'N/A')}** ({meta.get('project_code', 'N/A')})\n"
                f"     Organization: {meta.get('organization_name', 'N/A')}\n"
                f"     Location: {meta.get('location', 'N/A')}\n"
                f"     Duration: {meta.get('start_date')} to {meta.get('end_date')}\n"
            )
            if "total_delay_days" in meta:
                answer += f"     Total Delay Days: {meta['total_delay_days']}\n"
            answer += "\n"

        return answer

    def _answer_general_query(self, query: str, sources: List[Dict[str, Any]]) -> str:
        # Group by source type
        by_type = {}
        for s in sources:
            st = s["source_type"]
            if st not in by_type:
                by_type[st] = []
            by_type[st].append(s)

        answer = f"Found {len(sources)} relevant documents across {len(by_type)} categories:\n\n"
        for st, srcs in by_type.items():
            answer += f"  **{st.replace('_', ' ').title()}**: {len(srcs)} records\n"

        answer += "\nTop matches:\n"
        for i, src in enumerate(sources[:5], 1):
            meta = src["metadata"]
            answer += f"  {i}. [{src['source_type']}] {src['content'][:200]}...\n"

        return answer


from sqlalchemy.sql import func