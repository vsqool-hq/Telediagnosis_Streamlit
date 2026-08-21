"""Router panelu Ustawienia — edycja konfiguracji silnika."""

import io

from fastapi import APIRouter, HTTPException, UploadFile, File

from app import db
from app.engine.config import DEFAULT_CONFIG

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings():
    return {"settings": db.get_settings(), "defaults": DEFAULT_CONFIG}


@router.put("")
async def update_settings(payload: dict):
    cfg = payload.get("settings", payload)
    if not isinstance(cfg, dict):
        raise HTTPException(400, "Nieprawidłowy format konfiguracji.")
    # Walidacja kluczowych pól liczbowych (num_processes: 0 = Auto)
    if "num_processes" in cfg:
        try:
            cfg["num_processes"] = max(0, int(cfg["num_processes"]))
        except (ValueError, TypeError):
            raise HTTPException(400, "Pole num_processes musi być liczbą całkowitą (0 = Auto).")
        # Zgodność wstecz: utrzymuj jedno źródło prawdy dla obu etapów.
        cfg["num_processes_verify"] = cfg["num_processes"] or 1
        cfg["num_processes_billing"] = cfg["num_processes"] or 1
    for key in ("num_processes_verify", "num_processes_billing"):
        if key in cfg:
            try:
                cfg[key] = max(1, int(cfg[key]))
            except (ValueError, TypeError):
                raise HTTPException(400, f"Pole {key} musi być liczbą całkowitą.")
    # Grupy jednostek: lista {name, units:[...]} — odrzucamy puste nazwy/jednostki.
    if "unit_groups" in cfg:
        groups = cfg["unit_groups"]
        if not isinstance(groups, list):
            raise HTTPException(400, "Pole unit_groups musi być listą grup.")
        clean = []
        for g in groups:
            if not isinstance(g, dict):
                continue
            name = str(g.get("name", "")).strip()
            units = [str(u).strip() for u in (g.get("units") or []) if str(u).strip()]
            if name and units:
                clean.append({"name": name, "units": units})
        cfg["unit_groups"] = clean
    # Scalanie jednostek: mapa {podległa: główna} — odrzucamy puste i samopętle.
    if "unit_aliases" in cfg:
        cfg["unit_aliases"] = _clean_aliases(cfg["unit_aliases"])
    # Konsultacje: grupy (konsultujący → opisujący [+ opcjonalna stawka grupy]).
    if "consult_groups" in cfg:
        cfg["consult_groups"] = _clean_consult_groups(cfg["consult_groups"])
    db.save_settings(cfg)
    return {"ok": True, "settings": cfg}


def _clean_aliases(raw) -> dict:
    if not isinstance(raw, dict):
        raise HTTPException(400, "Pole unit_aliases musi być obiektem {podległa: główna}.")
    clean = {}
    for src, tgt in raw.items():
        s = str(src or "").strip()
        t = str(tgt or "").strip()
        if s and t and s.lower() != t.lower():   # bez pustych i bez „X → X"
            clean[s] = t
    return clean


@router.get("/unit-aliases")
async def get_unit_aliases():
    """Mapa scalania jednostek {podległa: główna}. Dedykowany endpoint dla panelu
    (samodzielny — nie rusza reszty ustawień)."""
    cfg = db.get_settings()
    return {"aliases": cfg.get("unit_aliases") or {}}


@router.put("/unit-aliases")
async def save_unit_aliases(payload: dict):
    cfg = db.get_settings()
    cfg["unit_aliases"] = _clean_aliases(payload.get("aliases", payload))
    db.save_settings(cfg)
    return {"aliases": cfg["unit_aliases"]}


def _clean_consult_groups(raw) -> list:
    if not isinstance(raw, list):
        raise HTTPException(400, "Pole consult_groups musi być listą grup.")
    clean = []
    for g in raw:
        if not isinstance(g, dict):
            continue
        kons = str(g.get("konsultujacy", "")).strip()
        opis = [str(o).strip() for o in (g.get("opisujacy") or []) if str(o).strip()]
        if not (kons and opis):
            continue
        entry = {"konsultujacy": kons, "opisujacy": opis}
        # Opcjonalna stawka grupy: gdy podana (>0) → para dostaje TĘ stawkę zamiast 50%.
        rate = g.get("stawka", None)
        try:
            r = float(rate) if rate is not None and str(rate).strip() != "" else None
        except (TypeError, ValueError):
            r = None
        if r is not None and r > 0:
            entry["stawka"] = r
        clean.append(entry)
    return clean


@router.get("/consult-config")
async def get_consult_config():
    """Konfiguracja dopłat za konsultacje: grupy (konsultujący → opisujący [+ stawka])."""
    cfg = db.get_settings()
    return {"groups": cfg.get("consult_groups") or []}


@router.put("/consult-config")
async def save_consult_config(payload: dict):
    cfg = db.get_settings()
    if "groups" in payload:
        cfg["consult_groups"] = _clean_consult_groups(payload["groups"])
    db.save_settings(cfg)
    return {"groups": cfg.get("consult_groups") or []}


@router.post("/reset")
async def reset_settings():
    db.save_settings(dict(DEFAULT_CONFIG))
    return {"ok": True, "settings": DEFAULT_CONFIG}


@router.post("/adjustments/reseed")
async def reseed_adjustments():
    """Przywraca współczynniki cen jednostek z pliku startowego (seed_data/unit_adjustments.json),
    nadpisując bieżące. Pozostałe ustawienia bez zmian."""
    from app.seed import load_seed_adjustments
    seed = load_seed_adjustments()
    if not seed:
        raise HTTPException(404, "Brak pliku startowego ze współczynnikami.")
    cfg = db.get_settings()
    cfg["unit_adjustments"] = seed
    db.save_settings(cfg)
    return {"ok": True, "unit_adjustments": seed}


def _active_cennik_rows():
    """Wiersze aktywnego cennika jako (jednostka, BADANIE, cena_str). [] gdy brak."""
    import os
    import csv
    from app.storage import version_dir
    active = db.get_active_version("cennik")
    if not active:
        return []
    path = os.path.join(version_dir("cennik", active["id"]), active["filename"])
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8-sig") as f:
            rd = csv.reader(f, delimiter=";")
            next(rd, None)  # nagłówek BADANIE;Jednostka;Cena
            for r in rd:
                if len(r) >= 3:
                    rows.append((r[1].strip(), r[0].strip(), r[2].strip()))
    return rows


@router.post("/adjustments/generate")
async def generate_adjustments_from_file(file: UploadFile = File(...)):
    """PROPOZYCJA uzupełnień cen z pliku ZOBOWIĄZANIA SZPITALE — TYLKO luki (stawki
    pochodne z ostatniego aneksu, których BRAK w aktualnym cenniku). Formuła baza×k →
    współczynnik; literał → dodanie do cennika. Nic nie zapisuje — zwraca propozycję
    do zatwierdzenia (współczynniki przez PUT /api/settings, dodania przez
    POST /api/cennik/apply-additions)."""
    from app.engine.adjustments_gen import generate_adjustments
    content = await file.read()
    try:
        result = generate_adjustments(io.BytesIO(content), _active_cennik_rows())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Nie udało się odczytać pliku: {e}")
    result["current"] = db.get_settings().get("unit_adjustments", {}) or {}
    return result


@router.get("/adjustments/redundant")
async def adjustments_redundant():
    """Zwraca współczynniki, które aktualny cennik POKRYWA już wprost (cena > 0) — do
    wyszarzenia w interfejsie (są uśpione: w resolve_unit_price wygrywa cena z cennika)."""
    from app.engine.adjustments_gen import _cmp, _unorm
    per_unit = {}
    for unit, bad, cena in _active_cennik_rows():
        try:
            c = float(str(cena).replace(",", "."))
        except (TypeError, ValueError):
            c = 0.0
        if c > 0:
            per_unit.setdefault(_unorm(unit), set()).add(_cmp(bad))
    adj = db.get_settings().get("unit_adjustments", {}) or {}
    covered = [{"unit": unit, "key": key}
               for unit, rules in adj.items()
               for key in rules
               if _cmp(key) in per_unit.get(_unorm(unit), set())]
    return {"redundant": covered}
