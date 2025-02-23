# from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import base64
import json
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Header

# Load public key once at startup
PUBLIC_KEY = serialization.load_pem_public_key(
    Path('public.pem').read_bytes()
)

class InvalidAPIKey(HTTPException):
    INVALID_KEY_MSG = "Invalid API key"
    def __init__(self):
        super().__init__(status_code=403, detail=InvalidAPIKey.INVALID_KEY_MSG)

class ExpiredAPIKey(HTTPException):
    EXPIRED_KEY_MSG = "Token expired"
    def __init__(self):
        super().__init__(status_code=403, detail=ExpiredAPIKey.EXPIRED_KEY_MSG)

# todo: revoked key exception

def verify_api_key(api_key: str = Header(...)):
    try:
        # Decode the entire token at once
        raw_data = base64.b64decode(api_key)
        
        # Ed25519 signatures are exactly 64 bytes
        SIGNATURE_SIZE = 64
        
        # Split the raw data into payload and signature
        payload_bytes = raw_data[:-SIGNATURE_SIZE]
        print(f"payload_bytes: {payload_bytes}")
        signature = raw_data[-SIGNATURE_SIZE:]
        print(f"signature: {signature}")
        
        # Parse the payload
        payload = json.loads(payload_bytes)
        
        # Check required fields
        if not all(k in payload for k in ['t', 'e', 'x']):
            raise InvalidAPIKey()

        # Verify dates
        today = datetime.now().strftime('%Y%m%d')
        if payload['x'] < today:
            raise ExpiredAPIKey()
            
        # Verify signature
        try:
            PUBLIC_KEY.verify(signature, payload_bytes)
            return {
                'tid': payload['t'],
                'email': payload['e'],
                'expires': payload['x']
            }
        except InvalidSignature:
            raise InvalidAPIKey()
            
    except (ValueError, KeyError, json.JSONDecodeError):
        raise InvalidAPIKey()

