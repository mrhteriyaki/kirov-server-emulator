"""
Pydantic-XML models for Auth SOAP Service.

Endpoint: /AuthService/AuthService.asmx
Namespace: http://gamespy.net/AuthService
"""

from typing import Optional

from pydantic_xml import BaseXmlModel, element

AUTH_NS = "http://gamespy.net/AuthService"


class LoginRemoteAuthRequest(BaseXmlModel, tag="LoginRemoteAuth", nsmap={"": AUTH_NS}):
    """
    Request model for LoginRemoteAuth operation.

    The client sends ServerData and profileId to authenticate.
    """

    server_data: str = element(tag="ServerData", default="")
    profile_id: int = element(tag="profileId", default=0)


class LoginRemoteAuthResponse(BaseXmlModel, tag="LoginRemoteAuthResponse", nsmap={"": AUTH_NS}):
    """
    Response model for LoginRemoteAuth operation.

    Returns a certificate and expiry time on success.
    """

    result: str = element(tag="LoginRemoteAuthResult")
    certificate: Optional[str] = element(tag="certificate", default=None)
    expiry: Optional[str] = element(tag="expiry", default=None)

    @classmethod
    def success(cls, certificate: str, expiry: str) -> "LoginRemoteAuthResponse":
        """Create a successful response with certificate and expiry."""
        return cls(
            result="Success",
            certificate=certificate,
            expiry=expiry,
        )

    @classmethod
    def error(cls, message: str = "Error") -> "LoginRemoteAuthResponse":
        """Create an error response."""
        return cls(result=message)
