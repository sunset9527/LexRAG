# Stage 2 Security and Privacy Verification

Date: 2026-10-22  
Implementation commits: `fdf06e0`, `05b38b5`

## Verified scope

- Authentication: HttpOnly browser cookie, Bearer compatibility, production registration policy and explicit administrator bootstrap.
- Authorization: protected graph/case routes, organization-scoped prompts and recommendations, owned knowledge-base/document mutations, removal of the legacy process-local verification endpoint.
- Runtime LLM: provider allowlist, custom-endpoint permission, public DNS requirement, dangerous-address/port rejection, no redirects, bounded model/timeout/output/retry/connections.
- Privacy: no raw question/answer/key in regular logs, stable public 500 envelope, redacted append-only audit metadata, Langfuse disabled by default.
- Uploads: incremental byte ceilings, filename/MIME/magic checks, DOCX archive bounds, organization/knowledge-base paths, parsed page/character ceilings and Celery soft/hard limits.
- Frontend: Cookie session transport and memory-only BYOK secret.

## Commands and observed results

```powershell
python -m pytest tests/test_security_settings.py tests/test_request_security.py tests/test_auth_security.py tests/test_runtime_llm_policy.py tests/test_route_security_contract.py tests/test_upload_security.py tests/test_document_task_security.py tests/test_rate_limit.py tests/test_privacy_contract.py tests/test_prompt_organization.py tests/test_admin_bootstrap.py tests/test_session_service.py tests/test_audit_usage_service.py tests/test_rbac_service.py tests/test_agent_config_service.py -q --basetemp=reports/quality/pytest-stage2-focused-final
# 69 passed, 3 dependency warnings

python -m pytest tests/test_document_ingestion_service.py tests/test_document_library_service.py tests/test_document_parser.py tests/test_document_relation_service.py tests/test_document_result_service.py tests/test_document_structure_service.py tests/test_rich_document_parser.py -q --basetemp=reports/quality/pytest-stage2-documents-green
# 22 passed, 1 dependency warning

.\.venv\Scripts\ruff.exe check api.py config.py app/security app/api/auth.py app/api/prompts.py app/api/scenarios.py app/api/sessions.py app/models/prompt.py app/services app/tasks/document_tasks.py scripts/bootstrap_admin.py src/agent src/ingestion/rich_document_parser.py src/retrieval tests/test_admin_bootstrap.py tests/test_auth_security.py tests/test_document_task_security.py tests/test_privacy_contract.py tests/test_prompt_organization.py tests/test_rate_limit.py tests/test_request_security.py tests/test_route_security_contract.py tests/test_runtime_llm_policy.py tests/test_security_settings.py tests/test_session_service.py tests/test_upload_security.py
.\.venv\Scripts\ruff.exe check app src tests/test_privacy_contract.py
# All checks passed

cd frontend
node --test tests\*.test.mjs
# 4 passed
npx vue-tsc -b --pretty false
# exit 0
npx vite build
# built successfully; existing Rollup annotation and large-chunk warnings remain
```

No legal evaluation data, labels or metrics were changed.

## Verification boundary

The complete backend ASGI suite was not run in this Codex sandbox. FastAPI/httpx integration tests block while Windows Python 3.13 initializes the asyncio self-pipe (`_fallback_socketpair().accept()`). This is an execution-environment limitation, not a passing result.

Run the following in a normal project PowerShell terminal before marking Stage 2 closed:

```powershell
python -m pytest -q --basetemp=reports\quality\pytest-stage2-full
```

Stage 8 still owns real multi-organization adversarial testing, SSRF/DNS-rebinding exercises against controlled infrastructure, sensitive-artifact scanning and Docker end-to-end acceptance.
