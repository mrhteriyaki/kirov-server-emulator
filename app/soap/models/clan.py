"""
Pydantic-XML models for Clan Service.

Endpoint: /clans/ClanActions.asmx/*
Namespace: http://gamespy.net

Note: These are simple XML responses (not SOAP envelopes).
"""

from pydantic_xml import BaseXmlModel, element

CLAN_NS = "http://gamespy.net"
CLAN_NSMAP = {
    "": CLAN_NS,
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xsd": "http://www.w3.org/2001/XMLSchema",
}


class ClanInfo(BaseXmlModel, tag="ClanInfo", nsmap=CLAN_NSMAP):
    """Response model for ClanInfoByProfileID."""

    clan_id: int = element(tag="ClanID", default=0)
    clan_name: str = element(tag="ClanName", default="")
    clan_tag: str = element(tag="ClanTag", default="")

    @classmethod
    def no_clan(cls) -> "ClanInfo":
        """Create a response indicating no clan membership."""
        return cls(clan_id=0, clan_name="", clan_tag="")


class LadderRatings(BaseXmlModel, tag="LadderRatings", nsmap=CLAN_NSMAP):
    """Response model for GetPlayerLadderRatings."""

    ratings: str = element(tag="Ratings", default="1500,1500,1500,1500")

    @classmethod
    def default(cls) -> "LadderRatings":
        """Create a response with default ratings (1500 for all ladders)."""
        return cls(ratings="1500,1500,1500,1500")
