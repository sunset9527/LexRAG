"""管理员路由必须注册到真实 LexRAG 应用。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def test_admin_router_is_registered_on_application():
    import api

    paths = {
        route.path
        for route in api.app.routes
        if hasattr(route, "path")
    }
    paths.update(
        child.path
        for route in api.app.routes
        if hasattr(route, "original_router")
        for child in route.original_router.routes
        if hasattr(child, "path")
    )

    assert "/admin/organization" in paths
    assert "/admin/members" in paths
