"""Convert Thunder Client collection/env to Postman Collection v2.1."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
THUNDER_DIR = ROOT / "thunder-tests"
OUT_DIR = ROOT / "postman"
FIXTURES_DIR = ROOT.parent / "reassignmentcheckin"

# Map extract/wearable request name fragments -> fixture filename
FIXTURE_FILES = {
    "lab_cbc_kauh.pdf": FIXTURES_DIR / "lab_cbc_kauh.pdf",
    "echocardiogram_fakeeh.pdf": FIXTURES_DIR / "echocardiogram_fakeeh.pdf",
    "PHOTO-2026-05-25-18-43-01.jpg": FIXTURES_DIR / "PHOTO-2026-05-25-18-43-01.jpg",
    "renal_ultrasound_sgh.pdf": FIXTURES_DIR / "renal_ultrasound_sgh.pdf",
    "wearable_export.xml": FIXTURES_DIR / "wearable_export.xml",
}


def resolve_fixture_from_name(request_name: str) -> Path | None:
    for filename, path in FIXTURE_FILES.items():
        if filename in request_name:
            return path if path.is_file() else None
    return None


def parse_url(url: str, params: list) -> dict:
    query: list[dict] = []
    if "?" in url:
        base, qs = url.split("?", 1)
        for part in qs.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                query.append({"key": key, "value": value})
            elif part:
                query.append({"key": part, "value": None})
        path_url = base
    else:
        path_url = url
        for param in params or []:
            if not param.get("isPath"):
                query.append({"key": param["name"], "value": param.get("value", "")})

    if path_url.startswith("{{baseUrl}}"):
        rest = path_url[len("{{baseUrl}}") :].lstrip("/")
        path = [p for p in rest.split("/") if p] if rest else []
        return {
            "raw": url,
            "host": ["{{baseUrl}}"],
            "path": path,
            "query": query,
        }
    return {"raw": url, "host": ["{{baseUrl}}"], "path": [], "query": query}


def body_to_postman(body: dict | None, request_name: str = "") -> dict | None:
    if not body or body.get("type") == "none":
        return None
    if body.get("type") == "json":
        return {
            "mode": "raw",
            "raw": body.get("raw") or "",
            "options": {"raw": {"language": "json"}},
        }
    if body.get("type") == "formdata":
        fixture = resolve_fixture_from_name(request_name)
        formdata = []
        for item in body.get("form") or []:
            if item.get("type") == "file":
                src = item.get("value") or ""
                if not src and fixture is not None:
                    src = str(fixture)
                formdata.append(
                    {
                        "key": item["name"],
                        "type": "file",
                        "src": src if src else None,
                    }
                )
            else:
                formdata.append(
                    {
                        "key": item["name"],
                        "type": "text",
                        "value": item.get("value", ""),
                    }
                )
        return {"mode": "formdata", "formdata": formdata}
    return None


def headers_to_postman(headers: list | None) -> list[dict]:
    return [{"key": h["name"], "value": h["value"]} for h in (headers or [])]


def tests_to_event(tests: list | None) -> dict | None:
    if not tests:
        return None
    lines: list[str] = []
    for test in tests:
        if test.get("type") == "res-code" and test.get("action") == "equal":
            code = test.get("value")
            lines.append(
                "pm.test('Status is %s', function () { pm.response.to.have.status(%s); });"
                % (code, code)
            )
        elif test.get("type") == "json-query":
            path = (test.get("custom") or "").removeprefix("json.")
            parts = path.split(".") if path else []
            accessor = "json"
            for part in parts:
                if part.isidentifier():
                    accessor += f".{part}"
                else:
                    accessor += f'["{part}"]'
            if test.get("action") == "equal":
                value = test.get("value")
                if value == "{{patientId}}":
                    rhs = (
                        "pm.environment.get('patientId') || "
                        "pm.collectionVariables.get('patientId')"
                    )
                elif isinstance(value, str) and value.isdigit():
                    rhs = value
                else:
                    rhs = json.dumps(value)
                lines.append(
                    "pm.test('%s equals expected', function () { "
                    "const json = pm.response.json(); "
                    "pm.expect(%s).to.eql(%s); "
                    "});" % (path, accessor, rhs)
                )
            elif test.get("action") == "istype":
                typ = test.get("value")
                if typ == "array":
                    lines.append(
                        "pm.test('%s is array', function () { "
                        "const json = pm.response.json(); "
                        "pm.expect(%s).to.be.an('array'); "
                        "});" % (path, accessor)
                    )
                else:
                    lines.append(
                        "pm.test('%s is %s', function () { "
                        "const json = pm.response.json(); "
                        "pm.expect(%s).to.be.an('%s'); "
                        "});" % (path, typ, accessor, typ)
                    )
    if not lines:
        return None
    return {
        "listen": "test",
        "script": {"type": "text/javascript", "exec": lines},
    }


def patch_thunder_file_paths(thunder: dict) -> dict:
    """Embed absolute fixture paths into Thunder form file fields."""
    for req in thunder.get("requests", []):
        body = req.get("body") or {}
        if body.get("type") != "formdata":
            continue
        fixture = resolve_fixture_from_name(req.get("name", ""))
        if fixture is None:
            continue
        for item in body.get("form") or []:
            if item.get("type") == "file":
                item["value"] = str(fixture)
        req["docs"] = f"File pre-attached: {fixture}"
    return thunder


def main() -> None:
    thunder_path = THUNDER_DIR / "thunder-collection_VitaReports.json"
    thunder = json.loads(thunder_path.read_text(encoding="utf-8"))
    thunder = patch_thunder_file_paths(thunder)
    thunder_path.write_text(json.dumps(thunder, indent=2), encoding="utf-8")

    env_path = THUNDER_DIR / "thunder-environment_Local.json"
    env = json.loads(env_path.read_text(encoding="utf-8"))
    data = env.setdefault("data", [])
    if not any(v.get("name") == "fixturesDir" for v in data):
        data.append({"name": "fixturesDir", "value": str(FIXTURES_DIR)})
    else:
        for v in data:
            if v.get("name") == "fixturesDir":
                v["value"] = str(FIXTURES_DIR)
    env_path.write_text(json.dumps(env, indent=2), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)

    folders = sorted(thunder["folders"], key=lambda f: f.get("sortNum", 0))
    folder_by_id = {f["_id"]: f for f in folders}
    items_by_folder: dict[str, list] = {f["_id"]: [] for f in folders}

    for req in sorted(
        thunder["requests"],
        key=lambda r: (
            folder_by_id.get(r["containerId"], {}).get("sortNum", 0),
            r.get("sortNum", 0),
        ),
    ):
        item = {
            "name": req["name"],
            "request": {
                "method": req["method"],
                "header": headers_to_postman(req.get("headers")),
                "url": parse_url(req["url"], req.get("params") or []),
                "description": req.get("docs") or "",
            },
            "response": [],
        }
        body = body_to_postman(req.get("body"), req.get("name", ""))
        if body:
            item["request"]["body"] = body
        event = tests_to_event(req.get("tests"))
        if event:
            item["event"] = [event]
        items_by_folder.setdefault(req["containerId"], []).append(item)

    collection = {
        "info": {
            "_postman_id": str(uuid4()),
            "name": thunder.get("name", "VitaReports"),
            "description": thunder.get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": folder["name"],
                "item": items_by_folder.get(folder["_id"], []),
                "description": "",
            }
            for folder in folders
        ],
        "variable": [
            {"key": "baseUrl", "value": "http://127.0.0.1:8000"},
            {"key": "patientId", "value": "VTR-00471"},
            {"key": "fixturesDir", "value": str(FIXTURES_DIR)},
        ],
    }

    environment = {
        "id": str(uuid4()),
        "name": env.get("name", "Local"),
        "values": [
            {
                "key": value["name"],
                "value": value["value"],
                "type": "default",
                "enabled": True,
            }
            for value in env.get("data", [])
        ],
        "_postman_variable_scope": "environment",
    }

    collection_path = OUT_DIR / "VitaReports.postman_collection.json"
    env_out = OUT_DIR / "Local.postman_environment.json"
    collection_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    env_out.write_text(json.dumps(environment, indent=2), encoding="utf-8")
    print(f"Updated {thunder_path}")
    print(f"Wrote {collection_path}")
    print(f"Wrote {env_out}")
    print(f"fixturesDir={FIXTURES_DIR}")
    missing = [name for name, path in FIXTURE_FILES.items() if not path.is_file()]
    if missing:
        print("WARNING missing fixtures:", missing)


if __name__ == "__main__":
    main()
