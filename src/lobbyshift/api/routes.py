"""HTTP API. Everything except /api/health and /api/auth/* requires auth."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from .. import __version__
from ..auth import COOKIE_NAME, SESSION_TTL, Auth
from ..providers import proton
from ..service import LobbyShift, ServiceError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def get_service(request: Request) -> LobbyShift:
    return request.app.state.service


def get_auth(request: Request) -> Auth:
    return request.app.state.auth


def require_auth(request: Request, auth: Annotated[Auth, Depends(get_auth)]) -> None:
    if auth.valid_session(request.cookies.get(COOKIE_NAME)):
        return
    if auth.valid_token(request.headers.get("authorization")):
        return
    raise HTTPException(status_code=401, detail="Authentication required")


Service = Annotated[LobbyShift, Depends(get_service)]

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


# ----------------------------------------------------------------- models

class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordBody(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(min_length=8, max_length=256)


class ConfigText(BaseModel):
    text: str = Field(min_length=1, max_length=64 * 1024)


class ConfigPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    favorite: bool | None = None


class PrefsPatch(BaseModel):
    autostart: bool | None = None
    autostart_config: str | None = Field(default=None, max_length=64)
    kill_switch: bool | None = None
    auto_reconnect: bool | None = None


class Device(BaseModel):
    ip: str = Field(max_length=15)
    name: str = Field(default="", max_length=64)


class DevicesBody(BaseModel):
    devices: list[Device] = Field(max_length=64)


class LatencyBody(BaseModel):
    names: list[str] | None = None


# ------------------------------------------------------------------ public

@public.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


@public.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response,
          auth: Annotated[Auth, Depends(get_auth)]) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    try:
        session = auth.login(body.password, client)
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    if not session:
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(COOKIE_NAME, session, max_age=SESSION_TTL, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https", path="/")
    return {"authenticated": True}


@public.post("/auth/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}


@public.get("/auth/me")
def me(request: Request, auth: Annotated[Auth, Depends(get_auth)]) -> dict[str, Any]:
    ok = auth.valid_session(request.cookies.get(COOKIE_NAME)) or auth.valid_token(
        request.headers.get("authorization"))
    return {"authenticated": ok, "version": __version__}


# --------------------------------------------------------------- protected

@router.put("/auth/password")
def change_password(body: PasswordBody, request: Request, response: Response,
                    auth: Annotated[Auth, Depends(get_auth)]) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    if not auth.login(body.current, client):
        raise HTTPException(status_code=403, detail="Current password is wrong")
    auth.set_password(body.new)
    request.app.state.initial_password_file.unlink(missing_ok=True)
    # The secret rotated: issue a fresh cookie for this browser.
    session = auth.login(body.new, client)
    response.set_cookie(COOKIE_NAME, session or "", max_age=SESSION_TTL, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https", path="/")
    return {"message": "Password changed"}


@router.get("/status")
async def status(svc: Service) -> dict[str, Any]:
    return await svc.status()


@router.post("/tunnel/up")
async def tunnel_up(svc: Service) -> dict[str, Any]:
    return {"config": await svc.up()}


@router.post("/tunnel/down")
async def tunnel_down(svc: Service) -> dict[str, Any]:
    await svc.disconnect()
    return {"message": "Disconnected"}


@router.post("/tunnel/connect/{name}")
async def tunnel_connect(name: str, svc: Service) -> dict[str, Any]:
    return {"config": await svc.connect(name)}


@router.get("/configs")
def list_configs(svc: Service) -> dict[str, Any]:
    return {"configs": svc.list_configs()}


@router.post("/configs")
async def upload_configs(svc: Service,
                         files: Annotated[list[UploadFile], File()]) -> dict[str, Any]:
    imported: list[dict] = []
    errors: list[dict] = []
    for upload in files[:50]:
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        name = upload.filename or "config.conf"
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append({"file": name, "error": "File is too large"})
            continue
        try:
            result = await svc.import_upload(name, data)
        except ServiceError as e:
            errors.append({"file": name, "error": str(e)})
            continue
        imported += result["imported"]
        errors += result["errors"]
    if not imported and errors:
        raise HTTPException(status_code=400, detail={"message": "Nothing imported", "errors": errors})
    return {"imported": imported, "errors": errors}


@router.get("/configs/{name}")
def get_config(name: str, svc: Service) -> dict[str, Any]:
    return {**svc.get_config(name), "text": svc.get_config_text(name)}


@router.put("/configs/{name}/text")
async def put_config_text(name: str, body: ConfigText, svc: Service) -> dict[str, Any]:
    return await svc.update_config_text(name, body.text)


@router.patch("/configs/{name}")
def patch_config(name: str, body: ConfigPatch, svc: Service) -> dict[str, Any]:
    return svc.update_config_fields(name, display_name=body.display_name, favorite=body.favorite)


@router.delete("/configs/{name}")
async def delete_config(name: str, svc: Service) -> dict[str, Any]:
    await svc.delete_config(name)
    return {"message": "Deleted"}


@router.post("/latency")
async def latency(body: LatencyBody, svc: Service) -> dict[str, Any]:
    return {"configs": await svc.measure_latency(body.names)}


@router.get("/events")
def events(svc: Service, limit: int = 50) -> dict[str, Any]:
    return {"events": svc.store.list_events(max(1, min(limit, 500)))}


@router.delete("/events")
def clear_events(svc: Service) -> dict[str, Any]:
    svc.store.clear_events()
    return {"message": "Cleared"}


@router.get("/settings")
def get_settings(svc: Service) -> dict[str, Any]:
    return {
        "prefs": svc.prefs(),
        "devices": svc.devices(),
        "routed_ranges": list(svc.settings.routed_ranges),
        "lan": svc.lan.__dict__ if svc.lan else None,
    }


@router.put("/settings/prefs")
async def put_prefs(body: PrefsPatch, svc: Service) -> dict[str, Any]:
    return {"prefs": await svc.update_prefs(body.model_dump(exclude_none=True))}


@router.put("/settings/devices")
async def put_devices(body: DevicesBody, svc: Service) -> dict[str, Any]:
    return {"devices": await svc.set_devices([d.model_dump() for d in body.devices])}


@router.get("/system/doctor")
async def doctor(svc: Service) -> dict[str, Any]:
    checks = await svc.doctor()
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


@router.post("/system/geoip/update")
async def geoip_update(svc: Service) -> dict[str, Any]:
    return {"updated": await svc.update_geoip(), "available": svc.geoip.available}


@router.get("/providers/proton")
def proton_info(svc: Service) -> dict[str, Any]:
    configs = [c for c in svc.list_configs() if c["provider"] == proton.PROVIDER]
    return {
        "account_url": proton.ACCOUNT_URL,
        "recommended": {
            "platform": "Router",
            "netshield": "Off",
            "moderate_nat": "On",
            "vpn_accelerator": "On",
            "port_forwarding": "Off",
            "secure_core": "Off",
        },
        "configs": len(configs),
        "countries": sorted({c["country"]["code"] for c in configs}),
    }
