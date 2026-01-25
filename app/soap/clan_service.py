"""
Clan Service - Stub endpoints for clan functionality.

These endpoints are called by the game but we return empty/default responses.
"""

from fastapi import APIRouter, Response

from app.soap.models.clan import ClanInfo, LadderRatings
from app.util.logging_helper import get_logger

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
    Returns ladder ratings for a player. Returns default ratings.
    """
    logger.debug("GetPlayerLadderRatings: gp=%s...", gp[:20] if gp else "")

    response_model = LadderRatings.default()

    return Response(
        content=to_xml_response(response_model),
        media_type="text/xml; charset=utf-8",
    )
