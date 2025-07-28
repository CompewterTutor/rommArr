from config import (
    DISABLE_EMULATOR_JS,
    DISABLE_RUFFLE_RS,
    DISABLE_USERPASS_LOGIN,
    HASHEOUS_API_ENABLED,
    LAUNCHBOX_API_ENABLED,
    OIDC_ENABLED,
    OIDC_PROVIDER,
    PLAYMATCH_API_ENABLED,
    TGDB_API_ENABLED,
    UPLOAD_TIMEOUT,
    YOUTUBE_BASE_URL,
)
from endpoints.responses.heartbeat import HeartbeatResponse
from handler.database import db_user_handler
from handler.filesystem import fs_platform_handler
from handler.metadata.igdb_handler import IGDB_API_ENABLED
from handler.metadata.moby_handler import MOBY_API_ENABLED
from handler.metadata.ra_handler import RA_API_ENABLED
from handler.metadata.sgdb_handler import STEAMGRIDDB_API_ENABLED
from handler.metadata.ss_handler import SS_API_ENABLED
from utils import get_version
from utils.router import APIRouter

router = APIRouter(
    tags=["system"],
)


@router.get("/heartbeat")
async def heartbeat() -> HeartbeatResponse:
    """Endpoint to set the CSRF token in cache and return all the basic RomM config

    Returns:
        HeartbeatReturn: TypedDict structure with all the defined values in the HeartbeatReturn class.
    """

    return {
        "SYSTEM": {
            "VERSION": get_version(),
            "SHOW_SETUP_WIZARD": len(db_user_handler.get_admin_users()) == 0,
        },
        "METADATA_SOURCES": {
            "ANY_SOURCE_ENABLED": IGDB_API_ENABLED
            or SS_API_ENABLED
            or MOBY_API_ENABLED
            or RA_API_ENABLED
            or LAUNCHBOX_API_ENABLED
            or HASHEOUS_API_ENABLED
            or TGDB_API_ENABLED,
            "IGDB_API_ENABLED": IGDB_API_ENABLED,
            "SS_API_ENABLED": SS_API_ENABLED,
            "MOBY_API_ENABLED": MOBY_API_ENABLED,
            "STEAMGRIDDB_API_ENABLED": STEAMGRIDDB_API_ENABLED,
            "RA_API_ENABLED": RA_API_ENABLED,
            "LAUNCHBOX_API_ENABLED": LAUNCHBOX_API_ENABLED,
            "HASHEOUS_API_ENABLED": HASHEOUS_API_ENABLED,
            "PLAYMATCH_API_ENABLED": PLAYMATCH_API_ENABLED,
            "TGDB_API_ENABLED": TGDB_API_ENABLED,
        },
        "FILESYSTEM": {
            "FS_PLATFORMS": await fs_platform_handler.get_platforms(),
        },
        "EMULATION": {
            "DISABLE_EMULATOR_JS": DISABLE_EMULATOR_JS,
            "DISABLE_RUFFLE_RS": DISABLE_RUFFLE_RS,
        },
        "FRONTEND": {
            "UPLOAD_TIMEOUT": UPLOAD_TIMEOUT,
            "DISABLE_USERPASS_LOGIN": DISABLE_USERPASS_LOGIN,
            "YOUTUBE_BASE_URL": YOUTUBE_BASE_URL,
        },
        "OIDC": {
            "ENABLED": OIDC_ENABLED,
            "PROVIDER": OIDC_PROVIDER,
        },
    }
