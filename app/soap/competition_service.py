"""
Competition SOAP Service - Match session and report handling.

Endpoint: /competitionservice/competitionservice.asmx

This service handles:
- CreateSession: Creates a match session, returns csid/ccid
- SetReportIntention: Signals that a player will submit a report
- SubmitReport: Submits match report binary data

The game uses this service to track match results for ranked games.
"""

import gzip
import json
import os

from fastapi import APIRouter, Request, Response

from app.db.crud import (
    complete_competition_session,
    create_competition_session,
    set_report_intention,
    submit_match_report,
)
from app.db.database import create_session
from app.models.match_report import MatchReport
from app.soap.envelope import (
    create_soap_fault,
    extract_soap_body,
    get_child_element,
    get_element_text,
    get_operation_name,
    wrap_soap_envelope,
)
from app.soap.models.competition import (
    CreateSessionResponse,
    SetReportIntentionResponse,
    SubmitReportResponse,
)
from app.util.logging_helper import get_logger

logger = get_logger(__name__)

competition_router = APIRouter()

# Namespace definitions
COMP_NS = "http://gamespy.net/competition"


def extract_profile_id_from_certificate(operation: any) -> int:
    """
    Extract profileid from the certificate element in the operation.

    The game sends profileid inside a nested certificate element:
    <SetReportIntention>
        <certificate>
            <profileid>12345</profileid>
            ...
        </certificate>
        ...
    </SetReportIntention>

    Args:
        operation: The parsed XML operation element.

    Returns:
        The profile ID, or 0 if not found.
    """
    cert_element = get_child_element(operation, "certificate")
    if cert_element is not None:
        profile_id_str = get_element_text(cert_element, "profileid")
        if profile_id_str:
            return int(profile_id_str)
    return 0


# Directory to save match reports
REPORT_DIR = os.path.join(os.getcwd(), "Report")


def save_match_report(csid: str, ccid: str, raw_report: bytes, report: MatchReport | None) -> None:
    """
    Save match report to files (binary and parsed JSON).

    Args:
        csid: Competition Session ID (match ID).
        ccid: Competition Channel ID (player ID).
        raw_report: Raw binary report data.
        report: Parsed MatchReport object, or None if parsing failed.
    """
    try:
        os.makedirs(REPORT_DIR, exist_ok=True)

        # Save raw binary report
        bin_path = os.path.join(REPORT_DIR, f"Report_{csid}_{ccid}.bin")
        with open(bin_path, "wb") as f:
            f.write(raw_report)
        logger.info("Competition: Saved raw report to %s", bin_path)

        # Save parsed report as JSON
        if report:
            json_path = os.path.join(REPORT_DIR, f"Report_{csid}_{ccid}.json")
            report_dict = {
                "protocol_version": report.protocol_version,
                "developer_version": report.developer_version,
                "game_status": report.game_status,
                "flags": report.flags,
                "player_count": report.player_count,
                "team_count": report.team_count,
                "map_path": report.get_map_path(),
                "replay_guid": report.get_replay_guid(),
                "game_type": report.get_game_type(),
                "is_auto_match": report.is_auto_match,
                "players": [
                    {
                        "full_id": p.full_id,
                        "persona_id": p.persona_id,
                        "faction": p.faction,
                        "is_winner": p.is_winner,
                    }
                    for p in report.get_player_list()
                ],
            }
            with open(json_path, "w") as f:
                json.dump(report_dict, f, indent=2)
            logger.info("Competition: Saved parsed report to %s", json_path)

    except Exception as e:
        logger.warning("Competition: Error saving report: %s", e)


def handle_create_session(profile_id: int) -> CreateSessionResponse:
    """
    Handle CreateSession SOAP operation.

    Creates a new match session and returns csid and ccid.

    Args:
        profile_id: The profile ID creating the session.

    Returns:
        CreateSessionResponse with session IDs.
    """
    logger.debug("Competition CreateSession: profileId=%s", profile_id)

    session = create_session()
    try:
        comp_session = create_competition_session(session, profile_id)
        logger.debug(
            "Competition: Created session csid=%s, ccid=%s",
            comp_session.csid,
            comp_session.ccid,
        )
        return CreateSessionResponse.success(
            csid=comp_session.csid,
            ccid=comp_session.ccid,
        )
    finally:
        session.close()


def handle_set_report_intention(csid: str, ccid: str, profile_id: int) -> SetReportIntentionResponse:
    """
    Handle SetReportIntention SOAP operation.

    Signals that a player intends to submit a match report.

    Args:
        csid: Competition Session ID.
        ccid: Competition Channel ID.
        profile_id: The profile ID setting the intention.

    Returns:
        SetReportIntentionResponse confirming the intention.
    """
    logger.debug(
        "Competition SetReportIntention: csid=%s, ccid=%s, profileId=%s",
        csid,
        ccid,
        profile_id,
    )

    session = create_session()
    try:
        success = set_report_intention(session, csid, profile_id)
        if success:
            return SetReportIntentionResponse.success(csid=csid, ccid=ccid)
        else:
            return SetReportIntentionResponse.error()
    finally:
        session.close()


def handle_submit_report(csid: str, ccid: str, profile_id: int, raw_report: bytes) -> SubmitReportResponse:
    """
    Handle SubmitReport SOAP operation.

    Submits match report data (raw binary). Parses the report using MatchReport,
    saves both raw and parsed data to files, and stores results in the database.

    Args:
        csid: Competition Session ID.
        ccid: Competition Channel ID.
        profile_id: The profile ID submitting the report.
        raw_report: Raw binary report data.

    Returns:
        SubmitReportResponse indicating success or error.
    """
    logger.info(
        "Competition SubmitReport: csid=%s, ccid=%s, profileId=%s, report_size=%d",
        csid,
        ccid,
        profile_id,
        len(raw_report) if raw_report else 0,
    )

    report: MatchReport | None = None
    report_data: dict = {}

    # Parse the binary report
    if raw_report:
        try:
            report = MatchReport.from_bytes(raw_report)

            # Extract useful data for database storage
            player_list = report.get_player_list()
            report_data = {
                "game_type": report.get_game_type(),
                "map_path": report.get_map_path(),
                "replay_guid": report.get_replay_guid(),
                "is_auto_match": report.is_auto_match,
                "player_count": len(player_list),
                "players": [
                    {
                        "persona_id": p.persona_id,
                        "faction": p.faction,
                        "is_winner": p.is_winner,
                    }
                    for p in player_list
                ],
                "winner_ids": report.get_winner_id_list(),
                "loser_ids": report.get_loser_id_list(),
            }

            logger.info(
                "Competition: Parsed report - game_type=%s, map=%s, players=%d, is_auto_match=%s",
                report.get_game_type(),
                report.get_map_path(),
                len(player_list),
                report.is_auto_match,
            )

            # Log each player's result
            for player in player_list:
                logger.info(
                    "Competition: Player %d (%s) - faction=%s, winner=%s",
                    player.persona_id,
                    player.full_id,
                    player.faction,
                    player.is_winner,
                )

        except Exception as e:
            logger.exception("Competition: Error parsing report: %s", e)

        # Save report to files
        save_match_report(csid, ccid, raw_report, report)

    # Store in database
    session = create_session()
    try:
        submit_match_report(session, csid, ccid, profile_id, report_data)
        complete_competition_session(session, csid)
        return SubmitReportResponse.success()
    finally:
        session.close()


def extract_submit_report_data(body: bytes) -> tuple[str, str, int, bytes]:
    """
    Extract data from SubmitReport request.

    The game sends SubmitReport as XML followed by binary data:
    - XML SOAP envelope with csid, ccid, certificate
    - Marker: "application/bin\0"
    - Raw binary report data

    Args:
        body: Raw request body bytes.

    Returns:
        Tuple of (csid, ccid, profile_id, raw_report).
    """
    # Markers to find in the raw bytes
    csid_marker = b"<gsc:csid>"
    csid_end_marker = b"</gsc:csid>"
    ccid_marker = b"<gsc:ccid>"
    ccid_end_marker = b"</gsc:ccid>"
    profileid_marker = b"<gsc:profileid>"
    profileid_end_marker = b"</gsc:profileid>"
    bin_marker = b"application/bin\x00"

    # Extract csid
    csid = ""
    csid_start = body.find(csid_marker)
    if csid_start != -1:
        csid_start += len(csid_marker)
        csid_end = body.find(csid_end_marker, csid_start)
        if csid_end != -1:
            csid = body[csid_start:csid_end].decode("ascii", errors="ignore")

    # Extract ccid
    ccid = ""
    ccid_start = body.find(ccid_marker)
    if ccid_start != -1:
        ccid_start += len(ccid_marker)
        ccid_end = body.find(ccid_end_marker, ccid_start)
        if ccid_end != -1:
            ccid = body[ccid_start:ccid_end].decode("ascii", errors="ignore")

    # Extract profileid from certificate
    profile_id = 0
    profileid_start = body.find(profileid_marker)
    if profileid_start != -1:
        profileid_start += len(profileid_marker)
        profileid_end = body.find(profileid_end_marker, profileid_start)
        if profileid_end != -1:
            try:
                profile_id = int(body[profileid_start:profileid_end].decode("ascii"))
            except ValueError:
                pass

    # Extract binary report (after "application/bin\0" marker)
    raw_report = b""
    bin_pos = body.find(bin_marker)
    if bin_pos != -1:
        raw_report = body[bin_pos + len(bin_marker):]

    logger.debug(
        "Competition: Extracted SubmitReport data: csid=%s, ccid=%s, profileId=%d, report_size=%d",
        csid,
        ccid,
        profile_id,
        len(raw_report),
    )

    return csid, ccid, profile_id, raw_report


@competition_router.post("/competitionservice/competitionservice.asmx")
async def competition_handler(request: Request) -> Response:
    """
    Main handler for Competition Service SOAP requests.

    Routes requests based on SOAPAction header.
    """
    try:
        soap_action = request.headers.get("SOAPAction", "").strip('"')
        logger.debug("Competition: SOAPAction=%s", soap_action)

        body = await request.body()
        # Check for gzip compression (magic bytes 0x1f 0x8b)
        if len(body) >= 2 and body[0] == 0x1F and body[1] == 0x8B:
            body = gzip.decompress(body)

        # SubmitReport has binary data appended after XML, handle it specially
        if "SubmitReport" in soap_action:
            logger.debug("Competition: Request body (first 500 bytes)=%s", body[:500])
            csid, ccid, profile_id, raw_report = extract_submit_report_data(body)
            response_model = handle_submit_report(csid, ccid, profile_id, raw_report)
            response_xml = wrap_soap_envelope(response_model)
        else:
            # For other operations, parse as pure XML
            xml_content = body.decode("utf-8")
            logger.debug("Competition: Request body=%s", xml_content[:500])

            operation = extract_soap_body(xml_content)
            operation_name = get_operation_name(operation)
            logger.debug("Competition: Operation=%s", operation_name)

            if "CreateSession" in soap_action or operation_name == "CreateSession":
                profile_id = extract_profile_id_from_certificate(operation)
                response_model = handle_create_session(profile_id)
                response_xml = wrap_soap_envelope(response_model)

            elif "SetReportIntention" in soap_action or operation_name == "SetReportIntention":
                csid = get_element_text(operation, "csid")
                ccid = get_element_text(operation, "ccid")
                profile_id = extract_profile_id_from_certificate(operation)
                response_model = handle_set_report_intention(csid, ccid, profile_id)
                response_xml = wrap_soap_envelope(response_model)

            else:
                # Return generic success for unknown operations
                response_model = SubmitReportResponse.success()
                response_xml = wrap_soap_envelope(response_model)

        logger.debug("Competition: Response=%s", response_xml[:500])

        return Response(
            content=response_xml,
            media_type="text/xml; charset=utf-8",
        )

    except Exception as e:
        logger.exception("Competition: Error processing request: %s", e)
        fault_xml = create_soap_fault(str(e))
        return Response(
            content=fault_xml,
            media_type="text/xml; charset=utf-8",
            status_code=500,
        )
