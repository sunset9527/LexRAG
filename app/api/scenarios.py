"""v2.2 法律场景 API。"""

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from app.api.admin import get_authorization_context
from app.api.auth import get_current_user
from app.models.user import User
from app.security.runtime_llm import RuntimeLLMPolicy
from app.security.uploads import (
    UploadValidationError,
    build_isolated_upload_path,
    save_upload_file,
)
from app.services.authorization_service import AuthorizationContext
from app.services.langfuse_helper import create_llm
from app.services.scenario_runtime import create_runtime_scenario_service
from app.services.scenario_service import ScenarioService
from app.tasks.scenario_tasks import process_scenario_task
from config import settings
from src.ingestion.document_parser import parse_document
from src.scenarios.legal_scenarios import build_scenario_pdf, build_structured_report

router = APIRouter(prefix="/scenarios", tags=["法律场景"])
runtime_llm_policy = RuntimeLLMPolicy(settings)


class ScenarioCreateRequest(BaseModel):
    scenario_type: str = Field(
        ..., pattern=r"^(contract_review|compliance_check|document_draft|rights_path)$"
    )
    input_data: dict[str, Any] = Field(default_factory=dict)


def _validated_runtime(
    context: AuthorizationContext,
    base_url: str | None,
    model: str | None,
) -> tuple[str | None, str | None]:
    if not base_url and not model:
        return None, None
    try:
        runtime = runtime_llm_policy.validate(
            base_url=base_url or settings.deepseek_base_url,
            model=model or settings.deepseek_model,
            allow_custom=context.can("runtime_models:custom"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return runtime.base_url, runtime.model


def _service(
    api_key: str | None = None, base_url: str | None = None, model: str | None = None
) -> ScenarioService:
    def advice_generator(clause: str, citations: list[str]) -> str:
        llm = create_llm(api_key=api_key, base_url=base_url, model=model)
        return llm.invoke(
            f"仅依据条款和已验证法条给出一条修改建议，不得补充事实。条款：{clause}\n法条：{'、'.join(citations)}"
        ).content.strip()

    def case_provider(query: str) -> list[dict[str, Any]]:
        try:
            import api

            retriever = api.components.get("annual_case_retriever")
            return retriever.search(query, top_k=3) if retriever else []
        except Exception:
            return []

    try:
        return create_runtime_scenario_service(
            advice_generator=advice_generator if api_key else None,
            case_provider=case_provider,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="场景服务未初始化") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_scenario(
    request: ScenarioCreateRequest,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
    x_model: str | None = Header(None, alias="X-Model"),
):
    x_base_url, x_model = _validated_runtime(context, x_base_url, x_model)
    try:
        service = _service(x_api_key, x_base_url, x_model)
        result = service.create(
            user_id=current_user.id, organization_id=context.organization_id, **request.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    process_scenario_task.delay(current_user.id, result["id"], context.organization_id)
    return result


@router.post("/contract-file", status_code=status.HTTP_201_CREATED)
async def create_contract_file_review(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    """接收 PDF/DOCX，复用 v1.9 解析器后创建合同审查任务。"""
    stored = build_isolated_upload_path(
        settings.document_uploads_path,
        organization_id=context.organization_id,
        knowledge_base_slug="scenario-contracts",
        original_filename=file.filename,
    )
    try:
        artifact = await save_upload_file(file, stored, max_bytes=settings.upload_max_bytes)
        segments = parse_document(artifact.path)
        text = "\n".join(str(item.get("text", "")) for item in segments if item.get("text"))
    except UploadValidationError as exc:
        status_code = 413 if "大小" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="合同解析失败，请确认文件可读取") from exc
    finally:
        await file.close()
        if stored.exists():
            stored.unlink()
    if not text.strip():
        raise HTTPException(status_code=422, detail="未从合同中提取到文本")
    result = _service().create(
        user_id=current_user.id,
        organization_id=context.organization_id,
        scenario_type="contract_review",
        input_data={"text": text, "original_filename": artifact.original_filename},
    )
    process_scenario_task.delay(current_user.id, result["id"], context.organization_id)
    return result


@router.get("")
def list_scenarios(
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    return {
        "items": _service().list_for_user(
            user_id=current_user.id, organization_id=context.organization_id
        )
    }


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    result = _service().get(
        user_id=current_user.id, scenario_id=scenario_id, organization_id=context.organization_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="场景任务不存在")
    return result


@router.post("/{scenario_id}/retry")
def retry_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    if (
        _service().get(
            user_id=current_user.id,
            scenario_id=scenario_id,
            organization_id=context.organization_id,
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="场景任务不存在")
    process_scenario_task.delay(current_user.id, scenario_id, context.organization_id)
    return {"id": scenario_id, "status": "PENDING"}


@router.post("/{scenario_id}/advice")
def generate_contract_advice(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
    x_model: str | None = Header(None, alias="X-Model"),
):
    """按当前浏览器临时密钥，为已有验证证据补充合同修改建议。"""
    if not x_api_key:
        raise HTTPException(status_code=422, detail="请先在设置中填写 API Key")
    x_base_url, x_model = _validated_runtime(context, x_base_url, x_model)
    try:
        result = _service(x_api_key, x_base_url, x_model).generate_contract_advice(
            user_id=current_user.id,
            scenario_id=scenario_id,
            organization_id=context.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="场景任务不存在")
    return result


@router.get("/{scenario_id}/report.pdf")
def download_report(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    scenario = _service().get(
        user_id=current_user.id, scenario_id=scenario_id, organization_id=context.organization_id
    )
    if scenario is None:
        raise HTTPException(status_code=404, detail="场景任务不存在")
    if scenario["status"] != "READY":
        raise HTTPException(status_code=409, detail="场景任务尚未完成")
    report = build_structured_report(scenario["scenario_type"], scenario.get("result_data") or {})
    return Response(
        content=build_scenario_pdf(report["title"], report["sections"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="lexrag-{scenario_id}.pdf"'},
    )
