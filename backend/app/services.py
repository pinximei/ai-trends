import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, AdminSession, AdminSourceConfig, EvidenceSignal, PipelineRun, RemovalRequest, Trend


def envelope(data, message="ok", code=0, request_id=None):
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id or str(uuid.uuid4()),
    }


def seed_if_empty(db: Session):
    if db.scalar(select(Trend.id).limit(1)):
        return
    trend_templates = [
        (
            "workflow-automation-agent",
            78.2,
            0.84,
            "growth",
            {"adoption": 0.30, "persistence": 0.25, "cross_source": 0.15, "burst": 0.20, "novelty": 0.10},
            124,
        ),
        (
            "customer-support-agent",
            73.4,
            0.79,
            "emerging",
            {"adoption": 0.22, "persistence": 0.20, "cross_source": 0.18, "burst": 0.25, "novelty": 0.15},
            96,
        ),
        (
            "multimodal-content-agent",
            69.1,
            0.76,
            "emerging",
            {"adoption": 0.18, "persistence": 0.21, "cross_source": 0.19, "burst": 0.23, "novelty": 0.19},
            88,
        ),
    ]
    periods = [
        ("day", "2026-04-14", 0.97),
        ("week", "2026-04-06", 1.0),
        ("month", "2026-04-01", 1.03),
        ("quarter", "2026-04-01", 1.06),
        ("year", "2026-01-01", 1.1),
    ]
    trends = []
    for period_type, period_start, factor in periods:
        for trend_key, score, conf, stage, components, sample_size in trend_templates:
            trends.append(
                Trend(
                    trend_key=trend_key,
                    period_type=period_type,
                    period_start=period_start,
                    trend_score=round(score * factor, 1),
                    confidence=conf,
                    lifecycle_stage=stage,
                    score_components_json=json.dumps(components),
                    sample_size=sample_size,
                )
            )
    evidences = [
        EvidenceSignal(
            signal_id="sig_001",
            trend_key="workflow-automation-agent",
            source="github",
            evidence_url="https://github.com/example/workflow-agent",
            evidence_score=0.88,
            source_diversity=0.60,
            label_stability=0.80,
        ),
        EvidenceSignal(
            signal_id="sig_002",
            trend_key="customer-support-agent",
            source="huggingface",
            evidence_url="https://huggingface.co/spaces/example/support-agent",
            evidence_score=0.81,
            source_diversity=0.55,
            label_stability=0.77,
        ),
        EvidenceSignal(
            signal_id="sig_003",
            trend_key="multimodal-content-agent",
            source="github",
            evidence_url="https://github.com/example/multimodal-content-agent",
            evidence_score=0.79,
            source_diversity=0.52,
            label_stability=0.74,
        ),
        EvidenceSignal(
            signal_id="sig_004",
            trend_key="workflow-automation-agent",
            source="design-showcase",
            evidence_url="https://images.unsplash.com/photo-1518770660439-4636190af475",
            evidence_score=0.75,
            source_diversity=0.48,
            label_stability=0.72,
        ),
        EvidenceSignal(
            signal_id="sig_005",
            trend_key="multimodal-content-agent",
            source="video-demo",
            evidence_url="https://www.w3schools.com/html/mov_bbb.mp4",
            evidence_score=0.77,
            source_diversity=0.51,
            label_stability=0.76,
        ),
    ]
    db.add_all(trends)
    db.add_all(evidences)
    db.commit()


def clear_business_data(db: Session):
    db.query(EvidenceSignal).delete()
    db.query(Trend).delete()
    db.query(RemovalRequest).delete()
    db.query(PipelineRun).delete()
    db.query(AdminSourceConfig).delete()
    db.query(AuditLog).delete()
    db.query(AdminSession).delete()
    db.commit()


def seed_demo_bundle(db: Session):
    seed_if_empty(db)
    if not db.scalar(select(AdminSourceConfig.id).limit(1)):
        db.add_all(
            [
                AdminSourceConfig(
                    source="github",
                    enabled=True,
                    frequency="daily",
                    api_base="https://api.github.com",
                    api_key_masked="",
                    notes="public events + repos",
                    updated_at=datetime.utcnow(),
                ),
                AdminSourceConfig(
                    source="huggingface",
                    enabled=True,
                    frequency="daily",
                    api_base="https://huggingface.co/api",
                    api_key_masked="",
                    notes="spaces + models",
                    updated_at=datetime.utcnow(),
                ),
                AdminSourceConfig(
                    source="reddit",
                    enabled=True,
                    frequency="hourly",
                    api_base="https://www.reddit.com",
                    api_key_masked="",
                    notes="community trend crawling",
                    updated_at=datetime.utcnow(),
                ),
            ]
        )
        db.commit()


def get_or_create_run(db: Session, req):
    existing = db.scalar(
        select(PipelineRun).where(PipelineRun.idempotency_key == req.idempotency_key).order_by(PipelineRun.started_at.desc())
    )
    if existing:
        return existing
    run = PipelineRun(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        job_type=req.job_type,
        status="running",
        idempotency_key=req.idempotency_key,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_removal_ticket(db: Session, req):
    ticket_id = f"t_{uuid.uuid4().hex[:10]}"
    token = uuid.uuid4().hex[:16]
    item = RemovalRequest(
        ticket_id=ticket_id,
        token=token,
        request_type=req.request_type,
        requester_contact=req.requester_contact,
        target_signal_id=req.target_signal_id,
        reason=req.reason,
        status="submitted",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
