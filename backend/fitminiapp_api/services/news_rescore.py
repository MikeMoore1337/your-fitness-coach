from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from fitminiapp_api.models.news import NewsCluster, NewsItem, NewsSource
from fitminiapp_api.services.news_freshness import is_fresh_publication
from fitminiapp_api.services.news_ingestion import latest_items_by_source, score_candidate, utcnow
from fitminiapp_api.services.news_state import transition_news_cluster


def rescore_freshness_blocked_clusters(
    db: Session,
    *,
    candidate_threshold: int,
    now: datetime | None = None,
    limit: int = 1000,
) -> int:
    """Re-evaluate clustered items that were blocked only by the old freshness window."""
    current = now or utcnow()
    promoted = 0
    clusters = (
        db.query(NewsCluster)
        .filter(NewsCluster.status == "clustered", NewsCluster.primary_item_id.is_not(None))
        .order_by(NewsCluster.updated_at.desc())
        .limit(limit)
        .all()
    )
    for cluster in clusters:
        previous_risks = list(cluster.risk_flags or [])
        if "source_not_current_month" not in previous_risks:
            continue
        primary = db.get(NewsItem, cluster.primary_item_id)
        if primary is None or not is_fresh_publication(primary.published_at, now=current):
            continue
        source = db.get(NewsSource, primary.source_id)
        if source is None:
            continue
        items = db.query(NewsItem).filter(NewsItem.cluster_id == cluster.id).all()
        representative_items = latest_items_by_source(items)
        score, topic, reasons, risks = score_candidate(
            source,
            primary,
            supporting_source_count=max(0, len(representative_items) - 1),
            uncertain_duplicate="possible_duplicate" in previous_risks,
            now=current,
        )
        cluster.score = score
        cluster.topic = topic
        cluster.score_reasons = reasons
        cluster.risk_flags = risks
        if score >= candidate_threshold:
            transition_news_cluster(
                db,
                cluster,
                "candidate",
                reason_code="freshness_window_recheck",
            )
            promoted += 1
    return promoted
