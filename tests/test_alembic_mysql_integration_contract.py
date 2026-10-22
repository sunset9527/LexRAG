"""Unit contracts for assertions used by the opt-in MySQL migration test."""

from test_alembic_mysql_integration import (
    _actual_check_constraints,
    _expected_check_constraints,
    _registered_metadata,
)


class _ReflectedMySQLInspector:
    """Minimal reflection double with MySQL-style quoting and outer parentheses."""

    def get_check_constraints(self, table_name: str) -> list[dict[str, str]]:
        checks = {
            "document_pages": [
                {
                    "name": "ck_document_pages_page_number",
                    "sqltext": "(`page_number` >= 1)",
                }
            ],
            "document_relations": [
                {
                    "name": "ck_document_relations_evidence",
                    "sqltext": "((`law_article` IS NOT NULL OR `similarity` IS NOT NULL OR "
                    "`evidence_text` IS NOT NULL))",
                }
            ],
        }
        return checks.get(table_name, [])


def test_check_constraints_match_orm_metadata_after_mysql_reflection() -> None:
    metadata = _registered_metadata()
    inspector = _ReflectedMySQLInspector()

    assert _actual_check_constraints(
        inspector, "document_pages"
    ) == _expected_check_constraints(metadata.tables["document_pages"])
    assert _actual_check_constraints(
        inspector, "document_relations"
    ) == _expected_check_constraints(metadata.tables["document_relations"])
