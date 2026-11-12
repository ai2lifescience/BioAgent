"""HTTP authentication boundary for the stdlib server."""
from __future__ import annotations

from functools import wraps
from http.cookies import SimpleCookie
import ipaddress
import os
import socket
from urllib.parse import parse_qsl, parse_qs, urlencode, urlparse

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
    if auth_mode() != "local" and not os.getenv("AGENT_PUBLIC_ORIGIN"):
        os.environ["AGENT_DIRECT_HTTP"] = "true"
    validate_server(host)


def validate_server(host: str) -> None:
    if auth_mode() == "local" and not loopback(host):
        raise ValueError("Local mode must bind to localhost. Use AGENT_AUTH_MODE=multiuser for network access.")
    if auth_mode() != "local" and os.getenv("AGENT_PUBLIC_ORIGIN"):
        origin = urlparse(os.getenv("AGENT_PUBLIC_ORIGIN", ""))
        if origin.scheme not in {"http", "https"} or not origin.netloc or origin.path not in {"", "/"} or origin.query or origin.fragment or origin.username:
            raise ValueError("AGENT_PUBLIC_ORIGIN must be an HTTP(S) origin without a path.")
        if origin.scheme == "https" and not secure_cookie():
            raise ValueError("HTTPS requires secure cookies.")
        public_base = os.getenv("AGENT_PUBLIC_BASE_URL", "").strip()
        if public_base:
            base = urlparse(public_base)
            if (base.scheme != origin.scheme or base.netloc != origin.netloc
                    or base.query or base.fragment or base.username):
                raise ValueError("AGENT_PUBLIC_BASE_URL must use the AGENT_PUBLIC_ORIGIN scheme and host.")
    elif auth_mode() != "local" and not loopback(host) and os.getenv("AGENT_DIRECT_HTTP") != "true":
        raise ValueError("Configure the direct HTTP listener before network access.")
    if auth_mode() == "cas":
        from auth.cas import service_url
        service_url()
        _external_logout_url()
    elif auth_mode() == "oauth":
        from auth.oauth import validate_config
        validate_config()


def _request_origin(handler) -> str:
    host = (handler.headers.get("Host") or "").strip()
    if not host or any(char in host for char in "\r\n "):
        return ""
    proto = (handler.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip().lower()
    if proto not in {"http", "https"}:
        proto = "http"
    return f"{proto}://{host}"


def _check_origin(handler) -> None:
    from auth.oauth import flexible_host, local_hostname

    host = handler.headers.get("Host", "")
    public = os.getenv("AGENT_PUBLIC_ORIGIN", "").rstrip("/")
    hostname = urlparse("http://" + host).hostname or ""
    flexible_local = flexible_host() and local_hostname(hostname)
    if auth_mode() == "local":
        # Host validation also rejects DNS rebinding against the local service.
        if not loopback(hostname) or not loopback(handler.client_address[0]):
            raise AuthError("Local mode is available only through localhost.")
    elif public:
        if host != urlparse(public).netloc and not flexible_local:
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
            allowed = {public} if public and not flexible_local else {public, "http://" + host, "https://" + host}
            allowed.discard("")
            if origin.rstrip("/") not in {item.rstrip("/") for item in allowed}:
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


def _cookie(handler, name: str) -> str:
    cookies = SimpleCookie()
    try:
        cookies.load(handler.headers.get("Cookie", ""))
    except Exception:
        raise AuthError("Invalid session cookie.") from None
    value = cookies.get(name)
    return value.value if value else ""


def _redirect(handler, location: str, status: int = 302) -> None:
    handler.send_response(status)
    handler.send_header("Location", location)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def redirect_unauthenticated_app(handler) -> bool:
    """Open the identity login page instead of the unsigned-in application shell."""
    mode = auth_mode()
    if mode not in {"cas", "oauth"}:
        return False
    try:
        if AuthStore().authenticate(_credential(handler)):
            return False
    except AuthError:
        pass
    parsed = urlparse(handler.path)
    kept = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "logged_out"]
    return_to = "/" if parsed.path in {"", "/", "/index.html"} else parsed.path
    if kept:
        return_to += "?" + urlencode(kept)
    login = "/auth/oauth/login" if mode == "oauth" else "/auth/cas/login"
    _redirect(handler, login + "?" + urlencode({"return_to": return_to}))
    return True


def _external_login_url() -> str | None:
    if auth_mode() == "cas":
        return "/auth/cas/login"
    if auth_mode() == "oauth":
        return "/auth/oauth/login"
    return None


def _public_home_path() -> str:
    base = urlparse(os.getenv("AGENT_PUBLIC_BASE_URL", "")).path.rstrip("/")
    return (base + "/") if base else "/"


def _external_logout_url() -> str:
    from auth.cas import logout_url as cas_logout_url
    return cas_logout_url()


def _auth_endpoint(handler, path: str) -> bool:
    if path == "/auth/status" and handler.command == "GET":
        if auth_mode() == "local":
            principal = current_principal()
        else:
            try:
                principal = AuthStore().authenticate(_credential(handler))
            except AuthError:
                principal = None
        handler._send_json({
            "mode": auth_mode(),
            "registration_enabled": registration_enabled(),
            "login_url": _external_login_url(),
            "user": {"id": principal.user_id, "name": principal.username} if principal else None,
        })
        return True
    if path == "/auth/cas/login" and handler.command == "GET":
        if auth_mode() != "cas":
            raise AuthError("CAS login is not enabled.")
        from auth.cas import STATE_COOKIE, begin_login
        query = parse_qs(urlparse(handler.path).query)
        location, state = begin_login((query.get("return_to") or ["/"])[0])
        handler._auth_cookie = (
            f"{STATE_COOKIE}={state}; Path=/auth/cas; HttpOnly; SameSite=Lax; Max-Age=300"
            + ("; Secure" if secure_cookie() else "")
        )
        _redirect(handler, location)
        return True
    if path == "/auth/oauth/login" and handler.command == "GET":
        if auth_mode() != "oauth":
            raise AuthError("OAuth login is not enabled.")
        from auth.oauth import STATE_COOKIE, begin_login
        query = parse_qs(urlparse(handler.path).query)
        location, state = begin_login((query.get("return_to") or ["/"])[0], request_origin=_request_origin(handler))
        handler._auth_cookie = (
            f"{STATE_COOKIE}={state}; Path=/auth/oauth/callback; HttpOnly; SameSite=Lax; Max-Age=600"
            + ("; Secure" if secure_cookie() else "")
        )
        _redirect(handler, location)
        return True
    if path == "/auth/oauth/callback" and handler.command == "GET":
        if auth_mode() != "oauth":
            raise AuthError("OAuth login is not enabled.")
        from auth.oauth import STATE_COOKIE, complete_login
        query = parse_qs(urlparse(handler.path).query)
        if (query.get("error") or [""])[0]:
            _redirect(handler, _public_home_path())
            return True
        try:
            token, _, return_to = complete_login(
                (query.get("code") or [""])[0],
                (query.get("state") or [""])[0],
                _cookie(handler, STATE_COOKIE),
            )
        except AuthError:
            _redirect(handler, _public_home_path())
            return True
        handler._auth_cookie = (
            f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800"
            + ("; Secure" if secure_cookie() else "")
        )
        _redirect(handler, return_to)
        return True
    if path == "/auth/oauth/backchannel-logout" and handler.command == "POST":
        if auth_mode() != "oauth":
            raise AuthError("OAuth login is not enabled.")
        length = int(handler.headers.get("Content-Length", "0"))
        if length <= 0 or length > 16384:
            raise AuthError("Invalid OAuth backchannel logout.")
        from auth.oauth import consume_backchannel_logout
        revoked = consume_backchannel_logout(
            handler.rfile.read(length),
            handler.headers.get("X-OAuth-Logout-Signature", ""),
        )
        handler._send_json({"revoked": revoked})
        return True
    if path == "/auth/cas/callback" and handler.command == "GET":
        if auth_mode() != "cas":
            raise AuthError("CAS login is not enabled.")
        from auth.cas import STATE_COOKIE, complete_login
        query = parse_qs(urlparse(handler.path).query)
        token, _, return_to = complete_login(
            (query.get("ticket") or [""])[0],
            (query.get("state") or [""])[0],
            _cookie(handler, STATE_COOKIE),
        )
        handler._auth_cookie = (
            f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800"
            + ("; Secure" if secure_cookie() else "")
        )
        _redirect(handler, return_to)
        return True
    if path == "/auth/cas/callback" and handler.command == "POST":
        if auth_mode() != "cas":
            raise AuthError("CAS login is not enabled.")
        from auth.cas import consume_single_logout
        length = int(handler.headers.get("Content-Length", "0"))
        user_id = consume_single_logout(handler.rfile.read(length), handler.headers.get("Content-Type", ""))
        if user_id:
            from web_bridge import revoke_user
            revoke_user(user_id)
        handler._send_json({"signed_out": True})
        return True
    if path == "/auth/cas/logout" and handler.command == "POST":
        if auth_mode() != "cas":
            raise AuthError("CAS login is not enabled.")
        principal = AuthStore().authenticate(_credential(handler))
        AuthStore().logout(principal)
        from web_bridge import revoke_user
        revoke_user(principal.user_id)
        handler._auth_cookie = (
            f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            + ("; Secure" if secure_cookie() else "")
        )
        handler._send_json({"signed_out": True, "logout_url": _external_logout_url()})
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
        if auth_mode() == "cas":
            raise AuthError("Use CAS single logout.")
        if auth_mode() in {"multiuser", "oauth"}:
            principal = AuthStore().authenticate(_credential(handler))
            AuthStore().logout(principal)
            from web_bridge import revoke_user
            revoke_user(principal.user_id)
        handler._auth_cookie = f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + ("; Secure" if secure_cookie() else "")
        payload = {"signed_out": True}
        if auth_mode() == "oauth":
            from auth.oauth import begin_logout
            payload["logout_url"] = begin_logout(_request_origin(handler))
        handler._send_json(payload)
        return True
    return False


def authenticated_request(method):
    @wraps(method)
    def wrapper(handler):
        handler._streaming = False
        handler._auth_cookie = None
        handler._website_download_name = None
        try:
            _check_origin(handler)
            path = urlparse(handler.path).path
            from web_bridge import handle_public
            if handle_public(handler, path):
                return
            if _auth_endpoint(handler, path):
                return
            public = handler.command == "GET" and (
                path in {"/", "/index.html", "/assistant", "/assistant/", "/assistant.html", "/assistant-demo", "/assistant-demo/", "/assistant-demo.html", "/favicon.ico", "/favicon.svg", "/health"}
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
