import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.auth import create_staff_user
from app.auth.dependencies import require_roles
from app.config import settings
from app.db.models import ArtistProfile, CatalogSyncRun, Job, Label, LabelMember, Song, User
from app.db.session import get_db
from app.schemas.admin import LabelCreate, LabelMemberCreate, StaffUserCreate, UserRoleUpdate
from app.schemas.auth import UserSummary
from app.services.catalog_sync import EMBEDDING_VERSION

router = APIRouter(prefix="/admin", tags=["platform administration"])
PlatformAdmin = Depends(require_roles("platform_admin"))


@router.get("/config/status")
def configuration_status(_admin=PlatformAdmin):
    return {
        "jamendo_configured": bool(settings.jamendo_client_id),
        "google_oauth_configured": bool(settings.google_client_id and settings.google_client_secret),
        "embedding_model": settings.embedding_model,
        "max_sync_tracks": settings.jamendo_max_tracks,
        "page_size": settings.jamendo_page_size,
    }


@router.get("/users", response_model=list[UserSummary])
def list_users(_admin=PlatformAdmin, db: Session = Depends(get_db),
               offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return db.scalars(select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)).all()


@router.post("/users", response_model=UserSummary, status_code=201)
def create_staff(payload: StaffUserCreate, _admin=PlatformAdmin, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(func.lower(User.email) == str(payload.email).lower())):
        raise HTTPException(status_code=409, detail="An account already uses that email")
    if payload.label_id and db.get(Label, payload.label_id) is None:
        raise HTTPException(status_code=404, detail="Label not found")
    user = create_staff_user(db, name=payload.name.strip(), email=str(payload.email),
                             password=payload.password, role=payload.role)
    if payload.role == "artist":
        db.add(ArtistProfile(user_id=user.id, label_id=payload.label_id,
                             stage_name=payload.name.strip()))
    if payload.role == "label_admin" and payload.label_id:
        db.add(LabelMember(label_id=payload.label_id, user_id=user.id, membership_role="admin"))
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserSummary)
def change_role(user_id: uuid.UUID, payload: UserRoleUpdate, admin=PlatformAdmin,
                db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.execute(text("SELECT vibecast_admin_set_user_role(:target_id, :new_role)"),
               {"target_id": user_id, "new_role": payload.role})
    if payload.role == "artist" and db.scalar(select(ArtistProfile.id).where(ArtistProfile.user_id == user_id)) is None:
        db.add(ArtistProfile(user_id=user_id, stage_name=user.name))
    db.commit()
    db.refresh(user)
    return user


@router.post("/catalog/sync", status_code=202)
def request_catalog_sync(admin=PlatformAdmin, db: Session = Depends(get_db),
                         max_tracks: int = Query(1000, ge=1, le=10000),
                         page_size: int = Query(100, ge=1, le=200)):
    if not settings.jamendo_client_id:
        raise HTTPException(status_code=409, detail="Configure VIBECAST_JAMENDO_CLIENT_ID before starting a sync")
    job_id = uuid.uuid4()
    db.execute(pg_insert(Job).values(
        id=job_id, kind="sync_catalog", idempotency_key=f"manual-sync:{job_id}",
        payload={"requested_by": str(admin.id), "max_tracks": max_tracks, "page_size": page_size},
        status="queued",
    ))
    db.commit()
    return {"job_id": job_id, "status": "queued", "max_tracks": max_tracks, "page_size": page_size}


@router.get("/catalog/sync/status")
def catalog_sync_status(_admin=PlatformAdmin, db: Session = Depends(get_db),
                        limit: int = Query(20, ge=1, le=100)):
    runs = db.scalars(select(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).limit(limit)).all()
    jobs = db.execute(select(Job.id, Job.kind, Job.status, Job.attempts, Job.last_error,
                             Job.created_at, Job.updated_at)
                      .where(Job.kind == "sync_catalog").order_by(Job.created_at.desc()).limit(limit)).all()
    return {
        "runs": [{"id": run.id, "status": run.status, "configured_max_tracks": run.configured_max_tracks,
                  "tracks_seen": run.tracks_seen, "tracks_upserted": run.tracks_upserted,
                  "pages_fetched": run.pages_fetched, "error_summary": run.error_summary,
                  "started_at": run.started_at, "finished_at": run.finished_at} for run in runs],
        "jobs": [{"id": row.id, "kind": row.kind, "status": row.status,
                  "attempts": row.attempts, "last_error": row.last_error,
                  "created_at": row.created_at, "updated_at": row.updated_at} for row in jobs],
    }


@router.get("/jobs")
def list_jobs(_admin=PlatformAdmin, db: Session = Depends(get_db),
              status_filter: str | None = Query(None, alias="status", max_length=20),
              limit: int = Query(100, ge=1, le=500)):
    query = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status_filter:
        if status_filter not in {"queued", "running", "retry", "complete", "failed"}:
            raise HTTPException(status_code=422, detail="Invalid job status")
        query = query.where(Job.status == status_filter)
    rows = db.scalars(query).all()
    return [{"id": row.id, "kind": row.kind, "status": row.status, "attempts": row.attempts,
             "payload": row.payload, "last_error": row.last_error,
             "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: uuid.UUID, _admin=PlatformAdmin, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {"failed", "retry"}:
        raise HTTPException(status_code=409, detail="Only failed or retryable jobs can be retried")
    job.status = "queued"
    job.attempts = 0
    job.available_at = datetime.now(UTC)
    job.locked_at = None
    job.last_error = None
    db.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/catalog/embeddings/rebuild", status_code=202)
def rebuild_embeddings(_admin=PlatformAdmin, db: Session = Depends(get_db),
                       limit: int = Query(10000, ge=1, le=50000)):
    song_ids = list(db.scalars(select(Song.id).where(Song.source == "jamendo").order_by(Song.id).limit(limit)))
    rebuild_id = uuid.uuid4()
    if song_ids:
        db.execute(pg_insert(Job).values([
            {"kind": "embed_song", "idempotency_key": f"rebuild:{rebuild_id}:{song_id}:{EMBEDDING_VERSION}",
             "payload": {"song_id": str(song_id), "version": EMBEDDING_VERSION}}
            for song_id in song_ids
        ]))
    db.commit()
    return {"queued": len(song_ids), "rebuild_id": rebuild_id}


@router.post("/recommendations/rebuild", status_code=202)
def rebuild_recommendations(_admin=PlatformAdmin, db: Session = Depends(get_db)):
    job_id = uuid.uuid4()
    db.add(Job(kind="train_collaborative", idempotency_key=f"admin-itemknn:{job_id}", payload={}))
    db.commit()
    return {"job_id": job_id, "status": "queued"}


@router.post("/labels", status_code=201)
def create_label(payload: LabelCreate, _admin=PlatformAdmin, db: Session = Depends(get_db)):
    if db.scalar(select(Label.id).where(func.lower(Label.name) == payload.name.lower().strip())):
        raise HTTPException(status_code=409, detail="A label with that name already exists")
    label = Label(name=payload.name.strip())
    db.add(label)
    db.commit()
    db.refresh(label)
    return {"id": label.id, "name": label.name}


@router.post("/labels/{label_id}/admins", status_code=201)
def add_label_admin(label_id: uuid.UUID, payload: LabelMemberCreate, _admin=PlatformAdmin,
                    db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    user = db.get(User, payload.user_id)
    if label is None or user is None:
        raise HTTPException(status_code=404, detail="Label or user not found")
    if user.role != "label_admin":
        raise HTTPException(status_code=422, detail="The selected user must have the label_admin role")
    exists = db.scalar(select(LabelMember.id).where(LabelMember.label_id == label_id,
                                                   LabelMember.user_id == user.id))
    if exists:
        raise HTTPException(status_code=409, detail="The user is already assigned to this label")
    db.add(LabelMember(label_id=label_id, user_id=user.id, membership_role="admin"))
    db.commit()
    return {"label_id": label_id, "user_id": user.id, "membership_role": "admin"}
