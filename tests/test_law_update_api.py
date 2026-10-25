"""法规更新接口必须经组织管理员授权，并且不能越权读取事件。"""

import sys
from datetime import date
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
from app.services.legal_source_intake_service import LegalSourceIntakeService
from app.services.statute_version_chain_service import StatuteVersionChainService
from src.ingestion.statute_source_intake import (
    SOURCE_STATUS_CURRENT,
    Stage4SourceCandidate,
)


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
    app.dependency_overrides[law_updates.get_legal_source_intake_service] = lambda: (
        LegalSourceIntakeService(factory)
    )
    app.dependency_overrides[law_updates.get_statute_version_chain_service] = lambda: (
        StatuteVersionChainService(factory)
    )
    client = TestClient(app)
    client.lexrag_session_factory = factory
    return client


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


def test_law_update_api_lists_local_source_provenance_for_admin_only():
    client = make_client("admin")

    response = client.get("/law-updates/local-sources")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_admin_can_verify_local_source_with_an_official_url():
    client = make_client("admin")
    service = LegalSourceIntakeService(client.lexrag_session_factory)
    candidate = service.record_candidate(
        Stage4SourceCandidate(
            source_path=Path("E:/source/company-law.docx"),
            law_slug="company-law",
            law_name="中华人民共和国公司法",
            version_id="company-law@2023-12-29",
            promulgated_on=date(2023, 12, 29),
            effective_from=date(2024, 7, 1),
            source_status=SOURCE_STATUS_CURRENT,
            raw_sha256="a" * 64,
            content_sha256="b" * 64,
            content="中华人民共和国公司法\n第一条",
        )
    )

    response = client.post(
        f"/law-updates/local-sources/{candidate['id']}/verify",
        json={"authority_url": "https://www.samr.gov.cn/example"},
    )

    assert response.status_code == 200
    assert response.json()["authority_status"] == "VERIFIED"


def test_admin_can_create_and_list_an_indexable_version_chain():
    client = make_client("admin")
    sources = LegalSourceIntakeService(client.lexrag_session_factory)
    candidate = sources.record_candidate(
        Stage4SourceCandidate(
            source_path=Path("E:/source/company-law.docx"),
            law_slug="company-law",
            law_name="中华人民共和国公司法",
            version_id="company-law@2023-12-29",
            promulgated_on=date(2023, 12, 29),
            effective_from=date(2024, 7, 1),
            source_status=SOURCE_STATUS_CURRENT,
            raw_sha256="a" * 64,
            content_sha256="b" * 64,
            content="中华人民共和国公司法\n第一条",
        )
    )
    sources.verify_candidate(
        candidate["id"], authority_url="https://www.samr.gov.cn/example", reviewer_user_id=1
    )

    created = client.post(
        "/law-updates/version-chains",
        json={
            "law_slug": "company-law",
            "target_version_id": "company-law@2024-07-01",
            "effective_from": "2024-07-01",
            "consolidated_source_import_id": candidate["id"],
            "members": [{"source_import_id": candidate["id"], "role": "CONSOLIDATED_TEXT"}],
        },
    )

    assert created.status_code == 201
    assert created.json()["is_indexable"] is True
    listed = client.get("/law-updates/version-chains")
    assert listed.status_code == 200
    assert [item["target_version_id"] for item in listed.json()["items"]] == [
        "company-law@2024-07-01"
    ]
