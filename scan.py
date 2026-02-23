#!/usr/bin/env python3
"""
Admin Apps Audit - Scanner de servicios en proyectos Cursor.
Escanea todos los proyectos, detecta .env vars, dependencias,
y genera un HTML interactivo con filtros.

Uso:
    python3 scan.py              # Escanear y generar HTML
    python3 scan.py --open       # Escanear, generar y abrir en browser
    python3 scan.py --diff       # Mostrar cambios desde último scan
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "services_config.json"
OUTPUT_HTML = SCRIPT_DIR / "audit.html"
LAST_SCAN_PATH = SCRIPT_DIR / ".last_scan.json"
HOME = Path.home()


def expand_path(p: str) -> Path:
    return Path(p.replace("~", str(HOME)))


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def find_env_files(project_path: Path) -> list[Path]:
    env_files = []
    if not project_path.exists():
        return env_files
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build")]
        for f in files:
            if f.startswith(".env") or f.endswith(".env") or f == ".env.example":
                env_files.append(Path(root) / f)
            if f.startswith("config_") and f.endswith((".txt", ".sh")):
                env_files.append(Path(root) / f)
    return env_files


def extract_env_var_names(env_file: Path) -> set[str]:
    names = set()
    try:
        with open(env_file, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key = line.split("=", 1)[0].strip()
                    key = key.lstrip("# ")
                    if re.match(r"^[A-Z][A-Z0-9_]*$", key):
                        names.add(key)
    except (PermissionError, OSError):
        pass
    return names


def find_package_json_deps(project_path: Path) -> dict:
    deps = {"dependencies": set(), "devDependencies": set()}
    if not project_path.exists():
        return deps
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", "build")]
        if "package.json" in files:
            try:
                with open(Path(root) / "package.json") as f:
                    pkg = json.load(f)
                for key in ("dependencies", "devDependencies"):
                    if key in pkg:
                        deps[key].update(pkg[key].keys())
            except (json.JSONDecodeError, PermissionError, OSError):
                pass
    return deps


def find_requirements_txt_deps(project_path: Path) -> set[str]:
    pkgs = set()
    if not project_path.exists():
        return pkgs
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "venv", ".venv", "__pycache__")]
        for f in files:
            if f.startswith("requirements") and f.endswith(".txt"):
                try:
                    with open(Path(root) / f, encoding="utf-8", errors="ignore") as fh:
                        for line in fh:
                            line = line.strip()
                            if line and not line.startswith("#") and not line.startswith("-"):
                                pkg = re.split(r"[>=<\[!;]", line)[0].strip()
                                if pkg:
                                    pkgs.add(pkg)
                except (PermissionError, OSError):
                    pass
    return pkgs


def scan_project(project_cfg: dict) -> dict:
    path = expand_path(project_cfg["path"])
    exists = path.exists()
    result = {
        "id": project_cfg["id"], "name": project_cfg["name"],
        "path": str(path), "exists": exists,
        "env_vars": set(), "env_files": [],
        "npm_deps": {"dependencies": set(), "devDependencies": set()},
        "pip_deps": set(),
    }
    if not exists:
        return result
    env_files = find_env_files(path)
    result["env_files"] = [str(f) for f in env_files]
    for ef in env_files:
        result["env_vars"].update(extract_env_var_names(ef))
    result["npm_deps"] = find_package_json_deps(path)
    result["pip_deps"] = find_requirements_txt_deps(path)
    return result


def match_services(scan_results: list[dict], config: dict) -> dict:
    services_cfg = config["services"]
    known_patterns = set(config["env_patterns"])
    found_services = {}
    new_env_vars = set()
    new_var_projects = {}
    all_found_vars = set()
    for proj in scan_results:
        if not proj["exists"]:
            continue
        for var in proj["env_vars"]:
            all_found_vars.add(var)
            if var in services_cfg:
                svc_name = services_cfg[var]["name"]
                if svc_name not in found_services:
                    found_services[svc_name] = {"config": services_cfg[var], "env_var": var, "projects": []}
                found_services[svc_name]["projects"].append(proj["id"])
            elif var not in known_patterns:
                new_env_vars.add(var)
                if var not in new_var_projects:
                    new_var_projects[var] = []
                new_var_projects[var].append(proj["id"])
    missing_services = {}
    for var, svc in services_cfg.items():
        if svc["name"] not in found_services and var not in all_found_vars:
            missing_services[svc["name"]] = svc
    return {"found": found_services, "new_vars": sorted(new_env_vars), "new_var_projects": new_var_projects, "missing": missing_services}


def generate_diff(current_scan: dict) -> dict:
    diff = {"new_services": [], "removed_services": [], "new_vars": [], "new_projects": [], "removed_projects": []}
    if not LAST_SCAN_PATH.exists():
        return diff
    try:
        with open(LAST_SCAN_PATH) as f:
            last = json.load(f)
    except (json.JSONDecodeError, OSError):
        return diff
    last_services = set(last.get("found_services", []))
    curr_services = set(current_scan.get("found_services", []))
    diff["new_services"] = sorted(curr_services - last_services)
    diff["removed_services"] = sorted(last_services - curr_services)
    diff["new_vars"] = sorted(set(current_scan.get("new_vars", [])) - set(last.get("new_vars", [])))
    last_projects = set(last.get("active_projects", []))
    curr_projects = set(current_scan.get("active_projects", []))
    diff["new_projects"] = sorted(curr_projects - last_projects)
    diff["removed_projects"] = sorted(last_projects - curr_projects)
    return diff


def save_scan_state(matched: dict, scan_results: list[dict]):
    state = {
        "timestamp": datetime.now().isoformat(),
        "found_services": sorted(matched["found"].keys()),
        "new_vars": matched["new_vars"],
        "active_projects": [p["id"] for p in scan_results if p["exists"]],
    }
    with open(LAST_SCAN_PATH, "w") as f:
        json.dump(state, f, indent=2)


def build_service_rows(config, matched, projects_cfg):
    rows = []
    for ghost in config.get("ghost_services", []):
        rows.append({
            "id": f"ghost-{ghost['name'].lower().replace(' ', '-').replace('/', '-')}",
            "name": ghost["name"], "type": ghost["type"], "category": ghost["category"],
            "cost_model": "ghost", "cost_estimate": ghost["cost_estimate"],
            "action": "cancel", "action_label": "CANCELAR YA", "notes": ghost["notes"],
            "env_var": "", "projects": [],
            "search": ghost.get("search_terms", ghost["name"].lower()),
        })
    for svc_name, svc_data in sorted(matched["found"].items()):
        cfg = svc_data["config"]
        rows.append({
            "id": svc_data["env_var"], "name": svc_name, "type": cfg["type"],
            "category": cfg["category"], "cost_model": cfg["cost_model"],
            "cost_estimate": cfg["cost_estimate"], "action": cfg["action"],
            "action_label": cfg["action_label"], "notes": cfg["notes"],
            "env_var": svc_data["env_var"], "projects": list(set(svc_data["projects"])),
            "search": f"{svc_name.lower()} {svc_data['env_var'].lower()}",
        })
    for extra in config.get("extra_services", []):
        proj_ids = [p["id"] for p in config["projects"]] if extra.get("all_projects") else extra.get("projects", [])
        rows.append({
            "id": f"extra-{extra['name'].lower().replace(' ', '-').replace('/', '-')}",
            "name": extra["name"], "type": extra["type"], "category": extra["category"],
            "cost_model": extra["cost_model"], "cost_estimate": extra["cost_estimate"],
            "action": extra["action"], "action_label": extra["action_label"],
            "notes": extra["notes"], "env_var": "", "projects": proj_ids,
            "search": extra.get("search_terms", extra["name"].lower()),
            "enstil": "enstil" in extra.get("search_terms", "").lower(),
        })
    for var_name in matched.get("new_vars", []):
        proj_list = matched.get("new_var_projects", {}).get(var_name, [])
        rows.append({
            "id": f"new-{var_name.lower()}", "name": var_name,
            "type": "Detectado", "category": "other",
            "cost_model": "free", "cost_estimate": "$0",
            "action": "review", "action_label": "NUEVO",
            "notes": f"Variable nueva detectada. Revisar si es un servicio pago.",
            "env_var": var_name, "projects": list(set(proj_list)),
            "search": var_name.lower(), "is_new": True,
        })
    return rows


def generate_html(config: dict, scan_results: list[dict], matched: dict, diff: dict) -> str:
    projects_cfg = {p["id"]: p for p in config["projects"]}
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    service_rows = build_service_rows(config, matched, projects_cfg)

    projects_data = []
    for proj in scan_results:
        p = projects_cfg[proj["id"]]
        projects_data.append({
            "id": p["id"], "name": p["name"], "tag_class": p["tag_class"],
            "tag_label": p["tag_label"], "description": p["description"],
            "path": proj["path"], "exists": proj["exists"],
            "client": p.get("client", "Sin cliente"),
            "billable": p.get("billable", False),
            "env_count": len(proj["env_vars"]),
            "npm_count": len(proj["npm_deps"]["dependencies"]),
            "pip_count": len(proj["pip_deps"]),
        })

    template_path = SCRIPT_DIR / "template.html"
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("<!--SCAN_DATE-->", now)
    html = html.replace("/*SCAN_DATA_JSON*/", json.dumps(service_rows, ensure_ascii=False))
    html = html.replace("/*PROJECTS_JSON*/", json.dumps(projects_data, ensure_ascii=False))
    html = html.replace("/*DIFF_JSON*/", json.dumps(diff, ensure_ascii=False))
    html = html.replace("/*NEW_VARS_JSON*/", json.dumps(matched["new_vars"], ensure_ascii=False))

    weights = {k: {pk: pv for pk, pv in v.items() if not pk.startswith("_")}
               for k, v in config.get("allocation_weights", {}).items() if not k.startswith("_")}
    html = html.replace("/*WEIGHTS_JSON*/", json.dumps(weights, ensure_ascii=False))

    feedback_path = SCRIPT_DIR / "feedback.json"
    if feedback_path.exists():
        with open(feedback_path, "r", encoding="utf-8") as f:
            fb_data = json.load(f)
        html = html.replace("/*FEEDBACK_JSON*/", json.dumps(fb_data, ensure_ascii=False))
    else:
        html = html.replace("/*FEEDBACK_JSON*/", '{"services":{}}')

    billing_js_path = SCRIPT_DIR / "billing.js"
    if billing_js_path.exists():
        with open(billing_js_path, "r", encoding="utf-8") as f:
            billing_js = f.read()
        html = html.replace("/*BILLING_JS*/", billing_js)

    return html


def main():
    config = load_config()

    print("Escaneando proyectos...")
    scan_results = []
    for proj_cfg in config["projects"]:
        path = expand_path(proj_cfg["path"])
        status = "OK" if path.exists() else "NO ENCONTRADO"
        print(f"  [{status}] {proj_cfg['name']} -> {path}")
        scan_results.append(scan_project(proj_cfg))

    print("\nDetectando servicios...")
    matched = match_services(scan_results, config)
    print(f"  Servicios conocidos encontrados: {len(matched['found'])}")
    print(f"  Variables desconocidas: {len(matched['new_vars'])}")
    if matched["new_vars"]:
        print(f"    -> {', '.join(matched['new_vars'])}")

    print("\nComparando con último scan...")
    diff = generate_diff({
        "found_services": sorted(matched["found"].keys()),
        "new_vars": matched["new_vars"],
        "active_projects": [p["id"] for p in scan_results if p["exists"]],
    })
    changes = sum(len(v) for v in diff.values() if isinstance(v, list))
    if changes:
        print(f"  Cambios detectados: {changes}")
        for k, v in diff.items():
            if v:
                print(f"    {k}: {v}")
    else:
        print("  Sin cambios desde último scan.")

    print("\nGenerando HTML...")
    html = generate_html(config, scan_results, matched, diff)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    index_path = SCRIPT_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  -> {OUTPUT_HTML}")
    print(f"  -> {index_path} (GitHub Pages)")

    save_scan_state(matched, scan_results)

    if "--open" in sys.argv:
        subprocess.run(["open", str(OUTPUT_HTML)])
        print("  Abierto en el navegador.")

    if "--diff" in sys.argv:
        if changes:
            print(f"\n{'='*50}")
            print("CAMBIOS DETECTADOS:")
            print(f"{'='*50}")
            for k, v in diff.items():
                if v:
                    print(f"  {k}: {', '.join(v)}")
        else:
            print("\nSin cambios desde el último scan.")

    print("\nListo.")


if __name__ == "__main__":
    main()
