"""
Prompt 管理服务

支持 CRUD + 版本递增 + 热加载缓存
"""

import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.prompt import Prompt

logger = logging.getLogger(__name__)

# 内存缓存：(organization_id, name) -> Prompt
_prompt_cache: dict[tuple[int, str], Prompt] = {}


def _invalidate_cache(name: str | None = None, organization_id: int | None = None):
    """使缓存失效（更新/删除时调用）"""
    if name and organization_id is not None:
        _prompt_cache.pop((organization_id, name), None)
    else:
        _prompt_cache.clear()


def get_prompt_by_name(
    db: Session,
    name: str,
    *,
    organization_id: int,
    use_cache: bool = True,
) -> Prompt | None:
    """
    按名称获取 Prompt（优先从缓存读取）

    Args:
        db: 数据库会话
        name: Prompt 名称
        use_cache: 是否使用缓存

    Returns:
        Prompt 对象，不存在返回 None
    """
    cache_key = (organization_id, name)
    if use_cache and cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    prompt = (
        db.query(Prompt)
        .filter(
            Prompt.name == name,
            Prompt.organization_id == organization_id,
            Prompt.is_active.is_(True),
        )
        .order_by(Prompt.version.desc())
        .first()
    )
    if prompt is None:
        prompt = (
            db.query(Prompt)
            .filter(
                Prompt.name == name,
                Prompt.organization_id.is_(None),
                Prompt.is_active.is_(True),
            )
            .order_by(Prompt.version.desc())
            .first()
        )

    if prompt and use_cache:
        _prompt_cache[cache_key] = prompt

    return prompt


def get_all_active_prompts(db: Session, *, organization_id: int) -> list[Prompt]:
    """获取所有活跃 Prompt（每个 name 返回最新版本）"""
    candidates = (
        db.query(Prompt)
        .filter(
            Prompt.is_active.is_(True),
            or_(Prompt.organization_id == organization_id, Prompt.organization_id.is_(None)),
        )
        .order_by(Prompt.version.desc())
        .all()
    )
    selected: dict[str, Prompt] = {}
    for prompt in candidates:
        current = selected.get(prompt.name)
        if current is None or (
            current.organization_id is None and prompt.organization_id == organization_id
        ):
            selected[prompt.name] = prompt
    return list(selected.values())


def create_prompt(
    db: Session,
    organization_id: int,
    name: str,
    content: str,
    description: str | None = None,
    category: str | None = None,
) -> Prompt:
    """
    创建新 Prompt（版本号从 1 开始）

    Raises:
        ValueError: 同名 Prompt 已存在
    """
    existing = (
        db.query(Prompt)
        .filter(Prompt.name == name, Prompt.organization_id == organization_id)
        .first()
    )
    if existing:
        raise ValueError(f"Prompt '{name}' 已存在，请使用更新接口")

    prompt = Prompt(
        organization_id=organization_id,
        name=name,
        content=content,
        version=1,
        description=description,
        category=category,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)

    # 热加载到缓存
    _prompt_cache[(organization_id, name)] = prompt
    logger.info("Prompt 已创建 organization_id=%s version=1", organization_id)
    return prompt


def update_prompt(
    db: Session,
    organization_id: int,
    name: str,
    content: str,
    description: str | None = None,
) -> Prompt:
    """
    更新 Prompt（版本号递增，旧版本标记为 inactive）

    Raises:
        ValueError: Prompt 不存在
    """
    # 获取当前版本
    current_owned = (
        db.query(Prompt)
        .filter(
            Prompt.name == name,
            Prompt.organization_id == organization_id,
            Prompt.is_active.is_(True),
        )
        .order_by(Prompt.version.desc())
        .first()
    )
    current = current_owned or get_prompt_by_name(
        db, name, organization_id=organization_id, use_cache=False
    )
    if not current:
        raise ValueError(f"Prompt '{name}' 不存在")

    # 将旧版本标记为非活跃
    if current_owned is not None:
        db.query(Prompt).filter(
            Prompt.name == name,
            Prompt.organization_id == organization_id,
        ).update({"is_active": False})

    # 创建新版本
    new_prompt = Prompt(
        organization_id=organization_id,
        name=name,
        content=content,
        version=current.version + 1,
        description=description or current.description,
        category=current.category,
        is_active=True,
    )
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)

    # 热加载到缓存
    _prompt_cache[(organization_id, name)] = new_prompt
    logger.info(
        "Prompt 已更新 organization_id=%s version=%s",
        organization_id,
        new_prompt.version,
    )
    return new_prompt


def delete_prompt(db: Session, name: str, *, organization_id: int) -> bool:
    """
    删除 Prompt（软删除：标记为 inactive）

    Returns:
        True 表示删除成功，False 表示不存在
    """
    result = (
        db.query(Prompt)
        .filter(Prompt.name == name, Prompt.organization_id == organization_id)
        .update({"is_active": False})
    )
    db.commit()

    if result:
        _invalidate_cache(name, organization_id)
        logger.info("Prompt 已删除 organization_id=%s", organization_id)
        return True
    return False


def get_prompt_history(db: Session, name: str, *, organization_id: int) -> list[Prompt]:
    """获取 Prompt 的完整版本历史"""
    return (
        db.query(Prompt)
        .filter(Prompt.name == name, Prompt.organization_id == organization_id)
        .order_by(Prompt.version.desc())
        .all()
    )


def seed_default_prompts(db: Session):
    """
    初始化默认 Prompt 模板（仅当数据库为空时）

    在应用首次启动时调用，确保至少有一套可用的 Prompt
    """
    existing = db.query(Prompt).first()
    if existing:
        logger.info("数据库中已有 Prompt，跳过初始化")
        return

    defaults = [
        {
            "name": "system_agent",
            "description": "ReAct Agent 系统提示词",
            "category": "agent",
            "content": """你是一个专业的法律助手，专门解答中国法律相关问题。

你可以使用以下工具来回答用户的问题：
1. search_statute - 检索法律条文（输入法律问题描述）
2. search_case - 检索类似判例（输入案情描述）
3. lookup_article - 精确查阅某条法条全文（输入法条编号如"第712条"）
4. analyze_legal_relation - 分析法律关系（输入案情描述）

回答原则：
- 你只能引用通过工具检索到的法条，不要引用训练数据中记忆的法条
- 每个结论都要引用具体法条，使用【法条编号】格式
- 如果工具未返回某法条，说明知识库中暂时没有，不要自行编造该法条内容
- 先理解问题，再决定调用哪个工具
- 复杂问题可以多次调用不同工具
- 回答要准确、专业、有法条支撑""",
        },
        {
            "name": "answer_generation",
            "description": "答案生成 Prompt",
            "category": "generation",
            "content": """你是一个专业的法律助手。请基于以下检索到的法律条文和案例，回答用户的问题。

## 用户问题
{question}

## 检索到的法律条文
{statute_context}

## 相关案例
{case_context}

## 法律分析
{legal_analysis}

请遵循以下要求：
1. 每个结论必须引用具体的法条编号（如"《民法典》第xxx条"）
2. 先给出法律结论，再说明法律依据
3. 如果有类似案例，可以引用作为参考
4. 语言专业但不晦涩，让非法律专业人士也能理解
5. 如果涉及多个法律问题，逐一回答""",
        },
        {
            "name": "query_rewrite",
            "description": "查询改写 Prompt",
            "category": "retrieval",
            "content": """你是一个法律检索专家。请将用户的口语化法律问题改写为更精确的法律检索查询。

## 改写规则
1. 将口语表达转换为法律术语（如"被公司开了"→"解除劳动合同"）
2. 补充隐含的法律概念（如"工伤赔偿"→扩展为"工伤保险条例 工伤认定 赔偿标准"）
3. 去除无意义的疑问词和语气词
4. 保留问题的核心法律诉求
5. 生成 {num_candidates} 个改写候选项，每个都应产生不同的检索视角

## 用户问题
{question}

请以 JSON 格式返回改写结果：
{{"rewrites": ["改写1", "改写2", ...]}}""",
        },
        {
            "name": "self_verify",
            "description": "法条自校验 Prompt",
            "category": "verification",
            "content": """你是一个法律条文校验专家。请检查以下AI回答中引用的法条是否真实准确。

## AI 回答
{answer}

请做以下检查：
1. 提取回答中所有引用的法条编号（如"第xxx条"、"《xxx法》第xxx条"）
2. 判断每条引用是否能在检索结果中找到原文支撑
3. 对于找不到原文的引用，标注为"待核实"
4. 检查法条引用是否与结论逻辑一致

请以 JSON 格式返回校验结果：
{{
  "citations": [
    {{"article_id": "法条编号", "citation_text": "引用的文本", "is_verified": true/false}}
  ],
  "issues": ["发现的问题"],
  "overall_pass": true/false,
  "corrected_answer": "修正后的回答（如果需要）"
}}""",
        },
    ]

    for p in defaults:
        prompt = Prompt(
            organization_id=None,
            name=p["name"],
            content=p["content"],
            version=1,
            description=p.get("description"),
            category=p.get("category"),
            is_active=True,
        )
        db.add(prompt)

    db.commit()
    logger.info(f"已初始化 {len(defaults)} 个默认 Prompt 模板")
