"""Prompt templates and their cache must be isolated by organization."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.organization import Organization
from app.models.prompt import Prompt
from app.services import prompt_service


def test_prompt_names_versions_and_cache_are_organization_scoped():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as db:
        first = Organization(name="First", slug="first")
        second = Organization(name="Second", slug="second")
        third = Organization(name="Third", slug="third")
        db.add_all([first, second, third])
        db.commit()
        db.add(
            Prompt(
                organization_id=None,
                name="global-default",
                content="shared-default",
                version=1,
                is_active=True,
            )
        )
        db.commit()

        prompt_service.create_prompt(
            db,
            organization_id=first.id,
            name="answer_generation",
            content="first-private-content",
        )
        prompt_service.create_prompt(
            db,
            organization_id=second.id,
            name="answer_generation",
            content="second-private-content",
        )

        first_prompt = prompt_service.get_prompt_by_name(
            db, "answer_generation", organization_id=first.id
        )
        second_prompt = prompt_service.get_prompt_by_name(
            db, "answer_generation", organization_id=second.id
        )

        assert first_prompt.content == "first-private-content"
        assert second_prompt.content == "second-private-content"

        prompt_service.update_prompt(
            db,
            organization_id=first.id,
            name="answer_generation",
            content="first-v2",
        )

        assert prompt_service.get_prompt_by_name(
            db, "answer_generation", organization_id=first.id
        ).content == "first-v2"
        assert prompt_service.get_prompt_by_name(
            db, "answer_generation", organization_id=second.id
        ).content == "second-private-content"
        visible_to_third = {
            prompt.name: prompt.content
            for prompt in prompt_service.get_all_active_prompts(db, organization_id=third.id)
        }
        assert visible_to_third["global-default"] == "shared-default"
