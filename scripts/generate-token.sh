#!/bin/bash

# # Generate Ed25519 keypair if private key doesn't exist
# if [ ! -f private.pem ]; then
#     openssl genpkey -algorithm ED25519 -out private.pem
# fi

# # Generate public key
# openssl pkey -in private.pem -pubout -out public.pem

# Create a new token (pass email and expiry date as arguments)
create_token() {
    EMAIL=$1
    EXPIRES=$2
    if [ -z "$EMAIL" ] || [ -z "$EXPIRES" ]; then
        echo "Usage: ./keygen.sh email YYYY-MM-DD"
        echo "Example: ./keygen.sh alice@example.com 2025-12-31"
        exit 1
    fi
    
    # Generate shorter random token ID (8 chars)
    TOKEN_ID=$(openssl rand -hex 4)
    
    # Create compact payload
    PAYLOAD="{\"t\":\"$TOKEN_ID\",\"e\":\"$EMAIL\",\"x\":\"${EXPIRES//-/}\"}"
    
    # Write payload to file for signing
    echo -n "$PAYLOAD" > payload.txt
    
    # Sign payload and get raw signature
    SIGNATURE=$(openssl pkeyutl -sign -inkey private.pem -rawin -in payload.txt)
    
    # Combine and base64 encode
    TOKEN=$( (echo -n "$PAYLOAD"; echo -n "$SIGNATURE") | base64)
    
    # Cleanup
    rm payload.txt
    
    # Output
    echo "Token for $EMAIL (ID: $TOKEN_ID):"
    echo "$TOKEN"
}

create_token $1 $2