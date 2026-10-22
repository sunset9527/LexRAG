"""Explicit, idempotent organization-administrator bootstrap."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.organization import Organization
from app.models.user import User
from app.services.auth_service import hash_password
from app.services.authorization_service import AuthorizationService

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def bootstrap_administrator(
    session_factory: sessionmaker,
    *,
    username: str,
    password: str,
    email: str | None,
    organization_name: str,
    organization_slug: str,
) -> dict[str, object]:
    """Create or reuse one user/organization and assign the admin role."""

    if len(username) < 3 or len(password) < 12:
        raise ValueError("管理员用户名或密码长度不足")
    if not _SLUG.fullmatch(organization_slug):
        raise ValueError("组织 slug 格式无效")

    authorization = AuthorizationService(session_factory)
    with session_factory() as db:
        authorization._ensure_seed_data(db)
        organization = db.scalar(
            select(Organization).where(Organization.slug == organization_slug)
        )
        if organization is None:
            organization = Organization(name=organization_name, slug=organization_slug)
            db.add(organization)
            db.flush()

        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                is_active=True,
            )
            db.add(user)
            db.flush()
        db.commit()
        user_id = user.id
        organization_id = organization.id

    authorization.assign_role(
        user_id=user_id,
        organization_id=organization_id,
        role_code="admin",
    )
    return {
        "user_id": user_id,
        "organization_id": organization_id,
        "username": username,
        "organization_slug": organization_slug,
    }
