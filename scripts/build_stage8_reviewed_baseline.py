"""CLI for constructing the non-formal Stage 8 reviewed candidate baseline."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.evaluation.stage8_reviewed_baseline import Stage8ReviewedBaselineError, baseline_jsonl, build_reviewed_baseline

def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream: stream.write(text)
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except OSError: pass
        raise

def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]; default = root / "data/evaluation/stage8"
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, default=default / "review_queue_300.jsonl")
    parser.add_argument("--second", type=Path, default=default / "round2_candidates_171.jsonl")
    parser.add_argument("--manifest", type=Path, default=default / "round2_remediation_manifest.json")
    parser.add_argument("--first-pending", type=Path, default=default / "review_queue_300.pending.bak.jsonl")
    parser.add_argument("--second-pending", type=Path, default=default / "round2_candidates_171.pending.bak.jsonl")
    parser.add_argument("--baseline-output", type=Path)
    parser.add_argument("--scope-output", type=Path)
    args = parser.parse_args(argv)
    try:
        baseline, scope = build_reviewed_baseline(args.first,args.second,args.manifest,args.first_pending,args.second_pending)
        if bool(args.baseline_output) != bool(args.scope_output): raise Stage8ReviewedBaselineError("必须同时提供两个输出路径，或均不提供")
        if args.baseline_output:
            _write_atomic(args.baseline_output, baseline_jsonl(baseline)); _write_atomic(args.scope_output, json.dumps(scope, ensure_ascii=False, indent=2)+"\n")
        print(json.dumps({"kind": scope["kind"], "count":len(baseline), "retired_count":scope["retired_count"], "sha256":scope["sha256"]["baseline_jsonl"]}, ensure_ascii=False))
        return 0
    except Stage8ReviewedBaselineError as exc:
        print(str(exc)); return 1
if __name__ == "__main__": raise SystemExit(main())
