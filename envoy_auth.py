"""Local Enphase IQ Gateway (Envoy) access using a pre-provisioned bearer token.

The Envoy's local API requires a bearer token over HTTPS (plain HTTP on port
80 is refused outright). Rather than have the CYD perform the Enlighten
login/token-exchange itself, ENVOY_TOKEN is generated once outside the device
and stored in secrets.py; this module just attaches it to HTTPS requests
against the local Envoy. Certificate verification is left off since the
Envoy's cert is self-signed.
"""
import socket
import time
import ujson  # type: ignore

try:
    import ssl  # type: ignore
except ImportError:
    import ussl as ssl  # type: ignore

from secrets import ENVOY_HOST, ENVOY_TOKEN  # type: ignore

REQUEST_TIMEOUT = 8.0
HANDSHAKE_RETRIES = 3
HANDSHAKE_RETRY_DELAY_MS = 500


def _connect_and_wrap_with_retries(host, port=443):
    # Each retry opens a brand new TCP connection: retrying wrap_socket() on
    # a socket that already failed mid-handshake just corrupts the stream
    # further (a partial handshake has already been sent/consumed on it).
    addr = socket.getaddrinfo(host, port)[0][-1]
    attempt = 1
    while True:
        s = socket.socket()
        s.settimeout(REQUEST_TIMEOUT)
        try:
            s.connect(addr)
            return ssl.wrap_socket(s, server_hostname=host)  # type: ignore
        except OSError as e:
            s.close()
            print("TLS handshake with %s failed on attempt %d/%d: %s"
                  % (host, attempt, HANDSHAKE_RETRIES, e))
            if attempt == HANDSHAKE_RETRIES:
                raise
            time.sleep_ms(HANDSHAKE_RETRY_DELAY_MS)  # type: ignore
            attempt += 1


def fetch_envoy_json(path):
    """GET a path from the local Envoy over HTTPS, authenticated with ENVOY_TOKEN."""
    s = _connect_and_wrap_with_retries(ENVOY_HOST)

    try:
        request = (
            "GET %s HTTP/1.0\r\n"
            "Host: %s\r\n"
            "Authorization: Bearer %s\r\n"
            "Accept: application/json\r\n"
            "\r\n"
        ) % (path, ENVOY_HOST, ENVOY_TOKEN)
        s.write(request.encode())

        raw = b""
        while True:
            chunk = s.read(512)
            if not chunk:
                break
            raw += chunk
    finally:
        s.close()

    header_end = raw.find(b"\r\n\r\n")
    status_line = raw[:header_end].split(b"\r\n")[0].decode()
    status_code = int(status_line.split(" ")[1])
    body = raw[header_end + 4:]

    if status_code != 200:
        raise RuntimeError("Envoy request failed (%d): %s" % (status_code, body[:200]))

    return ujson.loads(body)
