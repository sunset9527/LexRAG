"""法规更新接口必须经组织管理员授权，并且不能越权读取事件。"""

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
from app.models.user import User
from app.services.authorization_service import AuthorizationService


def make_client(role_code: str):
    from app.api import admin, law_updates

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(User(id=1, username="admin", hashed_password="hash"))
        db.commit()
    authorization = AuthorizationService(factory)
    organization = authorization.ensure_demo_organization()
    authorization.assign_role(user_id=1, organization_id=organization["id"], role_code=role_code)
    context = authorization.build_context(user_id=1, organization_id=organization["id"])
    app = FastAPI()
    app.include_router(law_updates.router)
    app.dependency_overrides[admin.get_authorization_context] = lambda: context
    app.dependency_overrides[law_updates.get_law_update_service] = lambda: (
        law_updates.LawUpdateService(factory)
    )
    return TestClient(app)


def test_law_update_subscription_and_manual_snapshot_confirmation_are_admin_only():
    client = make_client("admin")
    created = client.post(
        "/law-updates/subscriptions",
        json={"law_name": "民法典", "source_url": "https://example.test/civil"},
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]
    assert (
        client.post(
            f"/law-updates/subscriptions/{subscription_id}/observe", json={"content": "v1"}
        ).status_code
        == 204
    )
    event = client.post(
        f"/law-updates/subscriptions/{subscription_id}/observe", json={"content": "v2"}
    )
    assert event.status_code == 201
    assert (
        client.post(f"/law-updates/events/{event.json()['id']}/confirm").json()["status"]
        == "CONFIRMED"
    )


def test_law_update_api_rejects_non_admin():
    client = make_client("member")
    response = client.get("/law-updates/subscriptions")
    assert response.status_code == 403
