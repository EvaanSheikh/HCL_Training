import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import auth


@pytest.fixture
def token_env(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("AUTH0_ISSUER", "https://tenant.example/")
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://noha.example/api")
    monkeypatch.setenv("AUTH0_JWKS_URL", "https://tenant.example/.well-known/jwks.json")
    monkeypatch.setenv("AUTH0_REQUIRED_SCOPE", "noha:access")
    monkeypatch.setenv("AUTH0_ALLOWED_CLIENT_ID", "bff-client")
    class Key:
        key = private.public_key()
    class Client:
        def get_signing_key_from_jwt(self, token):
            return Key()
    monkeypatch.setattr(auth, "_jwks_client", lambda _: Client())
    return private


def make_token(private, **overrides):
    claims = {"iss": "https://tenant.example/", "sub": "auth0|user-a", "aud": "https://noha.example/api",
              "iat": int(time.time()), "exp": int(time.time()) + 60, "scope": "noha:access", "azp": "bff-client"}
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256")


def test_valid_token_resolves_issuer_subject(token_env):
    principal = auth.validate_access_token(make_token(token_env))
    assert (principal.issuer, principal.subject) == ("https://tenant.example/", "auth0|user-a")


@pytest.mark.parametrize("claims", [
    {"iss": "https://attacker.example/"},
    {"aud": "wrong-audience"},
    {"scope": "openid"},
    {"exp": int(time.time()) - 120},
    {"azp": "untrusted-client"},
])
def test_wrong_claims_rejected(token_env, claims):
    status = 403 if "scope" in claims else 401
    with pytest.raises(HTTPException) as error:
        auth.validate_access_token(make_token(token_env, **claims))
    assert error.value.status_code == status
    assert "tenant.example" not in str(error.value.detail)


def test_bad_signature_rejected(token_env):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(HTTPException) as error:
        auth.validate_access_token(make_token(other))
    assert error.value.status_code == 401


def test_missing_auth_configuration_fails_closed(monkeypatch):
    for key in ("AUTH0_ISSUER", "AUTH0_AUDIENCE", "AUTH0_JWKS_URL", "AUTH0_ALLOWED_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(HTTPException) as error:
        auth.validate_access_token("anything")
    assert error.value.status_code == 503


def test_fastapi_http_rejects_bad_bearer_tokens_and_accepts_valid_claims(api_test_client, token_env):
    from app import auth
    from cryptography.hazmat.primitives.asymmetric import rsa
    from app.api import routes
    from app.auth import Principal

    endpoint = "/api/analysis/00000000-0000-4000-8000-000000000000"
    assert api_test_client.get(endpoint, headers={"Authorization": "Bearer malformed"}).status_code == 401

    wrong_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rejected = [
        (make_token(token_env, iss="https://wrong.example/"), 401),
        (make_token(token_env, aud="wrong-audience"), 401),
        (make_token(token_env, exp=int(time.time()) - 120), 401),
        (make_token(token_env, scope="openid"), 403),
        (make_token(wrong_private), 401),
    ]
    for token, expected_status in rejected:
        response = api_test_client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == expected_status
        assert "tenant.example" not in response.text
        assert "C:\\Users\\" not in response.text

    valid = api_test_client.get(endpoint, headers={"Authorization": f"Bearer {make_token(token_env)}"})
    assert valid.status_code == 404


def test_fastapi_http_fails_closed_for_missing_config_and_jwks_outage(api_test_client, token_env, monkeypatch):
    from app import auth
    endpoint = "/api/analysis/00000000-0000-4000-8000-000000000000"
    token = make_token(token_env)
    monkeypatch.delenv("AUTH0_ALLOWED_CLIENT_ID")
    missing = api_test_client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
    assert missing.status_code == 503

    monkeypatch.setenv("AUTH0_ALLOWED_CLIENT_ID", "bff-client")
    class OfflineClient:
        def get_signing_key_from_jwt(self, _token):
            raise auth.jwt.PyJWKClientConnectionError("network detail must not leak")
    monkeypatch.setattr(auth, "_jwks_client", lambda _url: OfflineClient())
    outage = api_test_client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
    assert outage.status_code == 503
    assert "network detail" not in outage.text


def test_report_path_redaction_does_not_return_private_paths():
    from app.api.routes import _safe_report
    result = _safe_report("chart at C:\\private\\reports\\chart.png and /srv/noha/reports/plot.png")
    assert "C:\\private" not in result
    assert "/srv/noha" not in result
    assert "[private asset]" in result


def test_chart_route_streams_only_contained_png_and_returns_generic_not_found(tmp_path, monkeypatch):
    from app.api import routes
    from app.auth import Principal
    root = tmp_path / "reports" / "private"
    chart = root / "session" / "chart.png"
    chart.parent.mkdir(parents=True)
    chart.write_bytes(b"png-test")
    monkeypatch.setattr(routes, "PRIVATE_REPORT_ROOT", root)
    monkeypatch.setattr(routes, "get_user_id", lambda principal: principal.subject)
    assets = {"asset": {"relative_path": "session/chart.png", "media_type": "image/png"}}
    monkeypatch.setattr(routes, "get_owned_report_asset", lambda sid, aid, owner: assets.get(aid) if owner == "owner" else None)

    opened_handles = []
    original_open = routes._open_private_asset
    def capture_open(relative_path, private_root):
        handle = original_open(relative_path, private_root)
        opened_handles.append(handle)
        return handle
    monkeypatch.setattr(routes, "_open_private_asset", capture_open)
    response = routes.get_analysis_chart("session", "asset", Principal("https://issuer/", "owner"))
    assert opened_handles[0].read() == b"png-test"
    opened_handles[0].close()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"

    with pytest.raises(HTTPException) as denied:
        routes.get_analysis_chart("session", "asset", Principal("https://issuer/", "other"))
    assert denied.value.status_code == 404

    assets["traversal"] = {"relative_path": "../../outside.png", "media_type": "image/png"}
    with pytest.raises(HTTPException) as rejected:
        routes.get_analysis_chart("session", "traversal", Principal("https://issuer/", "owner"))
    assert rejected.value.status_code == 404
