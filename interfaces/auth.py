"""HTTP authentication boundary for the stdlib server."""
from __future__ import annotations

from functools import wraps
from http.cookies import SimpleCookie
import ipaddress
import os
import socket
from urllib.parse import urlparse

from auth import AuthError, AuthStore, COOKIE_NAME, auth_mode, current_principal, principal_scope, registration_enabled


def loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def secure_cookie() -> bool:
    default = "true" if os.getenv("AGENT_PUBLIC_ORIGIN", "").startswith("https://") else "false"
    return os.getenv("AGENT_AUTH_COOKIE_SECURE", default).lower() != "false"


def configure_server(host: str) -> None:
    """Network listeners default to accounts; explicit local mode stays local."""
    if not loopback(host):
        os.environ.setdefault("AGENT_AUTH_MODE", "multiuser")
    if auth_mode() == "multiuser" and not os.getenv("AGENT_PUBLIC_ORIGIN"):
        os.environ["AGENT_DIRECT_HTTP"] = "true"
    validate_server(host)


def validate_server(host: str) -> None:
    if auth_mode() == "local" and not loopback(host):
        raise ValueError("Local mode must bind to localhost. Use AGENT_AUTH_MODE=multiuser for network access.")
    if auth_mode() == "multiuser" and os.getenv("AGENT_PUBLIC_ORIGIN"):
        origin = urlparse(os.getenv("AGENT_PUBLIC_ORIGIN", ""))
        if origin.scheme not in {"http", "https"} or not origin.netloc or origin.path not in {"", "/"} or origin.query or origin.fragment or origin.username:
            raise ValueError("AGENT_PUBLIC_ORIGIN must be an HTTP(S) origin without a path.")
        if origin.scheme == "https" and not secure_cookie():
            raise ValueError("HTTPS requires secure cookies.")
    elif auth_mode() == "multiuser" and not loopback(host) and os.getenv("AGENT_DIRECT_HTTP") != "true":
        raise ValueError("Configure the direct HTTP listener before network access.")


def _check_origin(handler) -> None:
    host = handler.headers.get("Host", "")
    public = os.getenv("AGENT_PUBLIC_ORIGIN", "").rstrip("/")
    hostname = urlparse("http://" + host).hostname or ""
    if auth_mode() == "local":
        # Host validation also rejects DNS rebinding against the local service.
        if not loopback(hostname) or not loopback(handler.client_address[0]):
            raise AuthError("Local mode is available only through localhost.")
    elif public:
        if host != urlparse(public).netloc:
            raise AuthError("Unexpected request host.")
    elif os.getenv("AGENT_DIRECT_HTTP") == "true":
        # Numeric server addresses work on a LAN without trusting arbitrary DNS
        # names. Configure PUBLIC_ORIGIN when using a domain/reverse proxy.
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            if hostname not in {"localhost", socket.gethostname().lower()}:
                raise AuthError("Use the server IP address or configure AGENT_PUBLIC_ORIGIN.") from None
    elif not loopback(hostname) or not loopback(handler.client_address[0]):
        raise AuthError("Configure AGENT_PUBLIC_ORIGIN for network access.")
    origin = handler.headers.get("Origin")
    if handler.command in {"POST", "PATCH", "DELETE"}:
        if handler.headers.get("Sec-Fetch-Site") == "cross-site":
            raise AuthError("Cross-site requests are not accepted.")
        if origin:
            allowed = {public} if public else {"http://" + host, "https://" + host}
            if origin not in allowed:
                raise AuthError("Request origin does not match this application.")


def _credential(handler) -> str:
    authorization = handler.headers.get("Authorization", "")
    if authorization:
        if not authorization.startswith("Bearer "):
            raise AuthError("Invalid authentication scheme.")
        return authorization[7:]
    cookies = SimpleCookie()
    try:
        cookies.load(handler.headers.get("Cookie", ""))
    except Exception:
        raise AuthError("Invalid session cookie.") from None
    value = cookies.get(COOKIE_NAME)
    return value.value if value else ""


def _auth_endpoint(handler, path: str) -> bool:
    if path == "/auth/status" and handler.command == "GET":
        if auth_mode() == "local":
            principal = current_principal()
        else:
            try:
                principal = AuthStore().authenticate(_credential(handler))
            except AuthError:
                principal = None
        handler._send_json({"mode": auth_mode(), "registration_enabled": registration_enabled(), "user": {"id": principal.user_id, "name": principal.username} if principal else None})
        return True
    if path in {"/auth/login", "/auth/register"} and handler.command == "POST":
        if auth_mode() != "multiuser":
            raise AuthError("Login is available only in multi-user mode.")
        payload = handler._read_json()
        username, password = payload.get("username"), payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 100 or len(password) > 1024:
            raise AuthError("Invalid username or password.")
        action = AuthStore().register if path == "/auth/register" else AuthStore().login
        token, principal = action(username, password, handler.client_address[0])
        handler._auth_cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800" + ("; Secure" if secure_cookie() else "")
        handler._send_json({"user": {"id": principal.user_id, "name": principal.username}}, status=201 if path == "/auth/register" else 200)
        return True
    if path == "/auth/logout" and handler.command == "POST":
        if auth_mode() == "multiuser":
            principal = AuthStore().authenticate(_credential(handler))
            AuthStore().logout(principal)
            from harness.website import get_bridge
            get_bridge().revoke_user(principal.user_id)
        handler._auth_cookie = f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + ("; Secure" if secure_cookie() else "")
        handler._send_json({"signed_out": True})
        return True
    return False


def authenticated_request(method):
    @wraps(method)
    def wrapper(handler):
        handler._streaming = False
        handler._auth_cookie = None
        try:
            _check_origin(handler)
            path = urlparse(handler.path).path
            if _auth_endpoint(handler, path):
                return
            public = handler.command == "GET" and (
                path in {"/", "/index.html", "/assistant", "/assistant/", "/assistant.html", "/assistant-demo", "/assistant-demo/", "/assistant-demo.html", "/favicon.svg", "/health"}
                or path.startswith("/static/")
            )
            if public:
                return method(handler)
            principal = current_principal() if auth_mode() == "local" else AuthStore().authenticate(_credential(handler))
            with principal_scope(principal):
                return method(handler)
        except AuthError as exc:
            if handler._streaming:
                handler._send_stream_event("error", {"error": str(exc), "status": exc.status})
            else:
                handler._send_json({"error": str(exc)}, status=exc.status)
        except (ValueError, TypeError) as exc:
            if not handler._streaming:
                handler._send_json({"error": str(exc)}, status=400)
    return wrapper
