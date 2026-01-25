"""
Auth SOAP Service - Certificate management for RA3.

Endpoint: /AuthService/AuthService.asmx

This service handles:
- LoginRemoteAuth: Allocates a certificate from the pool for authentication

Certificates have a 180-second expiry and are returned to the pool after use.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Response

from app.db.crud import get_available_certificate
from app.db.database import create_session
from app.soap.envelope import (
    create_soap_fault,
    extract_soap_body,
    get_element_text,
    get_operation_name,
    wrap_soap_envelope,
)
from app.soap.models.auth import LoginRemoteAuthResponse
from app.util.logging_helper import get_logger

logger = get_logger(__name__)

auth_router = APIRouter()

# Namespace definitions
AUTH_NS = "http://gamespy.net/AuthService"

# Certificate expiry time in seconds
CERT_EXPIRY_SECONDS = 180


def handle_login_remote_auth(server_data: str, profile_id: int) -> LoginRemoteAuthResponse:
    """
    Handle LoginRemoteAuth SOAP operation.

    Allocates a certificate from the pool and returns it.
    If no certificates are available, returns a placeholder certificate.

    Args:
        server_data: Server authentication data from the client.
        profile_id: The profile ID requesting authentication.

    Returns:
        LoginRemoteAuthResponse with certificate and expiry.
    """
    logger.debug(
        "Auth LoginRemoteAuth: ServerData=%s..., profileId=%s",
        server_data[:20] if server_data else "",
        profile_id,
    )

    session = create_session()
    try:
        cert = get_available_certificate(session)
        expiry_time = datetime.utcnow() + timedelta(seconds=CERT_EXPIRY_SECONDS)
        expiry_str = expiry_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if cert:
            logger.debug("Auth: Allocated certificate id=%s", cert.id)
            return LoginRemoteAuthResponse.success(
                certificate=cert.certificate_data,
                expiry=expiry_str,
            )
        else:
            logger.debug("Auth: No certificates available, using placeholder")
            return LoginRemoteAuthResponse.success(
                certificate="PLACEHOLDER_CERTIFICATE",
                expiry=expiry_str,
            )

    finally:
        session.close()


@auth_router.post("/AuthService/AuthService.asmx")
async def auth_handler(request: Request) -> Response:
    """
    Main handler for Auth Service SOAP requests.

    Routes requests based on SOAPAction header.
    """
    try:
        soap_action = request.headers.get("SOAPAction", "").strip('"')
        logger.debug("Auth: SOAPAction=%s", soap_action)

        body = await request.body()
        xml_content = body.decode("utf-8")
        logger.debug("Auth: Request body=%s", xml_content[:500])

        operation = extract_soap_body(xml_content)
        operation_name = get_operation_name(operation)
        logger.debug("Auth: Operation=%s", operation_name)

        if "LoginRemoteAuth" in soap_action or operation_name == "LoginRemoteAuth":
            server_data = get_element_text(operation, "ServerData")
            profile_id_str = get_element_text(operation, "profileId")
            profile_id = int(profile_id_str) if profile_id_str else 0

            response_model = handle_login_remote_auth(server_data, profile_id)
            response_xml = wrap_soap_envelope(response_model)
        else:
            # Return generic success for unknown operations
            response_model = LoginRemoteAuthResponse(result="Success")
            response_xml = wrap_soap_envelope(response_model)

        logger.debug("Auth: Response=%s", response_xml[:500])

        return Response(
            content=response_xml,
            media_type="text/xml; charset=utf-8",
        )

    except Exception as e:
        logger.exception("Auth: Error processing request: %s", e)
        fault_xml = create_soap_fault(str(e))
        return Response(
            content=fault_xml,
            media_type="text/xml; charset=utf-8",
            status_code=500,
        )
