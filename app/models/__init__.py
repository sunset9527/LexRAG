"""Runtime model registry.

Importing one ORM model must register every table referenced by the runtime
metadata.  Alembic already imports this same catalogue before it evaluates
the migration metadata; application services need the identical guarantee.
"""

import app.models.agent_config  # noqa: F401
import app.models.audit_log  # noqa: F401
import app.models.case_source  # noqa: F401
import app.models.chat_history  # noqa: F401
import app.models.document_job  # noqa: F401
import app.models.document_page  # noqa: F401
import app.models.document_relation  # noqa: F401
import app.models.document_structure  # noqa: F401
import app.models.favorite  # noqa: F401
import app.models.knowledge_base  # noqa: F401
import app.models.law_update  # noqa: F401
import app.models.legal_source_import  # noqa: F401
import app.models.organization  # noqa: F401
import app.models.prompt  # noqa: F401
import app.models.rbac  # noqa: F401
import app.models.scenario_job  # noqa: F401
import app.models.session  # noqa: F401
import app.models.statute_version_chain  # noqa: F401
import app.models.usage_daily  # noqa: F401
import app.models.user  # noqa: F401
import app.models.user_profile  # noqa: F401
