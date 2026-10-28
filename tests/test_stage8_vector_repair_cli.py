from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = ROOT / "scripts" / "repair_stage8_vector_index_copy.py"
    spec = importlib.util.spec_from_file_location("stage8_vector_repair_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_cli_binds_snapshot_and_writes_auditable_repair_report(tmp_path, monkeypatch):
    cli = _load_script()
    source = tmp_path / "source"
    target = tmp_path / "target"
    output = tmp_path / "report.json"
    snapshot = tmp_path / "snapshot.json"
    source.mkdir()
    snapshot.write_text("{}", encoding="utf-8")
    law = {
        "knowledge_base_slug": "civil-code",
        "collection_name": "kb_civil_code_v_aaaaaaaaaaaa",
    }
    seen = {}

    monkeypatch.setattr(cli, "load_stage4_snapshot", lambda _: ({"as_of": "2026-10-27", "laws": [law]}, {}))

    def repair(actual_source, actual_target, laws, *, client_factory):
        seen.update(source=actual_source, target=actual_target, laws=laws, client_factory=client_factory)
        return {"collections": [{"collection_name": law["collection_name"], "queryable": True}]}

    monkeypatch.setattr(cli, "repair_isolated_copy", repair)
    assert (
        cli.main(
            [
                "--source-directory",
                str(source),
                "--target-directory",
                str(target),
                "--snapshot",
                str(snapshot),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "lexrag.stage8-vector-index-repair"
    assert report["snapshot"]["sha256"]
    assert report["collections"] == [{"collection_name": law["collection_name"], "queryable": True}]
    assert seen["source"] == source
    assert seen["target"] == target
    assert seen["laws"] == {"civil-code": law}
