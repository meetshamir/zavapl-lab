"""ServiceNow OAuth client and incident creation helpers for the demo simulator."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse

import requests


class ServiceNowError(RuntimeError):
    """Base error for actionable ServiceNow failures."""


class ServiceNowConfigurationError(ServiceNowError):
    """Raised when required environment configuration is missing or invalid."""


class ServiceNowAuthenticationError(ServiceNowError):
    """Raised when OAuth token acquisition fails."""


class ServiceNowAccessError(ServiceNowError):
    """Raised when the integration user lacks a required ACL."""


class ServiceNowUnavailableError(ServiceNowError):
    """Raised when the PDI is asleep, unavailable, or cannot be reached."""


class ServiceNowApiError(ServiceNowError):
    """Raised for an unexpected ServiceNow API response."""


def _read_env_file(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ServiceNowConfigurationError(
            f"Cannot read ServiceNow environment file {path}: {exc}"
        ) from exc

    values: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[7:].lstrip()
        key, separator, value = entry.partition("=")
        key = key.strip()
        if not separator or not key.replace("_", "").isalnum():
            raise ServiceNowConfigurationError(
                f"Invalid environment entry in {path} at line {line_number}."
            )
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class ServiceNowConfig:
    instance_url: str
    client_id: str
    client_secret: str
    token_url: str
    assignment_group_sys_id: str
    scope: Optional[str] = None

    @classmethod
    def from_environment(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        env_file: Optional[Path] = None,
    ) -> "ServiceNowConfig":
        if environ is None:
            path = env_file or Path(__file__).resolve().parents[1] / ".env"
            values = {**_read_env_file(path), **os.environ}
        else:
            values = environ
        required = {
            "SERVICENOW_INSTANCE_URL": values.get("SERVICENOW_INSTANCE_URL", "").strip(),
            "SERVICENOW_CLIENT_ID": values.get("SERVICENOW_CLIENT_ID", "").strip(),
            "SERVICENOW_CLIENT_SECRET": values.get("SERVICENOW_CLIENT_SECRET", "").strip(),
            "SERVICENOW_ASSIGNMENT_GROUP_SYS_ID": values.get(
                "SERVICENOW_ASSIGNMENT_GROUP_SYS_ID", ""
            ).strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ServiceNowConfigurationError(
                "Missing ServiceNow configuration: "
                + ", ".join(missing)
                + ". Copy .env.example into your secret environment store and set the values."
            )

        instance_url = required["SERVICENOW_INSTANCE_URL"].rstrip("/")
        parsed = urlparse(instance_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ServiceNowConfigurationError(
                "SERVICENOW_INSTANCE_URL must be an HTTPS origin such as "
                "https://dev442167.service-now.com."
            )

        token_url = values.get("SERVICENOW_TOKEN_URL", "").strip()
        if not token_url:
            token_url = f"{instance_url}/oauth_token.do"
        token_parsed = urlparse(token_url)
        if token_parsed.scheme != "https" or not token_parsed.netloc:
            raise ServiceNowConfigurationError(
                "SERVICENOW_TOKEN_URL must be an HTTPS URL when provided."
            )

        return cls(
            instance_url=instance_url,
            client_id=required["SERVICENOW_CLIENT_ID"],
            client_secret=required["SERVICENOW_CLIENT_SECRET"],
            token_url=token_url,
            assignment_group_sys_id=required["SERVICENOW_ASSIGNMENT_GROUP_SYS_ID"],
            scope=values.get("SERVICENOW_SCOPE", "").strip() or None,
        )


@dataclass(frozen=True)
class CreatedIncident:
    sys_id: str
    number: str


class ServiceNowClient:
    def __init__(
        self,
        config: ServiceNowConfig,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def acquire_token(self) -> str:
        form = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        if self.config.scope:
            form["scope"] = self.config.scope

        try:
            response = self.session.post(
                self.config.token_url,
                data=form,
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ServiceNowUnavailableError(
                "Could not reach the ServiceNow OAuth endpoint. Wake the PDI, verify "
                "SERVICENOW_INSTANCE_URL/SERVICENOW_TOKEN_URL, and check network access."
            ) from exc
        except requests.RequestException as exc:
            raise ServiceNowAuthenticationError(
                "The ServiceNow OAuth token request failed before a response was received."
            ) from exc

        if response.status_code in (401, 403):
            raise ServiceNowAuthenticationError(
                "ServiceNow rejected the OAuth client credentials. Verify the client ID, "
                "secret, client-credentials grant property, OAuth application user, and scope."
            )
        if response.status_code >= 500:
            raise ServiceNowUnavailableError(
                f"ServiceNow token endpoint returned HTTP {response.status_code}. "
                "The PDI may be asleep or unavailable."
            )
        if not 200 <= response.status_code < 300:
            raise ServiceNowAuthenticationError(
                f"ServiceNow token acquisition failed with HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceNowAuthenticationError(
                "ServiceNow token endpoint returned a non-JSON response."
            ) from exc
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ServiceNowAuthenticationError(
                "ServiceNow token response did not contain an access_token."
            )
        return token

    def create_incident(
        self,
        short_description: str,
        description: str,
        *,
        category: str = "software",
        impact: str = "2",
        urgency: str = "2",
    ) -> CreatedIncident:
        token = self.acquire_token()
        body = {
            "short_description": short_description,
            "description": description,
            "category": category,
            "impact": impact,
            "urgency": urgency,
            "assignment_group": self.config.assignment_group_sys_id,
        }
        try:
            response = self.session.post(
                f"{self.config.instance_url}/api/now/table/incident",
                json=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=self.timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ServiceNowUnavailableError(
                "Could not reach the ServiceNow Incident Table API. Wake the PDI and "
                "verify network access and the instance URL."
            ) from exc
        except requests.RequestException as exc:
            raise ServiceNowApiError(
                "The ServiceNow incident request failed before a response was received."
            ) from exc

        if response.status_code == 401:
            raise ServiceNowAuthenticationError(
                "ServiceNow rejected the bearer token while creating the incident."
            )
        if response.status_code == 403:
            raise ServiceNowAccessError(
                "ServiceNow denied incident creation. Grant the OAuth application user "
                "only the required incident table/field ACLs and assignment-group access."
            )
        if response.status_code >= 500:
            raise ServiceNowUnavailableError(
                f"ServiceNow Incident API returned HTTP {response.status_code}. "
                "The PDI may be asleep or unavailable."
            )
        if not 200 <= response.status_code < 300:
            raise ServiceNowApiError(
                f"ServiceNow incident creation failed with HTTP {response.status_code}."
            )

        try:
            result = response.json().get("result", {})
        except ValueError as exc:
            raise ServiceNowApiError(
                "ServiceNow Incident API returned a non-JSON response."
            ) from exc
        sys_id = result.get("sys_id")
        number = result.get("number")
        if not isinstance(sys_id, str) or not sys_id:
            raise ServiceNowApiError(
                "ServiceNow incident response did not contain result.sys_id."
            )
        if not isinstance(number, str) or not number:
            raise ServiceNowApiError(
                "ServiceNow incident response did not contain result.number."
            )
        return CreatedIncident(sys_id=sys_id, number=number)
