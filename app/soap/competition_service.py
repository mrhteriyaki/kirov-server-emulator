"""
Competition SOAP Service - Match session and report handling.

Endpoint: /competitionservice/competitionservice.asmx

This service handles:
- CreateSession: Creates a match session, returns csid/ccid
- SetReportIntention: Signals that a player will submit a report
- SubmitReport: Submits match report binary data

The game uses this service to track match results for ranked games.
"""

import base64
import struct

from fastapi import APIRouter, Request, Response

from app.db.crud import (
    complete_competition_session,
    create_competition_session,
    set_report_intention,
    submit_match_report,
)
from app.db.database import create_session
from app.soap.envelope import (
    create_soap_fault,
    extract_soap_body,
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


def parse_match_report(report_data: bytes) -> dict:
    """
    Parse binary match report data.

    The report format is game-specific. This is a basic parser that
    extracts common fields.

    Returns:
        Dictionary with parsed report fields.
    """
    result = {
        "result": 0,  # 0=Win, 1=Loss, 3=DC
        "faction": "",
        "duration": 0,
        "gametype": 0,
        "map_name": "",
    }

    try:
        if len(report_data) < 8:
            return result

        if len(report_data) >= 4:
            result["result"] = struct.unpack("<I", report_data[0:4])[0] & 0x3

        if len(report_data) >= 8:
            result["duration"] = struct.unpack("<I", report_data[4:8])[0]

        if len(report_data) >= 12:
            result["gametype"] = struct.unpack("<I", report_data[8:12])[0] & 0xF

    except Exception as e:
        logger.warning("Competition: Error parsing report: %s", e)

    return result


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


def handle_submit_report(csid: str, ccid: str, profile_id: int, report_b64: str) -> SubmitReportResponse:
    """
    Handle SubmitReport SOAP operation.

    Submits match report data (base64 encoded).

    Args:
        csid: Competition Session ID.
        ccid: Competition Channel ID.
        profile_id: The profile ID submitting the report.
        report_b64: Base64 encoded report data.

    Returns:
        SubmitReportResponse indicating success or error.
    """
    logger.debug(
        "Competition SubmitReport: csid=%s, ccid=%s, profileId=%s",
        csid,
        ccid,
        profile_id,
    )

    session = create_session()
    try:
        report_data = {}
        if report_b64:
            try:
                report_bytes = base64.b64decode(report_b64)
                report_data = parse_match_report(report_bytes)
                logger.debug("Competition: Parsed report: %s", report_data)
            except Exception as e:
                logger.warning("Competition: Error decoding report: %s", e)

        submit_match_report(session, csid, ccid, profile_id, report_data)
        complete_competition_session(session, csid)

        return SubmitReportResponse.success()
    finally:
        session.close()


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
        xml_content = body.decode("utf-8")
        logger.debug("Competition: Request body=%s", xml_content[:500])

        operation = extract_soap_body(xml_content)
        operation_name = get_operation_name(operation)
        logger.debug("Competition: Operation=%s", operation_name)

        if "CreateSession" in soap_action or operation_name == "CreateSession":
            profile_id_str = get_element_text(operation, "profileId")
            profile_id = int(profile_id_str) if profile_id_str else 0
            response_model = handle_create_session(profile_id)
            response_xml = wrap_soap_envelope(response_model)

        elif "SetReportIntention" in soap_action or operation_name == "SetReportIntention":
            csid = get_element_text(operation, "csid")
            ccid = get_element_text(operation, "ccid")
            profile_id_str = get_element_text(operation, "profileId")
            profile_id = int(profile_id_str) if profile_id_str else 0
            response_model = handle_set_report_intention(csid, ccid, profile_id)
            response_xml = wrap_soap_envelope(response_model)

        elif "SubmitReport" in soap_action or operation_name == "SubmitReport":
            csid = get_element_text(operation, "csid")
            ccid = get_element_text(operation, "ccid")
            profile_id_str = get_element_text(operation, "profileId")
            profile_id = int(profile_id_str) if profile_id_str else 0
            report_b64 = get_element_text(operation, "report")
            response_model = handle_submit_report(csid, ccid, profile_id, report_b64)
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
