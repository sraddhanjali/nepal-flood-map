from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Nepal CEMS Infrastructure Impact Map",
    description="Track road, bridge, airfield, and heliport damage from Copernicus Emergency Management Service activations",
    version="0.0.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

CEMS_API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"
CACHE_TTL = 3600

app.mount("/static", StaticFiles(directory="static"), name="static")

_cache = {
    "data": None,
    "timestamp": 0,
    "code": None,
    "event_time": None,
    "activation_time": None,
}


def cache_metadata() -> dict[str, Any]:
    """Return a user-facing timestamp and age for the current dataset cache."""
    if not _cache["timestamp"]:
        return {"last_updated": None, "cache_age_seconds": None}

    age = max(0, int(time.time() - _cache["timestamp"]))
    return {
        "last_updated": datetime.fromtimestamp(
            _cache["timestamp"], tz=timezone.utc
        ).isoformat(),
        "cache_age_seconds": age,
        "event_time": _cache["event_time"],
        "activation_time": _cache["activation_time"],
    }


@app.get("/health", tags=["health"])
def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "service": "nepal-cems-infrastructure-api"}


@app.get("/", tags=["web"])
def index():
    """Serve the main HTML interface."""
    return FileResponse("static/index.html")


async def fetch_activation(code: str) -> dict[str, Any]:
    """Fetch activation from CEMS API."""
    code = code.upper().strip()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(CEMS_API, params={"code": code})
            r.raise_for_status()
            data = r.json()
        
        results = data.get("results", [])
        if not results:
            raise HTTPException(status_code=404, detail=f"Activation {code} not found")
        
        logger.info(f"Fetched activation {code}")
        return results[0]
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching activation {code}")
        raise HTTPException(status_code=504, detail="CEMS API timeout")
    except httpx.HTTPError as e:
        logger.error(f"Error fetching activation {code}: {e}")
        raise HTTPException(status_code=502, detail="CEMS API error")


async def fetch_layer_geojson(json_url: str) -> dict[str, Any]:
    """Fetch GeoJSON from layer URL."""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(json_url)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning(f"Error fetching layer {json_url}: {e}")
        return {"type": "FeatureCollection", "features": []}


async def load_infrastructure_data(code: str = "EMSR927") -> tuple[list[Any], bool]:
    """Load and cache infrastructure data. Cache expires after one hour.
    
    Returns:
        Tuple of (features, is_cached)
    """
    global _cache
    
    current_time = time.time()
    if (_cache["data"] is not None and 
        _cache["code"] == code and 
        (current_time - _cache["timestamp"]) < CACHE_TTL):
        logger.info(f"Using cached infrastructure data for {code} (age: {int(current_time - _cache['timestamp'])}s)")
        return _cache["data"], True
    
    logger.info(f"Fetching fresh infrastructure data for {code}")
    
    try:
        act = await fetch_activation(code)
    except HTTPException:
        raise
    
    all_features = []
    aois = act.get("aois", []) or []
    
    for aoi in aois:
        if not isinstance(aoi, dict):
            continue
        
        products = aoi.get("products", []) or []
        for product in products:
            if not isinstance(product, dict):
                continue
            
            layers = product.get("layers", []) or []
            for layer in layers:
                if not isinstance(layer, dict):
                    continue
                
                layer_name = layer.get("name", "").lower()
                json_url = layer.get("json")
                
                if not json_url:
                    continue
                
                if "transportation" not in layer_name and "facilities" not in layer_name:
                    continue
                
                geojson = await fetch_layer_geojson(json_url)
                features = geojson.get("features", []) or []
                
                for feature in features:
                    if not isinstance(feature, dict) or feature.get("type") != "Feature":
                        continue
                    
                    if not feature.get("geometry"):
                        continue
                    
                    props = feature.get("properties", {}) or {}
                    
                    feature["_aoi"] = aoi.get("name", f"AOI {aoi.get('number', '?')}")
                    feature["_source"] = layer_name
                    feature["_normalized"] = {
                        "name": str(props.get("name", "")).lower(),
                        "type": str(props.get("obj_type", "")).lower(),
                        "info": str(props.get("info", "")).lower(),
                        "damage": str(props.get("damage_gra", "")).lower(),
                        "simplified": str(props.get("simplified", "")).lower(),
                    }
                    
                    all_features.append(feature)
    
    _cache["data"] = all_features
    _cache["timestamp"] = current_time
    _cache["code"] = code
    _cache["event_time"] = act.get("eventTime")
    _cache["activation_time"] = act.get("activationTime")
    
    logger.info(f"Cached {len(all_features)} infrastructure features for {code}")
    return all_features, False


@app.get("/api/infrastructure/search", tags=["api"])
async def search_infrastructure(
    code: str = Query("EMSR927"),
    q: str = Query("", max_length=200),
    infra_type: str | None = Query(None),
    grading: str | None = Query(None),
):
    """Search infrastructure features from CEMS data.
    
    Query parameters:
    - code: EMSR code (default EMSR927)
    - q: Text search (name, type, damage status)
    - infra_type: Filter by infrastructure type
    - grading: Filter by damage grading
    
    Data is cached for one hour.
    """
    
    try:
        all_features, is_cached = await load_infrastructure_data(code)
    except HTTPException:
        raise
    
    q_lower = q.lower().strip() if q else ""
    infra_type_lower = infra_type.lower().strip() if infra_type else ""
    grading_lower = grading.lower().strip() if grading else ""
    
    filtered = []
    for feature in all_features:
        props = feature.get("properties", {}) or {}
        normalized = feature.get("_normalized", {})
        
        if infra_type_lower:
            type_match = (
                infra_type_lower in normalized.get("type", "") or
                infra_type_lower in normalized.get("simplified", "") or
                infra_type_lower in normalized.get("info", "")
            )
            if not type_match:
                continue
        
        if q_lower:
            search_text = (
                f"{normalized.get('name', '')} {normalized.get('type', '')} "
                f"{normalized.get('info', '')} {normalized.get('damage', '')}"
            )
            if q_lower not in search_text:
                continue
        
        if grading_lower:
            if grading_lower not in normalized.get("damage", ""):
                continue
        
        feature["display_name"] = props.get("name", "Unnamed")
        feature["display_type"] = props.get("obj_type", "Feature")
        feature["damage_grade"] = props.get("damage_gra", "Not assessed")
        feature["aoi"] = feature.get("_aoi", "")
        
        filtered.append(feature)
    
    logger.info(f"Infrastructure search: code={code}, q={q}, type={infra_type}, grading={grading}, results={len(filtered)}, cached={is_cached}")
    
    return {
        "code": code,
        "cached": is_cached,
        **cache_metadata(),
        "query": {
            "text": q,
            "type": infra_type,
            "grading": grading,
        },
        "count": len(filtered),
        "features": filtered[:1000],
    }


@app.get("/api/infrastructure/summary", tags=["api"])
async def infrastructure_summary(code: str = Query("EMSR927")):
    """Get summary statistics of infrastructure by type and damage.
    
    Data is cached for one hour.
    """
    
    try:
        all_features, is_cached = await load_infrastructure_data(code)
    except HTTPException:
        raise
    
    summary = {
        category: {"total": 0, "destroyed": 0, "damaged": 0, "possibly_damaged": 0, "no_damage": 0}
        for category in ("roads", "bridges", "power_plants", "hospitals", "airfields", "heliports")
    }
    
    for feature in all_features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            continue
        
        props = feature.get("properties", {}) or {}
        obj_type = str(props.get("obj_type", "")).lower()
        damage = str(props.get("damage_gra", "")).lower()
        
        category = None
        if "road" in obj_type or "highway" in obj_type or "cart track" in obj_type:
            category = "roads"
        elif "bridge" in obj_type or "elevated highway" in obj_type:
            category = "bridges"
        elif "power" in obj_type or "hydro" in obj_type or "dam" in obj_type:
            category = "power_plants"
        elif "hospital" in obj_type or "medical" in obj_type:
            category = "hospitals"
        elif "airfield" in obj_type or "airport" in obj_type:
            category = "airfields"
        elif "heliport" in obj_type or "helipad" in obj_type:
            category = "heliports"
        
        if category:
            summary[category]["total"] += 1
            
            if "destroyed" in damage:
                summary[category]["destroyed"] += 1
            elif "possibly damaged" in damage:
                summary[category]["possibly_damaged"] += 1
            elif "damaged" in damage:
                summary[category]["damaged"] += 1
            elif "no" in damage:
                summary[category]["no_damage"] += 1
    
    logger.info(f"Infrastructure summary: code={code}, total={len(all_features)}, cached={is_cached}")
    
    return {
        "code": code,
        "cached": is_cached,
        **cache_metadata(),
        "activation_name": "Flood in Nepal",
        "total_features": len(all_features),
        "summary": summary,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
