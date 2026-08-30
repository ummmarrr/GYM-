"""Reception check-in, member passes, photos, and operational notices."""

import base64
import hashlib
import hmac
from datetime import date, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_front_desk
from app.core.config import get_settings
from app.db import (
    Attendance,
    AuditEvent,
    ClassBooking,
    ClassSchedule,
    FitnessProfile,
    GymNotice,
    MemberPass,
    MemberPhoto,
    Membership,
    Role,
    User,
    get_db,
    utc_now,
)
from app.schemas import (
    AttendanceCreateRequest,
    AttendanceResponse,
    CheckInResponse,
    EntitlementsResponse,
    FrontDeskBriefing,
    FrontDeskMember,
    MemberPassResponse,
    NoticeResponse,
    NoticeWriteRequest,
    PassLookupRequest,
    UpcomingClassBrief,
)
from app.services.entitlements import entitlements_for

router = APIRouter(tags=["front desk"])

PASS_PREFIX = "mgp1"
CHECK_IN_COOLDOWN = timedelta(hours=4)
MAX_PHOTO_BYTES = 500 * 1024


def _token_for(member_id: str, pass_id: str) -> str:
    """Build a recoverable, revocable pass without storing bearer credentials.

    The random pass UUID is the nonce. Its signed representation is deterministic, so GET
    /me/pass can reproduce the same token later while the database retains only its SHA-256
    digest. Rotation changes the UUID and revokes the old row; HMAC prevents forgery.
    """
    body = base64.urlsafe_b64encode(f"{member_id}.{pass_id}".encode()).rstrip(b"=").decode()
    signature = hmac.new(
        get_settings().jwt_secret.encode(), f"{PASS_PREFIX}.{body}".encode(), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{PASS_PREFIX}.{body}.{encoded_signature}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _parse_token(token: str) -> tuple[str, str] | None:
    try:
        prefix, body, encoded_signature = token.split(".")
        if prefix != PASS_PREFIX:
            return None
        expected = hmac.new(
            get_settings().jwt_secret.encode(), f"{prefix}.{body}".encode(), hashlib.sha256
        ).digest()
        signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(signature, expected):
            return None
        decoded = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        member_id, pass_id = decoded.split(".", 1)
        return member_id, pass_id
    except (UnicodeDecodeError, ValueError):
        return None


def _active_pass(db: Session, member_id: str) -> MemberPass | None:
    return db.scalars(
        select(MemberPass).where(
            MemberPass.member_id == member_id,
            MemberPass.active_slot == member_id,
            MemberPass.revoked_at.is_(None),
        )
    ).first()


def _issue_pass(db: Session, member: User) -> tuple[MemberPass, str]:
    pass_id = str(uuid4())
    token = _token_for(member.id, pass_id)
    member_pass = MemberPass(
        id=pass_id,
        member_id=member.id,
        token_hash=_token_hash(token),
        active_slot=member.id,
    )
    db.add(member_pass)
    db.flush()
    return member_pass, token


def _require_member(db: Session, member_id: str) -> User:
    member = db.get(User, member_id)
    if member is None or member.role is not Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found.")
    return member


def _entitlements_response(db: Session, member: User) -> EntitlementsResponse:
    ent = entitlements_for(db, member)
    return EntitlementsResponse(
        has_active_membership=ent.has_active_membership,
        plan_name=ent.plan_name,
        tier=ent.tier,
        expires_on=ent.expires_on,
        days_remaining=ent.days_remaining,
        allowed_disciplines=list(ent.allowed_disciplines),
        monthly_class_quota=ent.monthly_class_quota,
        classes_booked_this_month=ent.classes_booked_this_month,
        personalised_programme=ent.personalised_programme,
        priority_support=ent.priority_support,
    )


def _active_notices(db: Session) -> list[GymNotice]:
    now = utc_now()
    return list(
        db.scalars(
            select(GymNotice)
            .where(
                GymNotice.active_from <= now,
                or_(GymNotice.active_until.is_(None), GymNotice.active_until >= now),
            )
            .order_by(GymNotice.active_from.desc())
        ).all()
    )


def _briefing(db: Session, member: User) -> FrontDeskBriefing:
    now = utc_now()
    classes = db.execute(
        select(ClassSchedule)
        .join(ClassBooking, ClassBooking.class_id == ClassSchedule.id)
        .where(
            ClassBooking.member_id == member.id,
            ClassSchedule.starts_at >= now,
            ClassSchedule.starts_at <= now + timedelta(days=7),
        )
        .order_by(ClassSchedule.starts_at)
    ).scalars()
    profile = db.get(FitnessProfile, member.id)
    trainer = (
        db.get(User, profile.assigned_trainer_id)
        if profile is not None and profile.assigned_trainer_id
        else None
    )
    last_check_in = db.scalars(
        select(Attendance)
        .where(Attendance.member_id == member.id)
        .order_by(Attendance.checked_in_at.desc())
        .limit(1)
    ).first()
    latest_membership = db.scalars(
        select(Membership)
        .where(Membership.user_id == member.id)
        .order_by(Membership.expires_on.desc())
        .limit(1)
    ).first()

    warnings = []
    if not member.active:
        warnings.append("Member account is inactive.")
    if latest_membership is None:
        warnings.append("No membership is on record.")
    elif latest_membership.status != "active":
        warnings.append("Membership is not active.")
    elif latest_membership.expires_on < date.today():
        warnings.append(f"Membership expired on {latest_membership.expires_on.isoformat()}.")

    return FrontDeskBriefing(
        member=FrontDeskMember(
            id=member.id,
            email=member.email,
            full_name=member.full_name,
            phone=member.phone,
            active=member.active,
            photo_available=db.get(MemberPhoto, member.id) is not None,
        ),
        entitlements=_entitlements_response(db, member),
        upcoming_classes=[
            UpcomingClassBrief(
                id=item.id,
                name=item.name,
                discipline=item.discipline,
                instructor=item.instructor,
                starts_at=item.starts_at,
            )
            for item in classes
        ],
        trainer_name=trainer.full_name if trainer else None,
        active_notices=[NoticeResponse.model_validate(item) for item in _active_notices(db)],
        last_check_in=(
            AttendanceResponse.model_validate(last_check_in) if last_check_in else None
        ),
        warnings=warnings,
    )


@router.get("/me/pass", response_model=MemberPassResponse)
def my_pass(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.role is not Role.MEMBER:
        raise HTTPException(status_code=403, detail="Member passes are only available to members.")
    member_pass = _active_pass(db, current_user.id)
    if member_pass is None:
        member_pass, token = _issue_pass(db, current_user)
        db.add(
            AuditEvent(
                actor_id=current_user.id,
                action="member_pass.issued",
                resource_type="member_pass",
                resource_id=member_pass.id,
            )
        )
        db.commit()
    else:
        token = _token_for(current_user.id, member_pass.id)
    return MemberPassResponse(
        token=token,
        # The kiosk decoder submits this value directly to /front-desk/lookup.
        # Keep the QR payload opaque rather than teaching each client to parse a custom URI.
        qr_payload=token,
        created_at=member_pass.created_at,
    )


@router.post("/front-desk/lookup", response_model=FrontDeskBriefing)
def lookup_pass(
    payload: PassLookupRequest,
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
):
    parsed = _parse_token(payload.token)
    if parsed is None:
        raise HTTPException(status_code=404, detail="Pass not found or revoked.")
    member_id, pass_id = parsed
    member_pass = db.get(MemberPass, pass_id)
    if (
        member_pass is None
        or member_pass.member_id != member_id
        or member_pass.revoked_at is not None
        or member_pass.active_slot != member_id
        or not hmac.compare_digest(member_pass.token_hash, _token_hash(payload.token))
    ):
        raise HTTPException(status_code=404, detail="Pass not found or revoked.")
    return _briefing(db, _require_member(db, member_id))


@router.post("/front-desk/check-in", response_model=CheckInResponse)
def check_in(
    payload: AttendanceCreateRequest,
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
):
    member = _require_member(db, payload.user_id)
    if not member.active:
        raise HTTPException(status_code=409, detail="Inactive members cannot check in.")

    cutoff = utc_now() - CHECK_IN_COOLDOWN
    attendance = db.scalars(
        select(Attendance)
        .where(
            Attendance.member_id == member.id,
            Attendance.checked_in_at >= cutoff,
        )
        .order_by(Attendance.checked_in_at.desc())
        .limit(1)
    ).first()
    already_checked_in = attendance is not None
    if attendance is None:
        attendance = Attendance(
            member_id=member.id,
            actor_id=current_user.id,
            method=payload.method,
            note=payload.note,
        )
        db.add(attendance)
        db.flush()
        db.add(
            AuditEvent(
                actor_id=current_user.id,
                action="attendance.checked_in",
                resource_type="attendance",
                resource_id=attendance.id,
                detail=f"{member.email} via {payload.method}",
            )
        )
        db.commit()

    return CheckInResponse(
        attendance=AttendanceResponse.model_validate(attendance),
        already_checked_in=already_checked_in,
        briefing=_briefing(db, member),
    )


@router.get("/front-desk/search", response_model=list[FrontDeskMember])
def search_members(
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, max_length=120)],
):
    term = f"%{q.strip().lower()}%"
    members = db.scalars(
        select(User)
        .where(
            User.role == Role.MEMBER,
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
            ),
        )
        .order_by(User.full_name)
        .limit(8)
    ).all()
    photo_ids = set(
        db.scalars(
            select(MemberPhoto.member_id).where(
                MemberPhoto.member_id.in_([member.id for member in members])
            )
        ).all()
    )
    return [
        FrontDeskMember(
            id=member.id,
            email=member.email,
            full_name=member.full_name,
            phone=member.phone,
            active=member.active,
            photo_available=member.id in photo_ids,
        )
        for member in members
    ]


@router.get("/front-desk/briefing/{user_id}", response_model=FrontDeskBriefing)
def member_briefing(
    user_id: str,
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
):
    return _briefing(db, _require_member(db, user_id))


@router.post("/staff/members/{member_id}/pass/rotate", response_model=MemberPassResponse)
def rotate_pass(
    member_id: str,
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
):
    member = _require_member(db, member_id)
    previous = _active_pass(db, member.id)
    if previous is not None:
        previous.active_slot = None
        previous.revoked_at = utc_now()
        previous.revoked_by_id = current_user.id
        db.flush()
    member_pass, token = _issue_pass(db, member)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="member_pass.rotated",
            resource_type="member_pass",
            resource_id=member_pass.id,
            detail=member.email,
        )
    )
    db.commit()
    return MemberPassResponse(
        token=token,
        qr_payload=token,
        created_at=member_pass.created_at,
    )


@router.put("/staff/members/{member_id}/photo", status_code=status.HTTP_200_OK)
async def put_member_photo(
    member_id: str,
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
    photo: Annotated[UploadFile, File()],
):
    member = _require_member(db, member_id)
    image = await photo.read(MAX_PHOTO_BYTES + 1)
    if len(image) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo must be 500KB or smaller.")

    detected_type = None
    if image.startswith(b"\xff\xd8\xff"):
        detected_type = "image/jpeg"
    elif image.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_type = "image/png"
    if detected_type is None or photo.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=415, detail="Photo must be a JPEG or PNG image.")
    if photo.content_type != detected_type:
        raise HTTPException(status_code=400, detail="Photo content does not match its file type.")

    record = db.get(MemberPhoto, member.id)
    if record is None:
        record = MemberPhoto(
            member_id=member.id,
            image_bytes=image,
            content_type=detected_type,
            size_bytes=len(image),
            uploaded_by_id=current_user.id,
        )
        db.add(record)
    else:
        record.image_bytes = image
        record.content_type = detected_type
        record.size_bytes = len(image)
        record.uploaded_by_id = current_user.id
        record.uploaded_at = utc_now()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="member_photo.updated",
            resource_type="member_photo",
            resource_id=member.id,
            detail=f"{detected_type}, {len(image)} bytes",
        )
    )
    db.commit()
    return {"member_id": member.id, "content_type": detected_type, "size_bytes": len(image)}


@router.get("/staff/members/{member_id}/photo")
def get_member_photo(
    member_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.role not in (Role.ADMIN, Role.RECEPTION) and current_user.id != member_id:
        raise HTTPException(status_code=403, detail="You cannot view this member photo.")
    record = db.get(MemberPhoto, member_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Member photo not found.")
    return Response(
        content=record.image_bytes,
        media_type=record.content_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/front-desk/notices", response_model=list[NoticeResponse])
def list_notices(
    current_user: Annotated[User, Depends(require_front_desk)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(select(GymNotice).order_by(GymNotice.active_from.desc())).all()


def _validate_notice_window(payload: NoticeWriteRequest) -> None:
    if payload.active_until is not None and payload.active_until < payload.active_from:
        raise HTTPException(status_code=422, detail="active_until must be after active_from.")


@router.post("/front-desk/notices", response_model=NoticeResponse, status_code=201)
def create_notice(
    payload: NoticeWriteRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    _validate_notice_window(payload)
    notice = GymNotice(**payload.model_dump(), created_by_id=current_user.id)
    db.add(notice)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="gym_notice.created",
            resource_type="gym_notice",
            resource_id=notice.id,
            detail=notice.title,
        )
    )
    db.commit()
    return notice


@router.put("/front-desk/notices/{notice_id}", response_model=NoticeResponse)
def update_notice(
    notice_id: str,
    payload: NoticeWriteRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    _validate_notice_window(payload)
    notice = db.get(GymNotice, notice_id)
    if notice is None:
        raise HTTPException(status_code=404, detail="Notice not found.")
    for field, value in payload.model_dump().items():
        setattr(notice, field, value)
    notice.updated_at = utc_now()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="gym_notice.updated",
            resource_type="gym_notice",
            resource_id=notice.id,
            detail=notice.title,
        )
    )
    db.commit()
    return notice


@router.delete("/front-desk/notices/{notice_id}")
def delete_notice(
    notice_id: str,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    notice = db.get(GymNotice, notice_id)
    if notice is None:
        raise HTTPException(status_code=404, detail="Notice not found.")
    title = notice.title
    db.delete(notice)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="gym_notice.deleted",
            resource_type="gym_notice",
            resource_id=notice_id,
            detail=title,
        )
    )
    db.commit()
    return {"message": "Notice deleted."}
