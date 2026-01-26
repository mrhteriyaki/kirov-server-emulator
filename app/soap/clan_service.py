"""
Clan Service - Stub endpoints for clan functionality.

These endpoints are called by the game but we return empty/default responses.
"""

import os

from fastapi import APIRouter, Response

from app.soap.models.clan import ClanInfo
from app.util.logging_helper import get_logger
from app.util.paths import get_base_path

logger = get_logger(__name__)

clan_router = APIRouter()


def to_xml_response(model) -> str:
    """Convert a pydantic_xml model to XML string with declaration."""
    return '<?xml version="1.0" encoding="utf-8"?>' + model.to_xml(encoding="unicode")


@clan_router.get("/clans/ClanActions.asmx/ClanInfoByProfileID")
async def clan_info_by_profile_id(authToken: str = "", profileid: int = 0):
    """
    Returns clan info for a profile. Returns empty response (no clan).
    """
    logger.debug(
        "ClanInfoByProfileID: authToken=%s..., profileid=%s",
        authToken[:20] if authToken else "",
        profileid,
    )

    response_model = ClanInfo.no_clan()

    return Response(
        content=to_xml_response(response_model),
        media_type="text/xml; charset=utf-8",
    )


@clan_router.get("/GetPlayerLadderRatings.aspx")
async def get_player_ladder_ratings(gp: str = ""):
    """
    Returns ladder ratings for a player in CSV format.
    Format: statID,value,rank,elo,statID,value,rank,elo,...

    Reference stat IDs from C&C:Online:
    - 72587-72743, 75643, 75677-75686: Various game stats (value=1, rank/elo=-1)
    - 58938: RA3 1v1 ladder (value=32034 base, rank/elo from ladder)
    - 58940: Corona 1v1 ladder (value=1088 base, rank/elo from ladder)
    """
    logger.debug("GetPlayerLadderRatings: gp=%s...", gp[:20] if gp else "")

    # Default ratings (not ranked = -1)
    default_rank = -1
    default_elo = 1000

    # Build CSV response matching C&C:Online format
    # Format: statID,value,rank,elo (repeated)
    ratings = [
        # Static stat entries (always value=1, rank/elo=-1)
        "72587,1,-1,-1",
        "72743,1,-1,-1",
        "75643,1,-1,-1",
        "75677,1,-1,-1",
        "75679,1,-1,-1",
        "75680,1,-1,-1",
        "75681,1,-1,-1",
        "75682,1,-1,-1",
        "75683,1,-1,-1",
        "75684,1,-1,-1",
        "75685,1,-1,-1",
        "75686,1,-1,-1",
        # RA3 v1.12 AutoMatch 1v1 ladder
        f"58938,32034,{default_rank},{default_elo}",
        # Corona AutoMatch 1v1 ladder
        f"58940,1088,{default_rank},{default_elo}",
    ]

    response_content = ",".join(ratings) + ","

    return Response(
        content=response_content,
        media_type="text/html",
    )


@clan_router.get("/GetPlayerRankIcon.aspx")
async def get_player_rank_icon(gp: str = "", pid: int = 0, size: str = ""):
    """
    Returns the rank icon for a player as a PNG image.
    gp is the login ticket (base64 encoded userID|profileID|token).
    pid is the profile ID.
    size is optional - "L" for large icon, otherwise returns small icon.
    """
    logger.debug("GetPlayerRankIcon: gp=%s..., pid=%s, size=%s", gp[:20] if gp else "", pid, size)

    # Return large or small icon based on size parameter
    if size == "L":
        image_name = "rank_icon_large.png"
    else:
        image_name = "rank_icon_small.png"

    image_path = os.path.join(get_base_path(), "static", "images", image_name)

    with open(image_path, "rb") as f:
        image_data = f.read()

    return Response(
        content=image_data,
        media_type="image/png",
        headers={"Content-Length": str(len(image_data))},
    )
