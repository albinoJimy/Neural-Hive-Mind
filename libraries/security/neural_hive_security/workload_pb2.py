"""
SPIRE Workload API protobuf stubs
Generated from SPIRE workload.proto
"""

# This file contains minimal stubs for the SPIRE Workload API
# In production, these should be generated from the official SPIRE .proto files
# using protoc

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import List, Optional


class JWTSVIDRequest(_message.Message):
    """Request for JWT-SVID"""
    audience: List[str]
    spiffe_id: Optional[str]

    def __init__(self, audience: List[str] = None, spiffe_id: str = None):
        self.audience = audience or []
        self.spiffe_id = spiffe_id


class JWTSVID(_message.Message):
    """JWT-SVID response"""
    spiffe_id: str
    svid: str
    expires_at: int

    def __init__(self, spiffe_id: str = "", svid: str = "", expires_at: int = 0):
        self.spiffe_id = spiffe_id
        self.svid = svid
        self.expires_at = expires_at


class JWTSVIDResponse(_message.Message):
    """Response containing JWT-SVIDs"""
    svids: List[JWTSVID]

    def __init__(self, svids: List[JWTSVID] = None):
        self.svids = svids or []


class X509SVIDRequest(_message.Message):
    """Request for X.509-SVID"""
    pass


class X509SVID(_message.Message):
    """X.509-SVID response"""
    spiffe_id: str
    x509_svid: bytes
    x509_svid_key: bytes
    bundle: bytes
    expires_at: int

    def __init__(
        self,
        spiffe_id: str = "",
        x509_svid: bytes = b"",
        x509_svid_key: bytes = b"",
        bundle: bytes = b"",
        expires_at: int = 0
    ):
        self.spiffe_id = spiffe_id
        self.x509_svid = x509_svid
        self.x509_svid_key = x509_svid_key
        self.bundle = bundle
        self.expires_at = expires_at


class X509SVIDResponse(_message.Message):
    """Response containing X.509-SVIDs"""
    svids: List[X509SVID]
    crl: List[bytes]
    federated_bundles: dict

    def __init__(
        self,
        svids: List[X509SVID] = None,
        crl: List[bytes] = None,
        federated_bundles: dict = None
    ):
        self.svids = svids or []
        self.crl = crl or []
        self.federated_bundles = federated_bundles or {}


class ValidateJWTSVIDRequest(_message.Message):
    """Request to validate JWT-SVID"""
    audience: str
    svid: str

    def __init__(self, audience: str = "", svid: str = ""):
        self.audience = audience
        self.svid = svid


class ValidateJWTSVIDResponse(_message.Message):
    """Response from JWT-SVID validation"""
    spiffe_id: str
    claims: dict

    def __init__(self, spiffe_id: str = "", claims: dict = None):
        self.spiffe_id = spiffe_id
        self.claims = claims or {}
