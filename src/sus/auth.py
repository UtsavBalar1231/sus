"""Authentication system for accessing protected content.

Supports multiple authentication strategies:
- Basic Auth (username/password)
- Cookie-based authentication (session cookies)
- Header-based authentication (API keys, tokens)
- OAuth 2.0 (client credentials flow)

Entry point: create_auth_provider() factory function.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class AuthCredentials:
    """Authentication credentials for various auth methods."""

    # Basic Auth
    username: str | None = None
    password: str | None = None

    # Cookie Auth
    cookies: dict[str, str] = field(default_factory=dict)

    # Header Auth
    headers: dict[str, str] = field(default_factory=dict)

    # OAuth2
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scope: str | None = None


@dataclass
class AuthToken:
    """OAuth2 access token with expiry tracking."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None  # seconds
    refresh_token: str | None = None
    issued_at: float = field(default_factory=time.time)

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if token is expired or will expire soon.

        Args:
            buffer_seconds: Refresh token N seconds before actual expiry

        Returns:
            True if token is expired or will expire within buffer
        """
        if self.expires_in is None:
            return False  # No expiry specified

        elapsed = time.time() - self.issued_at
        return elapsed >= (self.expires_in - buffer_seconds)


class AuthProvider(ABC):
    """Abstract base class for authentication providers.

    Implementations handle different authentication methods and provide
    credentials to HTTP client via prepare_request().
    """

    def __init__(self, credentials: AuthCredentials) -> None:
        """Initialize auth provider.

        Args:
            credentials: Authentication credentials
        """
        self.credentials = credentials

    @abstractmethod
    async def prepare_request(self, request: httpx.Request) -> None:
        """Prepare HTTP request with authentication credentials.

        Modifies request in-place to add auth headers, cookies, or other credentials.

        Args:
            request: HTTPX request to modify
        """
        pass

    async def refresh_if_needed(self) -> None:  # noqa: B027
        """Refresh authentication if needed (e.g., expired tokens).

        Default implementation does nothing. Override for token-based auth.
        """
        pass

    async def close(self) -> None:  # noqa: B027
        """Cleanup resources (HTTP clients, sessions, etc.).

        Default implementation does nothing. Override if needed.
        """
        pass


class BasicAuthProvider(AuthProvider):
    """HTTP Basic Authentication provider.

    Adds Authorization header with base64-encoded username:password.

    Example:
        >>> credentials = AuthCredentials(username="user", password="pass")
        >>> provider = BasicAuthProvider(credentials)
        >>> await provider.prepare_request(request)  # Adds Authorization header
    """

    def __init__(self, credentials: AuthCredentials) -> None:
        """Initialize Basic Auth provider.

        Args:
            credentials: Must contain username and password

        Raises:
            ValueError: If username or password is missing
        """
        super().__init__(credentials)

        if not credentials.username or not credentials.password:
            raise ValueError("BasicAuthProvider requires username and password")

    async def prepare_request(self, request: httpx.Request) -> None:
        """Add Basic Auth header to request.

        Args:
            request: HTTPX request to modify
        """
        import base64

        credentials_str = f"{self.credentials.username}:{self.credentials.password}"
        encoded = base64.b64encode(credentials_str.encode("utf-8")).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"


class CookieAuthProvider(AuthProvider):
    """Cookie-based authentication provider.

    Uses pre-authenticated session cookies for authentication.
    Useful for sites that require login via web form.

    Example:
        >>> credentials = AuthCredentials(cookies={"session_id": "abc123"})
        >>> provider = CookieAuthProvider(credentials)
        >>> await provider.prepare_request(request)  # Adds cookies
    """

    def __init__(self, credentials: AuthCredentials) -> None:
        """Initialize Cookie Auth provider.

        Args:
            credentials: Must contain cookies dict

        Raises:
            ValueError: If cookies dict is empty
        """
        super().__init__(credentials)

        if not credentials.cookies:
            raise ValueError("CookieAuthProvider requires cookies")

    async def prepare_request(self, request: httpx.Request) -> None:
        """Add cookies to request.

        Args:
            request: HTTPX request to modify
        """
        # Add cookies to request (join all cookies with semicolons)
        cookie_parts = [f"{name}={value}" for name, value in self.credentials.cookies.items()]
        request.headers["Cookie"] = "; ".join(cookie_parts)


class HeaderAuthProvider(AuthProvider):
    """Header-based authentication provider.

    Adds custom headers for authentication (e.g., API keys, bearer tokens).

    Example:
        >>> credentials = AuthCredentials(headers={"X-API-Key": "secret123"})
        >>> provider = HeaderAuthProvider(credentials)
        >>> await provider.prepare_request(request)  # Adds X-API-Key header
    """

    def __init__(self, credentials: AuthCredentials) -> None:
        """Initialize Header Auth provider.

        Args:
            credentials: Must contain headers dict

        Raises:
            ValueError: If headers dict is empty
        """
        super().__init__(credentials)

        if not credentials.headers:
            raise ValueError("HeaderAuthProvider requires headers")

    async def prepare_request(self, request: httpx.Request) -> None:
        """Add custom headers to request.

        Args:
            request: HTTPX request to modify
        """
        request.headers.update(self.credentials.headers)


class OAuth2Provider(AuthProvider):
    """OAuth 2.0 Client Credentials flow provider.

    Automatically fetches and refreshes access tokens using client credentials.
    Suitable for API-to-API authentication (not user authentication).

    Example:
        >>> credentials = AuthCredentials(
        ...     client_id="client",
        ...     client_secret="secret",
        ...     token_url="https://api.example.com/oauth/token"
        ... )
        >>> provider = OAuth2Provider(credentials)
        >>> await provider.prepare_request(request)  # Adds Bearer token
    """

    def __init__(self, credentials: AuthCredentials) -> None:
        """Initialize OAuth2 provider.

        Args:
            credentials: Must contain client_id, client_secret, and token_url

        Raises:
            ValueError: If required OAuth2 fields are missing
        """
        super().__init__(credentials)

        if not credentials.client_id or not credentials.client_secret or not credentials.token_url:
            raise ValueError("OAuth2Provider requires client_id, client_secret, and token_url")

        self._token: AuthToken | None = None
        self._token_lock = asyncio.Lock()
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def _fetch_token(self) -> AuthToken:
        """Fetch new access token from OAuth2 server.

        Returns:
            New access token

        Raises:
            httpx.HTTPError: If token request fails
        """
        token_data = {
            "grant_type": "client_credentials",
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
        }

        if self.credentials.scope:
            token_data["scope"] = self.credentials.scope

        # token_url is guaranteed to exist by __init__ validation
        assert self.credentials.token_url is not None

        try:
            response = await self._http_client.post(
                self.credentials.token_url,
                data=token_data,
            )
            response.raise_for_status()
            token_json = response.json()
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"OAuth2 token request failed with status "
                f"{e.response.status_code}: {e.response.text}"
            ) from e
        except ValueError as e:
            # httpx raises ValueError (not JSONDecodeError) for invalid JSON in response.json()
            raise ValueError(f"OAuth2 server returned invalid JSON: {e}") from e

        if "access_token" not in token_json:
            raise ValueError(
                f"OAuth2 response missing 'access_token' field. Received: {list(token_json.keys())}"
            )

        return AuthToken(
            access_token=token_json["access_token"],
            token_type=token_json.get("token_type", "Bearer"),
            expires_in=token_json.get("expires_in"),
            refresh_token=token_json.get("refresh_token"),
        )

    async def refresh_if_needed(self) -> None:
        """Refresh access token if expired or missing."""
        async with self._token_lock:
            # Check if we need a new token
            if self._token is None or self._token.is_expired():
                self._token = await self._fetch_token()

    async def prepare_request(self, request: httpx.Request) -> None:
        """Add OAuth2 Bearer token to request.

        Automatically refreshes token if expired.

        Args:
            request: HTTPX request to modify
        """
        await self.refresh_if_needed()

        if self._token:
            auth_value = f"{self._token.token_type} {self._token.access_token}"
            request.headers["Authorization"] = auth_value

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()


class SessionManager:
    """Manages authentication state across crawl session.

    Coordinates auth provider lifecycle (initialization, refresh, cleanup).
    Provides single interface for crawler to interact with auth system.

    Example:
        >>> credentials = AuthCredentials(username="user", password="pass")
        >>> manager = SessionManager("basic", credentials)
        >>> async with manager:
        ...     await manager.prepare_request(request)
    """

    def __init__(self, auth_type: str, credentials: AuthCredentials) -> None:
        """Initialize session manager.

        Args:
            auth_type: Authentication type ("basic", "cookie", "header", "oauth2")
            credentials: Authentication credentials

        Raises:
            ValueError: If auth_type is invalid
        """
        self.auth_type = auth_type
        self.credentials = credentials
        self._provider: AuthProvider | None = None

    async def __aenter__(self) -> "SessionManager":
        """Initialize auth provider (async context manager)."""
        self._provider = create_auth_provider(self.auth_type, self.credentials)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Cleanup auth provider (async context manager)."""
        if self._provider:
            await self._provider.close()
            self._provider = None

    async def prepare_request(self, request: httpx.Request) -> None:
        """Prepare request with authentication credentials.

        Args:
            request: HTTPX request to modify

        Raises:
            RuntimeError: If called outside async context manager
        """
        if self._provider is None:
            raise RuntimeError("SessionManager must be used as async context manager")

        await self._provider.prepare_request(request)

    async def refresh_if_needed(self) -> None:
        """Refresh authentication if needed.

        Raises:
            RuntimeError: If called outside async context manager
        """
        if self._provider is None:
            raise RuntimeError("SessionManager must be used as async context manager")

        await self._provider.refresh_if_needed()


def create_auth_provider(
    auth_type: str, credentials: AuthCredentials
) -> BasicAuthProvider | CookieAuthProvider | HeaderAuthProvider | OAuth2Provider:
    """Factory function to create auth provider based on type.

    Args:
        auth_type: Authentication type ("basic", "cookie", "header", "oauth2")
        credentials: Authentication credentials

    Returns:
        Configured AuthProvider instance (concrete implementation)

    Raises:
        ValueError: If auth_type is invalid

    Example:
        >>> credentials = AuthCredentials(username="user", password="pass")
        >>> provider = create_auth_provider("basic", credentials)
    """
    auth_type_lower = auth_type.lower()

    if auth_type_lower == "basic":
        return BasicAuthProvider(credentials)
    elif auth_type_lower == "cookie":
        return CookieAuthProvider(credentials)
    elif auth_type_lower == "header":
        return HeaderAuthProvider(credentials)
    elif auth_type_lower == "oauth2":
        return OAuth2Provider(credentials)
    else:
        raise ValueError(
            f"Invalid auth_type: {auth_type}. Must be one of: basic, cookie, header, oauth2"
        )
