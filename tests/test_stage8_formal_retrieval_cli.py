"""Formal runner integration tests: all external indexing/query work is fake."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_formal_runner_exists():
    assert (ROOT / "scripts/evaluate_stage8_formal_retrieval.py").is_file()


@pytest.fixture
def cli():
    path = ROOT / "scripts/evaluate_stage8_formal_retrieval.py"
    assert path.is_file(), "the separate formal retrieval CLI is missing"
    return importlib.import_module("scripts.evaluate_stage8_formal_retrieval")


@pytest.fixture
def inputs(tmp_path):
    directory = ROOT / "data/evaluation/stage8"
    rows = [
        json.loads(line)
        for line in (directory / "stage8_frozen_280.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    selected = [
        next(row for row in rows if row["expected_knowledge_base_slugs"] == [slug])
        for slug in ("civil-code", "criminal-law")
    ]
    snapshot = json.loads(
        (directory / "stage4_provenance_2026-10-27.json").read_text(encoding="utf-8")
    )
    snapshot["laws"] = [
        law
        for law in snapshot["laws"]
        if law["knowledge_base_slug"] in {"civil-code", "criminal-law"}
    ]
    dataset_path, snapshot_path = tmp_path / "data.jsonl", tmp_path / "snapshot.json"
    dataset_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in selected), encoding="utf-8"
    )
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    chroma = tmp_path / "chroma"
    chroma.mkdir()
    return SimpleNamespace(
        rows=selected,
        snapshot=snapshot,
        dataset=dataset_path,
        snapshot_path=snapshot_path,
        chroma=chroma,
        output=tmp_path / "report.json",
    )


def args(inputs, mode="vector"):
    return [
        "--dataset",
        str(inputs.dataset),
        "--snapshot",
        str(inputs.snapshot_path),
        "--persist-directory",
        str(inputs.chroma),
        "--mode",
        mode,
        "--output",
        str(inputs.output),
    ]


@pytest.fixture
def runtime(cli, inputs, monkeypatch):
    calls = []
    laws = {law["collection_name"]: law for law in inputs.snapshot["laws"]}
    labels = {
        row["expected_knowledge_base_slugs"][0]: row["relevant_article_ids"][0]
        for row in inputs.rows
    }

    class Collection:
        def __init__(self, name):
            self.name = name
            self.law = laws[name]
            self.metadata = {
                "lexrag_statute_source_sha256": self.law["content_hash"],
                "lexrag_embedding_fingerprint": self.law["embedding_fingerprint"],
                "lexrag_index_schema_version": self.law["index_schema_version"],
            }

        def count(self):
            return self.law["chunk_count"]

    class Client:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        def get_collection(self, name):
            calls.append(("collection", name))
            return Collection(name)

    class Indexer:
        def __init__(self, **kwargs):
            calls.append(("indexer", kwargs))
            self.vectorstore = laws[kwargs["collection_name"]]["knowledge_base_slug"]

    class Retriever:
        def __init__(self, vectorstore, **kwargs):
            self.slug = vectorstore
            self._bm25 = SimpleNamespace(retrieve=self.bm25)
            self.enable_optimization = True
            calls.append(("retriever", vectorstore, kwargs))

        def retrieve(self, query, **kwargs):
            calls.append(("vector", self.slug, kwargs))
            return [SimpleNamespace(article_id=labels[self.slug], metadata={})]

        def _ensure_optimization_data(self):
            calls.append(("ensure", self.slug))

        def bm25(self, query, **kwargs):
            calls.append(("bm25", self.slug, kwargs))
            return [SimpleNamespace(metadata={"article_id": labels[self.slug]})]

        def retrieve_optimized(self, query, **kwargs):
            calls.append(("rrf", self.slug, kwargs))
            return [SimpleNamespace(article_id=labels[self.slug], metadata={})], "", []

    identity = SimpleNamespace(
        fingerprint=inputs.snapshot["laws"][0]["embedding_fingerprint"], schema_version=1
    )
    monkeypatch.setattr(cli, "_runtime_components", lambda: (Client, Indexer, Retriever, identity))
    return SimpleNamespace(calls=calls, Collection=Collection, Retriever=Retriever)


def test_help_works_without_runtime_or_external_services(cli):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate_stage8_formal_retrieval.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "--persist-directory" in completed.stdout
    assert "--collection" not in completed.stdout


@pytest.mark.parametrize("mode", ["vector", "bm25", "rrf"])
def test_modes_snapshot_binding_and_report(cli, inputs, runtime, mode):
    assert cli.main(args(inputs, mode)) == 0
    report = json.loads(inputs.output.read_text(encoding="utf-8"))
    assert report["schema"] == "lexrag.stage8-formal-retrieval-routing"
    assert report["version"] == 1
    assert report["mode"] == mode
    assert "abstention accuracy" in report["scope"]
    assert report["oracle_retrieval"]["overall"]["recall_at_1"] == 1
    assert report["routing"]["evaluation"] == "automatic_routing"
    assert report["snapshot"]["laws"] == inputs.snapshot["laws"]
    manifest = report["run_manifest"]
    assert len(manifest["git_commit"]) == 40
    assert manifest["runtime_identity"] == {"provider": "local", "model": "no-model"}
    assert (
        manifest["datasets"][0]["sha256"] == hashlib.sha256(inputs.dataset.read_bytes()).hexdigest()
    )
    assert (
        manifest["legal_source_manifests"][0]["sha256"]
        == hashlib.sha256(inputs.snapshot_path.read_bytes()).hexdigest()
    )
    assert manifest["collection_names"] == [
        law["collection_name"] for law in inputs.snapshot["laws"]
    ]
    indexer_calls = [call[1] for call in runtime.calls if call[0] == "indexer"]
    assert {call["collection_name"] for call in indexer_calls} == set(manifest["collection_names"])
    assert all(call["persist_directory"] == str(inputs.chroma) for call in indexer_calls)
    assert len([call for call in runtime.calls if call[0] == mode]) == 2
    if mode == "rrf":
        assert {call[1]: call[2]["law_name"] for call in runtime.calls if call[0] == "rrf"} == {
            "civil-code": "中华人民共和国民法典",
            "criminal-law": "中华人民共和国刑法",
        }


def test_routing_uses_ordered_candidates_even_when_selection_empty(
    cli, inputs, runtime, monkeypatch
):
    seen = []

    class Router:
        def route(self, question, available):
            seen.append(available)
            return SimpleNamespace(
                selected_slugs=[],
                candidates=[
                    SimpleNamespace(slug="criminal-law"),
                    SimpleNamespace(slug="civil-code"),
                ],
            )

    monkeypatch.setattr(cli, "_make_router", Router)
    assert cli.main(args(inputs)) == 0
    report = json.loads(inputs.output.read_text(encoding="utf-8"))
    assert all(
        item["candidate_knowledge_base_slugs"] == ["criminal-law", "civil-code"]
        for item in report["routing"]["items"]
    )
    assert report["routing"]["overall"]["candidate_recall"] == 1
    assert {item["slug"] for item in seen[0]} == {"civil-code", "criminal-law"}


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_slug",
        "duplicate_collection",
        "missing_collection",
        "pending",
        "source_mismatch",
        "invalid_json",
    ],
)
def test_validation_fails_before_runtime_and_preserves_output(cli, inputs, runtime, mutation):
    if mutation == "extra_slug":
        inputs.snapshot["laws"].pop()
    elif mutation == "duplicate_collection":
        inputs.snapshot["laws"][1]["collection_name"] = inputs.snapshot["laws"][0][
            "collection_name"
        ]
    elif mutation == "missing_collection":
        inputs.snapshot["laws"][0]["collection_name"] = ""
    elif mutation == "pending":
        inputs.rows[0]["review_status"] = "pending"
    elif mutation == "source_mismatch":
        inputs.rows[0]["source_evidence"][0]["content_hash"] = "f" * 64
    inputs.dataset.write_text("\n".join(json.dumps(row) for row in inputs.rows), encoding="utf-8")
    inputs.snapshot_path.write_text(
        "{bad" if mutation == "invalid_json" else json.dumps(inputs.snapshot), encoding="utf-8"
    )
    inputs.output.write_bytes(b"existing")
    assert cli.main(args(inputs)) == 1
    assert inputs.output.read_bytes() == b"existing"
    assert runtime.calls == []


def test_no_collection_override_and_required_options(cli, inputs):
    with pytest.raises(SystemExit):
        cli.main(args(inputs) + ["--collection", "arbitrary"])
    for required in ("--dataset", "--snapshot", "--persist-directory", "--mode", "--output"):
        argv = args(inputs)
        start = argv.index(required)
        del argv[start : start + 2]
        with pytest.raises(SystemExit):
            cli.main(argv)


def test_missing_or_changed_collection_fails_before_indexer(
    cli, inputs, runtime, monkeypatch, capsys
):
    def fail(self, name):
        raise OSError("password=do-not-print")

    client_class = cli._runtime_components()[0]
    monkeypatch.setattr(client_class, "get_collection", fail)
    assert cli.main(args(inputs)) == 1
    assert not inputs.output.exists()
    assert "do-not-print" not in capsys.readouterr().err
    assert not any(call[0] == "indexer" for call in runtime.calls)


def test_changed_collection_metadata_rejected(cli, inputs, runtime, monkeypatch):
    original = runtime.Collection.__init__

    def changed(self, name):
        original(self, name)
        self.metadata["lexrag_statute_source_sha256"] = "f" * 64

    monkeypatch.setattr(runtime.Collection, "__init__", changed)
    assert cli.main(args(inputs)) == 1
    assert not any(call[0] == "indexer" for call in runtime.calls)


def test_unknown_result_is_safe_execution_error(cli, inputs, runtime, monkeypatch):
    def retrieve(self, query, **kwargs):
        raise RuntimeError("password=do-not-print")

    monkeypatch.setattr(runtime.Retriever, "retrieve", retrieve)
    assert cli.main(args(inputs)) == 0
    raw = inputs.output.read_text(encoding="utf-8")
    assert "do-not-print" not in raw
    assert json.loads(raw)["oracle_retrieval"]["overall"]["execution_error_count"] == 2


def test_unmapped_article_is_execution_error(cli, inputs, runtime, monkeypatch):
    monkeypatch.setattr(
        runtime.Retriever,
        "retrieve",
        lambda *a, **kw: [SimpleNamespace(article_id="unknown", metadata={})],
    )
    assert cli.main(args(inputs)) == 0
    report = json.loads(inputs.output.read_text(encoding="utf-8"))
    assert report["oracle_retrieval"]["overall"]["execution_error_count"] == 2


def test_internal_vector_failure_cannot_be_silently_scored_as_miss(
    cli, inputs, runtime, monkeypatch
):
    original = runtime.Retriever.__init__

    def fail(*args, **kwargs):
        raise OSError("password=do-not-print")

    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.vectorstore = SimpleNamespace(similarity_search_with_relevance_scores=fail)

    def swallowing_retrieve(self, question, **kwargs):
        try:
            self.vectorstore.similarity_search_with_relevance_scores(question)
        except Exception:
            return []

    monkeypatch.setattr(runtime.Retriever, "__init__", initialize)
    monkeypatch.setattr(runtime.Retriever, "retrieve", swallowing_retrieve)
    assert cli.main(args(inputs)) == 0
    raw = inputs.output.read_text(encoding="utf-8")
    report = json.loads(raw)
    assert report["oracle_retrieval"]["overall"]["execution_error_count"] == 2
    assert "do-not-print" not in raw


def test_rrf_must_not_fall_back_to_vector(cli, inputs, runtime, monkeypatch):
    original = runtime.Retriever._ensure_optimization_data

    def disabled(self):
        original(self)
        self.enable_optimization = False

    monkeypatch.setattr(runtime.Retriever, "_ensure_optimization_data", disabled)
    assert cli.main(args(inputs, "rrf")) == 0
    report = json.loads(inputs.output.read_text(encoding="utf-8"))
    assert report["oracle_retrieval"]["overall"]["execution_error_count"] == 2
    assert not any(call[0] in {"vector", "rrf"} for call in runtime.calls)


def test_wrong_law_result_keeps_actual_snapshot_slug(cli, inputs, runtime, monkeypatch):
    criminal = inputs.rows[1]["relevant_article_ids"][0]
    monkeypatch.setattr(
        runtime.Retriever,
        "retrieve",
        lambda *a, **kw: [SimpleNamespace(article_id=criminal, metadata={})],
    )
    assert cli.main(args(inputs)) == 0
    report = json.loads(inputs.output.read_text(encoding="utf-8"))
    civil = report["oracle_retrieval"]["items"][0]
    assert civil["ranked_evidence_by_knowledge_base"]["civil-code"] == [
        {"knowledge_base_slug": "criminal-law", "article_id": criminal}
    ]
    assert civil["metrics"]["recall_at_5"] == 0


def test_output_replacement_failure_preserves_bytes_and_cleans_temp(
    cli, inputs, runtime, monkeypatch, capsys
):
    inputs.output.write_bytes(b"existing")

    def fail(*args):
        raise OSError("password=do-not-print")

    monkeypatch.setattr(os, "replace", fail)
    assert cli.main(args(inputs)) == 1
    assert inputs.output.read_bytes() == b"existing"
    assert not list(inputs.output.parent.glob("*.tmp"))
    assert "do-not-print" not in capsys.readouterr().err


@pytest.mark.parametrize("target", ["dataset", "snapshot_path", "chroma"])
def test_output_cannot_overwrite_inputs(cli, inputs, runtime, target):
    inputs.output = getattr(inputs, target)
    if target == "chroma":
        inputs.output /= "report.json"
    assert cli.main(args(inputs)) == 1
    assert runtime.calls == []


def test_manifest_binds_runner_checkout_when_invoked_from_another_directory(
    cli, inputs, runtime, monkeypatch, tmp_path
):
    expected = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent.resolve()))
    monkeypatch.chdir(tmp_path)
    assert cli.main(args(inputs)) == 0
    report = json.loads(inputs.output.read_text(encoding="utf-8"))
    assert report["run_manifest"]["git_commit"] == expected
