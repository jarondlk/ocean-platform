import argparse
import subprocess
import json
import copy
from pathlib import Path
from schema.context_catalogue import (
    CatalogueNode,
    ListingRequest,
    CatalogueListing,
    QueryResult,
)

models = {
    "CatalogueNode": CatalogueNode,
    "ListingRequest": ListingRequest,
    "CatalogueListing": CatalogueListing,
    "QueryResult": QueryResult,
}

parser = argparse.ArgumentParser()
parser.add_argument("--output-dir", default="/private/tmp/ocean-c08-parity")
parser.add_argument(
    "--node",
    default="/Users/jaronchai/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
)
args = parser.parse_args()
output = Path(args.output_dir)
output.mkdir(parents=True, exist_ok=True)
here = Path(__file__).resolve().parent
base = json.loads((here / "review-parity-seeds.json").read_text())
seeds = {
    name: base[key]
    for name, key in [
        ("CatalogueNode", "node"),
        ("ListingRequest", "request"),
        ("CatalogueListing", "listing"),
        ("QueryResult", "result"),
    ]
}
cases = []
variants = [
    None,
    True,
    False,
    0,
    1,
    1.0,
    1.5,
    -1,
    9007199254740991,
    9007199254740992,
    9007199254740993,
    1e20,
    -1e20,
    "",
    " ",
    "x",
    "\n",
    "\u0085",
    "\ufeff",
    [],
    {},
]


def paths(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from paths(v, path + (k,))
    elif isinstance(value, list) and value:
        yield from paths(value[0], path + (0,))


def put(value, path, new):
    if not path:
        return new
    p = value
    for key in path[:-1]:
        p = p[key]
    p[path[-1]] = new
    return value


def remove(value, path):
    p = value
    for key in path[:-1]:
        p = p[key]
    if isinstance(p, dict):
        del p[path[-1]]
    else:
        p.pop(path[-1])
    return value


for name, value in seeds.items():
    cases.append({"model": name, "id": "base", "value": value})
    for path, old in paths(value):
        for i, new in enumerate(variants):
            if type(old) is type(new) and old == new:
                continue
            cases.append(
                {
                    "model": name,
                    "id": str(path) + ":replace:" + str(i),
                    "value": put(copy.deepcopy(value), path, new),
                }
            )
        if path:
            cases.append(
                {
                    "model": name,
                    "id": str(path) + ":missing",
                    "value": remove(copy.deepcopy(value), path),
                }
            )
        if isinstance(old, dict):
            changed = copy.deepcopy(old)
            changed["unexpected_field"] = "x"
            cases.append(
                {
                    "model": name,
                    "id": str(path) + ":extra",
                    "value": put(copy.deepcopy(value), path, changed),
                }
            )
# Target scientific date/time/scope and unicode parsing cases.
for text in [
    "2024-02-29",
    "2023-02-29",
    "2024-02-30",
    "0000-01-01",
    "9999-12-31",
    "9999-12-31T23:59:59-23:59",
    "0001-01-01T00:00:00+23:59",
    "2024-01-01T12:00:00+24:00",
    "2024-01-01T12:00:00+00:60",
    "2024-01-01T12:00:00.1234567Z",
    "2024-01-01T12:00:00",
    "2024-01-01 12:00:00",
    "2024-01-01T12:00:00.000001Z",
    "2024-01-01T12:00:00+09:30",
]:
    v = copy.deepcopy(seeds["ListingRequest"])
    v["scope"]["sources"]["ctd"]["filters"]["time_from"] = text
    cases.append({"model": "ListingRequest", "id": "time:" + text, "value": v})
for text in [
    "\x1c",
    "\x1d",
    "\x1e",
    "\x1f",
    "\u0085",
    "\ufeff",
    "\u180e",
    "\u200b",
    "\u202f",
    "\u3000",
    "\u205f",
    "x\n",
]:
    for name, path in [
        ("CatalogueNode", ("title", "en")),
        ("CatalogueNode", ("id",)),
        ("ListingRequest", ("scope", "sources", "ctd", "filters", "station")),
    ]:
        cases.append(
            {
                "model": name,
                "id": "unicode:" + str(path) + ":" + repr(text),
                "value": put(copy.deepcopy(seeds[name]), path, text),
            }
        )
outputs = []
for case in cases:
    try:
        parsed = models[case["model"]].model_validate(case["value"])
        outputs.append({"ok": True, "value": parsed.model_dump(mode="json")})
    except Exception as exc:
        outputs.append({"ok": False, "error": type(exc).__name__})
(output / "cases.json").write_text(json.dumps(cases, ensure_ascii=False))
(output / "python.json").write_text(json.dumps(outputs, ensure_ascii=False))
print(len(cases), "cases prepared,", sum(o["ok"] for o in outputs), "Python accepts")

process = subprocess.run(
    [
        args.node,
        "--experimental-strip-types",
        "--disable-warning=ExperimentalWarning",
        "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON",
        str(here / "review_parity.mjs"),
        str(output / "cases.json"),
        str(output / "typescript.json"),
    ],
    check=True,
)
ts = json.loads((output / "typescript.json").read_text())
acceptance = []
normalization = []
for case, py, js in zip(cases, outputs, ts, strict=True):
    if py["ok"] != js["ok"]:
        acceptance.append(
            {
                "model": case["model"],
                "id": case["id"],
                "python_ok": py["ok"],
                "typescript_ok": js["ok"],
            }
        )
    elif py["ok"] and py["value"] != js["value"]:
        normalization.append({"model": case["model"], "id": case["id"]})
summary = {
    "cases": len(cases),
    "python_accepts": sum(row["ok"] for row in outputs),
    "typescript_accepts": sum(row["ok"] for row in ts),
    "acceptance_differences": acceptance,
    "normalization_differences": normalization,
}
(output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
if acceptance or normalization:
    raise SystemExit(1)
