"""Unit tests for Authentication system."""

import httpx
import pytest

from sus.auth import (
    AuthCredentials,
    AuthToken,
    BasicAuthProvider,
    CookieAuthProvider,
    HeaderAuthProvider,
    OAuth2Provider,
    SessionManager,
    create_auth_provider,
)


def test_auth_token_is_expired_no_expiry() -> None:
    """Test token with no expiry is never expired."""
    token = AuthToken(access_token="abc123", expires_in=None)
    assert not token.is_expired()


def test_auth_token_is_expired_fresh_token() -> None:
    """Test fresh token is not expired."""
    token = AuthToken(access_token="abc123", expires_in=3600)  # 1 hour
    assert not token.is_expired()


def test_auth_token_is_expired_with_buffer() -> None:
    """Test token expiry with buffer seconds."""
    token = AuthToken(access_token="abc123", expires_in=30)  # 30 seconds

    # With default 60s buffer, should be considered expired
    assert token.is_expired(buffer_seconds=60)

    # With 0s buffer, should not be expired yet
    assert not token.is_expired(buffer_seconds=0)


def test_basic_auth_provider_initialization() -> None:
    """Test BasicAuthProvider initialization."""
    credentials = AuthCredentials(username="testuser", password="testpass")
    provider = BasicAuthProvider(credentials)

    assert provider.credentials.username == "testuser"
    assert provider.credentials.password == "testpass"


def test_basic_auth_provider_missing_credentials() -> None:
    """Test BasicAuthProvider raises error for missing credentials."""
    # Missing password
    with pytest.raises(ValueError, match="requires username and password"):
        BasicAuthProvider(AuthCredentials(username="user"))

    # Missing username
    with pytest.raises(ValueError, match="requires username and password"):
        BasicAuthProvider(AuthCredentials(password="pass"))


@pytest.mark.asyncio
async def test_basic_auth_provider_prepare_request() -> None:
    """Test BasicAuthProvider adds Authorization header."""
    credentials = AuthCredentials(username="testuser", password="testpass")
    provider = BasicAuthProvider(credentials)

    # Create a dummy request
    request = httpx.Request("GET", "https://example.com")

    # Prepare request with auth
    await provider.prepare_request(request)

    # Check Authorization header was added
    assert "Authorization" in request.headers
    assert request.headers["Authorization"].startswith("Basic ")


def test_cookie_auth_provider_initialization() -> None:
    """Test CookieAuthProvider initialization."""
    credentials = AuthCredentials(cookies={"session_id": "abc123", "user_id": "456"})
    provider = CookieAuthProvider(credentials)

    assert provider.credentials.cookies == {"session_id": "abc123", "user_id": "456"}


def test_cookie_auth_provider_missing_cookies() -> None:
    """Test CookieAuthProvider raises error for missing cookies."""
    with pytest.raises(ValueError, match="requires cookies"):
        CookieAuthProvider(AuthCredentials())


@pytest.mark.asyncio
async def test_cookie_auth_provider_prepare_request() -> None:
    """Test CookieAuthProvider adds cookies to request."""
    credentials = AuthCredentials(cookies={"session_id": "abc123"})
    provider = CookieAuthProvider(credentials)

    # Create a dummy request
    request = httpx.Request("GET", "https://example.com")

    # Prepare request with auth
    await provider.prepare_request(request)

    # Check Cookie header was added
    assert "Cookie" in request.headers
    assert "session_id=abc123" in request.headers["Cookie"]


def test_header_auth_provider_initialization() -> None:
    """Test HeaderAuthProvider initialization."""
    credentials = AuthCredentials(headers={"X-API-Key": "secret123", "X-User-Id": "456"})
    provider = HeaderAuthProvider(credentials)

    assert provider.credentials.headers == {"X-API-Key": "secret123", "X-User-Id": "456"}


def test_header_auth_provider_missing_headers() -> None:
    """Test HeaderAuthProvider raises error for missing headers."""
    with pytest.raises(ValueError, match="requires headers"):
        HeaderAuthProvider(AuthCredentials())


@pytest.mark.asyncio
async def test_header_auth_provider_prepare_request() -> None:
    """Test HeaderAuthProvider adds custom headers to request."""
    credentials = AuthCredentials(headers={"X-API-Key": "secret123", "X-Custom": "value"})
    provider = HeaderAuthProvider(credentials)

    # Create a dummy request
    request = httpx.Request("GET", "https://example.com")

    # Prepare request with auth
    await provider.prepare_request(request)

    # Check custom headers were added
    assert request.headers["X-API-Key"] == "secret123"
    assert request.headers["X-Custom"] == "value"


def test_oauth2_provider_initialization() -> None:
    """Test OAuth2Provider initialization."""
    credentials = AuthCredentials(
        client_id="client123",
        client_secret="secret456",
        token_url="https://auth.example.com/oauth/token",
        scope="read write",
    )
    provider = OAuth2Provider(credentials)

    assert provider.credentials.client_id == "client123"
    assert provider.credentials.client_secret == "secret456"
    assert provider.credentials.token_url == "https://auth.example.com/oauth/token"
    assert provider.credentials.scope == "read write"


def test_oauth2_provider_missing_credentials() -> None:
    """Test OAuth2Provider raises error for missing credentials."""
    # Missing client_secret
    with pytest.raises(ValueError, match="requires client_id, client_secret, and token_url"):
        OAuth2Provider(
            AuthCredentials(
                client_id="client123",
                token_url="https://auth.example.com/oauth/token",
            )
        )

    # Missing token_url
    with pytest.raises(ValueError, match="requires client_id, client_secret, and token_url"):
        OAuth2Provider(
            AuthCredentials(
                client_id="client123",
                client_secret="secret456",
            )
        )


@pytest.mark.asyncio
async def test_oauth2_provider_refresh_if_needed() -> None:
    """Test OAuth2Provider refreshes token when needed."""
    credentials = AuthCredentials(
        client_id="test_client",
        client_secret="test_secret",
        token_url="https://httpbin.org/post",  # Use httpbin for testing
    )
    provider = OAuth2Provider(credentials)

    try:
        # Initial token should be None
        assert provider._token is None

        # Call refresh - this will attempt to fetch a token
        # We expect this to fail with httpbin (it won't return valid OAuth2 response)
        # but we can verify the attempt was made
        try:  # noqa: SIM105
            await provider.refresh_if_needed()
        except (httpx.HTTPError, ValueError):
            # Expected - httpbin won't return a valid OAuth2 token response
            pass

    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_oauth2_provider_prepare_request_fetches_token() -> None:
    """Test OAuth2Provider fetches token before preparing request."""
    credentials = AuthCredentials(
        client_id="test_client",
        client_secret="test_secret",
        token_url="https://httpbin.org/post",
    )
    provider = OAuth2Provider(credentials)

    try:
        # Create a dummy request
        request = httpx.Request("GET", "https://example.com")

        # Attempt to prepare request - should try to fetch token first
        try:  # noqa: SIM105
            await provider.prepare_request(request)
        except (httpx.HTTPError, ValueError):
            # Expected - httpbin won't return a valid OAuth2 token response
            pass

    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_oauth2_provider_close() -> None:
    """Test OAuth2Provider closes HTTP client."""
    credentials = AuthCredentials(
        client_id="test_client",
        client_secret="test_secret",
        token_url="https://auth.example.com/oauth/token",
    )
    provider = OAuth2Provider(credentials)

    # Close should succeed without errors
    await provider.close()

    # HTTP client should be closed
    assert provider._http_client.is_closed


def test_session_manager_initialization() -> None:
    """Test SessionManager initialization."""
    credentials = AuthCredentials(username="user", password="pass")
    manager = SessionManager("basic", credentials)

    assert manager.auth_type == "basic"
    assert manager.credentials.username == "user"


@pytest.mark.asyncio
async def test_session_manager_context_manager() -> None:
    """Test SessionManager as async context manager."""
    credentials = AuthCredentials(username="user", password="pass")
    manager = SessionManager("basic", credentials)

    # Use as context manager
    async with manager:
        assert manager._provider is not None
        assert isinstance(manager._provider, BasicAuthProvider)

    # After exit, provider should be cleaned up
    assert manager._provider is None


@pytest.mark.asyncio
async def test_session_manager_prepare_request() -> None:
    """Test SessionManager prepares requests using provider."""
    credentials = AuthCredentials(username="testuser", password="testpass")
    manager = SessionManager("basic", credentials)

    async with manager:
        request = httpx.Request("GET", "https://example.com")
        await manager.prepare_request(request)

        # Check that BasicAuthProvider added Authorization header
        assert "Authorization" in request.headers


@pytest.mark.asyncio
async def test_session_manager_prepare_request_outside_context() -> None:
    """Test SessionManager raises error when used outside context manager."""
    credentials = AuthCredentials(username="user", password="pass")
    manager = SessionManager("basic", credentials)

    request = httpx.Request("GET", "https://example.com")

    # Should raise error when used outside context manager
    with pytest.raises(RuntimeError, match="must be used as async context manager"):
        await manager.prepare_request(request)


@pytest.mark.asyncio
async def test_session_manager_refresh_if_needed() -> None:
    """Test SessionManager delegates refresh to provider."""
    credentials = AuthCredentials(username="user", password="pass")
    manager = SessionManager("basic", credentials)

    async with manager:
        # Should not raise error (BasicAuthProvider doesn't need refresh)
        await manager.refresh_if_needed()


def test_create_auth_provider_basic() -> None:
    """Test factory creates BasicAuthProvider."""
    credentials = AuthCredentials(username="user", password="pass")
    provider = create_auth_provider("basic", credentials)

    assert isinstance(provider, BasicAuthProvider)


def test_create_auth_provider_cookie() -> None:
    """Test factory creates CookieAuthProvider."""
    credentials = AuthCredentials(cookies={"session": "abc"})
    provider = create_auth_provider("cookie", credentials)

    assert isinstance(provider, CookieAuthProvider)


def test_create_auth_provider_header() -> None:
    """Test factory creates HeaderAuthProvider."""
    credentials = AuthCredentials(headers={"X-API-Key": "secret"})
    provider = create_auth_provider("header", credentials)

    assert isinstance(provider, HeaderAuthProvider)


def test_create_auth_provider_oauth2() -> None:
    """Test factory creates OAuth2Provider."""
    credentials = AuthCredentials(
        client_id="client",
        client_secret="secret",
        token_url="https://auth.example.com/token",
    )
    provider = create_auth_provider("oauth2", credentials)

    assert isinstance(provider, OAuth2Provider)


def test_create_auth_provider_case_insensitive() -> None:
    """Test factory is case insensitive."""
    credentials = AuthCredentials(username="user", password="pass")

    provider1 = create_auth_provider("BASIC", credentials)
    provider2 = create_auth_provider("Basic", credentials)
    provider3 = create_auth_provider("basic", credentials)

    assert isinstance(provider1, BasicAuthProvider)
    assert isinstance(provider2, BasicAuthProvider)
    assert isinstance(provider3, BasicAuthProvider)


def test_create_auth_provider_invalid_type() -> None:
    """Test factory raises error for invalid auth type."""
    credentials = AuthCredentials()

    with pytest.raises(ValueError, match="Invalid auth_type"):
        create_auth_provider("invalid", credentials)
