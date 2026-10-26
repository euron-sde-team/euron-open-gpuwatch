from pathlib import Path

import yaml

from gpuwatch.openapi import spec

COMMITTED = Path(__file__).parents[5] / "docs" / "api" / "openapi.yaml"


def test_committed_openapi_matches_the_app() -> None:
    committed = yaml.safe_load(COMMITTED.read_text())
    assert committed == yaml.safe_load(yaml.safe_dump(spec())), "regenerate with: make openapi"


def test_every_operation_is_documented() -> None:
    for path, ops in spec()["paths"].items():
        for method, op in ops.items():
            assert op.get("summary"), f"{method.upper()} {path} has no summary"
