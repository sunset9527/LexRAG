"""Materialize the formal 280-row Stage 8 dataset and bound manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.stage8_materializer import (
    Stage8MaterializationError,
    build_stage8_manifest,
    load_reviewed_baseline,
    load_stage4_snapshot,
    materialize_stage8_records,
    records_jsonl,
    validate_formal_freeze_counts,
)


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("generated-at must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("generated-at must include a timezone")
    return parsed


def _validate_paths(
    baseline: Path,
    snapshot: Path,
    dataset_output: Path,
    manifest_output: Path,
) -> None:
    inputs = {baseline.resolve(), snapshot.resolve()}
    outputs = {dataset_output.resolve(), manifest_output.resolve()}
    if inputs & outputs:
        raise Stage8MaterializationError("output paths must not overlap either input")
    if len(outputs) != 2:
        raise Stage8MaterializationError("dataset and manifest outputs must be distinct")
    if dataset_output.exists() != manifest_output.exists():
        raise Stage8MaterializationError(
            "paired outputs are inconsistent: both must exist or both must be absent"
        )


def _stage(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return Path(temporary_name)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _restore(path: Path, original: bytes | None) -> None:
    if original is None:
        path.unlink(missing_ok=True)
        return
    staged = _stage(path.with_name(f"{path.name}.restore"), original)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def _write_pair_atomically(
    dataset_path: Path,
    dataset_payload: bytes,
    manifest_path: Path,
    manifest_payload: bytes,
) -> None:
    if dataset_path.resolve() == manifest_path.resolve():
        raise Stage8MaterializationError("dataset and manifest outputs must be distinct")
    old_dataset = dataset_path.read_bytes() if dataset_path.exists() else None
    old_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    dataset_stage: Path | None = None
    manifest_stage: Path | None = None
    try:
        dataset_stage = _stage(dataset_path, dataset_payload)
        manifest_stage = _stage(manifest_path, manifest_payload)
        os.replace(dataset_stage, dataset_path)
        os.replace(manifest_stage, manifest_path)
    except OSError:
        restore_errors: list[OSError] = []
        for path, original in (
            (dataset_path, old_dataset),
            (manifest_path, old_manifest),
        ):
            try:
                _restore(path, original)
            except OSError as exc:
                restore_errors.append(exc)
        if restore_errors:
            raise OSError("paired output write failed and rollback was incomplete") from restore_errors[0]
        raise
    finally:
        if dataset_stage is not None:
            dataset_stage.unlink(missing_ok=True)
        if manifest_stage is not None:
            manifest_stage.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    default = ROOT / "data" / "evaluation" / "stage8"
    parser.add_argument(
        "--baseline",
        type=Path,
        default=default / "stage8_reviewed_baseline_280.jsonl",
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--dataset-output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--generated-at", type=_aware_datetime)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _validate_paths(args.baseline, args.snapshot, args.dataset_output, args.manifest_output)
        baseline, baseline_payload = load_reviewed_baseline(args.baseline)
        snapshot, snapshot_payload = load_stage4_snapshot(args.snapshot)
        records = materialize_stage8_records(baseline, snapshot)
        validate_formal_freeze_counts(records)
        dataset_payload = records_jsonl(records)
        manifest = build_stage8_manifest(
            records,
            dataset_payload=dataset_payload,
            baseline_payload=baseline_payload,
            snapshot_payload=snapshot_payload,
            generated_at=args.generated_at or datetime.now(timezone.utc),
        )
        manifest_payload = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        _write_pair_atomically(
            args.dataset_output,
            dataset_payload,
            args.manifest_output,
            manifest_payload,
        )
    except (Stage8MaterializationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "dataset_rows": manifest["dataset"]["row_count"],
                "dataset_sha256": manifest["dataset"]["sha256"],
                "manifest_output": str(args.manifest_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
