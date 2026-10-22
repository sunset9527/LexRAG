"""Production administrator bootstrap is explicit and idempotent."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.organization import Organization
from app.models.rbac import Role, UserRole
from app.models.user import User


def test_bootstrap_creates_one_admin_membership_and_is_idempotent():
    from app.services.bootstrap_service import bootstrap_administrator

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    first = bootstrap_administrator(
        factory,
        username="stage2-admin",
        password="test-only-password",
        email="admin@example.test",
        organization_name="Stage 2 Org",
        organization_slug="stage-2-org",
    )
    second = bootstrap_administrator(
        factory,
        username="stage2-admin",
        password="test-only-password",
        email="admin@example.test",
        organization_name="Stage 2 Org",
        organization_slug="stage-2-org",
    )

    assert second == first
    with factory() as db:
        assert len(db.scalars(select(User)).all()) == 1
        assert len(db.scalars(select(Organization)).all()) == 1
        membership = db.scalar(select(UserRole))
        role = db.get(Role, membership.role_id)
        assert role.code == "admin"
