#!/usr/bin/env python3
"""Verify the Envoy local-API bearer token from a regular computer.

Mirrors the HTTPS request envoy_auth.py makes on the CYD (GET /production.json
over HTTPS, self-signed cert verification skipped, token in the Authorization
header), but runs under CPython so we can test the token and connection to
the Envoy independently of the ESP32's TLS stack.

Run from the project root:
    python3 pc_test/verify_envoy_auth.py
"""
import http.client
import json
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from secrets import ENVOY_HOST, ENVOY_TOKEN  # noqa: E402  # type: ignore

PATH = "/production.json"


def main():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    print(f"Connecting to https://{ENVOY_HOST}{PATH} ...")
    conn = http.client.HTTPSConnection(ENVOY_HOST, 443, timeout=8, context=context)
    try:
        conn.request(
            "GET",
            PATH,
            headers={
                "Authorization": f"Bearer {ENVOY_TOKEN}",
                "Accept": "application/json",
            },
        )
        response = conn.getresponse()
        body = response.read()
    finally:
        conn.close()

    print(f"Status: {response.status} {response.reason}")

    if response.status != 200:
        print(body.decode(errors="replace")[:1000])
        sys.exit(1)

    data = json.loads(body)
    generating = data["production"][1]["wNow"]
    using = data["consumption"][0]["wNow"]
    print(f"Generating: {generating}W")
    print(f"Using:      {using}W")
    print(f"Net:        {generating - using}W")


if __name__ == "__main__":
    main()
