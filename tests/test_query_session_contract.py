"""主查询接口必须要求真实登录用户，而不是写入匿名用户 1。"""

import inspect

import api


def test_query_requires_authenticated_user_dependency():
    parameters = inspect.signature(api.query).parameters

    assert "current_user" in parameters
