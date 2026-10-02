"""v3.0 管理 API：客户端不能声称自己是管理员。"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.usage_daily import UsageDaily  # noqa: F401
from app.models.user import User

try:
    from app.api import admin
    from app.services.authorization_service import AuthorizationService
except ImportError:
    admin = None
    AuthorizationService = None


def make_client(role_code: str):
    assert admin is not None, "v3.0 应提供 admin 路由"
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [User(id=1, username="admin", hashed_password="hash"), User(id=2, username="member", hashed_password="hash")]
        )
        db.commit()
    service = AuthorizationService(factory)
    organization = service.ensure_demo_organization()
    service.assign_role(user_id=1, organization_id=organization["id"], role_code=role_code)
    context = service.build_context(user_id=1, organization_id=organization["id"])
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin.get_authorization_context] = lambda: context
    app.dependency_overrides[admin.get_authorization_service] = lambda: service
    return TestClient(app), organization


def test_admin_api_returns_current_organization_not_client_supplied_user():
    client, organization = make_client("admin")

    response = client.get("/admin/organization")

    assert response.status_code == 200
    assert response.json() == {
        "id": organization["id"],
        "name": "本机演示组织",
        "role": "admin",
    }


def test_member_management_requires_database_backed_admin_permission():
    client, _ = make_client("member")

    response = client.get("/admin/members")

    assert response.status_code == 403


def test_admin_can_list_and_change_member_role_only_inside_current_organization():
    client, _ = make_client("admin")

    before = client.get("/admin/members")
    changed = client.put("/admin/members/2/role", json={"role_code": "lawyer"})
    after = client.get("/admin/members")

    assert before.status_code == 200
    assert changed.status_code == 204
    assert [(item["user_id"], item["role"]) for item in after.json()["items"]] == [
        (1, "admin"),
        (2, "lawyer"),
    ]


def test_audit_and_usage_endpoints_are_admin_only_and_never_return_raw_question():
    client, _ = make_client("admin")

    usage = client.get("/admin/usage")
    audit = client.get("/admin/audit-logs")

    assert usage.status_code == 200
    assert usage.json() == {"items": []}
    assert audit.status_code == 200
    assert audit.json() == {"items": []}
