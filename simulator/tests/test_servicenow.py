import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from simulator.servicenow import (
    ServiceNowAccessError,
    ServiceNowApiError,
    ServiceNowAuthenticationError,
    ServiceNowClient,
    ServiceNowConfig,
    ServiceNowConfigurationError,
    ServiceNowUnavailableError,
)


class FakeResponse:
    def __init__(self, status_code, payload=None, json_error=False):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise ValueError("not json")
        return self.payload


class FakeSession:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


def valid_environment():
    return {
        "SERVICENOW_INSTANCE_URL": "https://dev442167.service-now.com",
        "SERVICENOW_CLIENT_ID": "test-client",
        "SERVICENOW_CLIENT_SECRET": "test-secret",
        "SERVICENOW_ASSIGNMENT_GROUP_SYS_ID": "0123456789abcdef0123456789abcdef",
        "SERVICENOW_SCOPE": "zava_incident",
    }


class ServiceNowConfigTests(unittest.TestCase):
    def test_requires_all_secret_and_reference_configuration(self):
        with self.assertRaisesRegex(
            ServiceNowConfigurationError, "SERVICENOW_CLIENT_SECRET"
        ):
            ServiceNowConfig.from_environment(
                {"SERVICENOW_INSTANCE_URL": "https://dev442167.service-now.com"}
            )

    def test_uses_default_token_endpoint(self):
        config = ServiceNowConfig.from_environment(valid_environment())
        self.assertEqual(
            config.token_url,
            "https://dev442167.service-now.com/oauth_token.do",
        )

    def test_rejects_non_https_instance(self):
        environ = valid_environment()
        environ["SERVICENOW_INSTANCE_URL"] = "http://dev442167.service-now.com"
        with self.assertRaisesRegex(ServiceNowConfigurationError, "HTTPS origin"):
            ServiceNowConfig.from_environment(environ)

    def test_loads_dotenv_with_process_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "SERVICENOW_INSTANCE_URL=https://file-instance.service-now.com",
                        "SERVICENOW_CLIENT_ID=file-client",
                        "SERVICENOW_CLIENT_SECRET='file-secret'",
                        (
                            "SERVICENOW_ASSIGNMENT_GROUP_SYS_ID="
                            "0123456789abcdef0123456789abcdef"
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"SERVICENOW_INSTANCE_URL": "https://dev442167.service-now.com"},
                clear=True,
            ):
                config = ServiceNowConfig.from_environment(env_file=env_file)

        self.assertEqual(
            config.instance_url, "https://dev442167.service-now.com"
        )
        self.assertEqual(config.client_id, "file-client")
        self.assertEqual(config.client_secret, "file-secret")


class ServiceNowClientTests(unittest.TestCase):
    def setUp(self):
        self.config = ServiceNowConfig.from_environment(valid_environment())

    def test_token_request_uses_client_credentials_and_scope(self):
        session = FakeSession(
            [FakeResponse(200, {"access_token": "mock-access-token"})]
        )
        token = ServiceNowClient(self.config, session=session).acquire_token()

        self.assertEqual(token, "mock-access-token")
        url, request = session.calls[0]
        self.assertEqual(url, self.config.token_url)
        self.assertEqual(
            request["data"],
            {
                "grant_type": "client_credentials",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "scope": "zava_incident",
            },
        )

    def test_incident_creation_request_shape_and_sys_id_result(self):
        session = FakeSession(
            [
                FakeResponse(200, {"access_token": "mock-access-token"}),
                FakeResponse(
                    201,
                    {
                        "result": {
                            "sys_id": "fedcba9876543210fedcba9876543210",
                            "number": "INC0012345",
                        }
                    },
                ),
            ]
        )
        incident = ServiceNowClient(self.config, session=session).create_incident(
            "Test outage",
            "Synthetic incident created by an explicitly selected simulator scenario.",
            category="network",
            impact="1",
            urgency="2",
        )

        self.assertEqual(incident.number, "INC0012345")
        self.assertEqual(incident.sys_id, "fedcba9876543210fedcba9876543210")
        url, request = session.calls[1]
        self.assertEqual(
            url,
            "https://dev442167.service-now.com/api/now/table/incident",
        )
        self.assertEqual(
            request["json"],
            {
                "short_description": "Test outage",
                "description": (
                    "Synthetic incident created by an explicitly selected "
                    "simulator scenario."
                ),
                "category": "network",
                "impact": "1",
                "urgency": "2",
                "assignment_group": "0123456789abcdef0123456789abcdef",
            },
        )
        self.assertEqual(
            request["headers"]["Authorization"], "Bearer mock-access-token"
        )

    def test_token_rejection_is_actionable(self):
        session = FakeSession([FakeResponse(401, {})])
        with self.assertRaisesRegex(
            ServiceNowAuthenticationError, "client-credentials grant property"
        ):
            ServiceNowClient(self.config, session=session).acquire_token()

    def test_incident_acl_denial_is_actionable(self):
        session = FakeSession(
            [
                FakeResponse(200, {"access_token": "mock-access-token"}),
                FakeResponse(403, {}),
            ]
        )
        with self.assertRaisesRegex(ServiceNowAccessError, "table/field ACLs"):
            ServiceNowClient(self.config, session=session).create_incident(
                "Test", "Test"
            )

    def test_unavailable_instance_is_distinct(self):
        session = FakeSession(error=requests.ConnectionError("offline"))
        with self.assertRaisesRegex(ServiceNowUnavailableError, "Wake the PDI"):
            ServiceNowClient(self.config, session=session).acquire_token()

    def test_api_error_does_not_echo_response_body(self):
        session = FakeSession(
            [
                FakeResponse(200, {"access_token": "mock-access-token"}),
                FakeResponse(400, {"error": {"message": "sensitive detail"}}),
            ]
        )
        with self.assertRaisesRegex(ServiceNowApiError, "HTTP 400") as raised:
            ServiceNowClient(self.config, session=session).create_incident(
                "Test", "Test"
            )
        self.assertNotIn("sensitive detail", str(raised.exception))

    def test_malformed_incident_response_is_reported(self):
        session = FakeSession(
            [
                FakeResponse(200, {"access_token": "mock-access-token"}),
                FakeResponse(201, {"result": {"number": "INC0012345"}}),
            ]
        )
        with self.assertRaisesRegex(ServiceNowApiError, "result.sys_id"):
            ServiceNowClient(self.config, session=session).create_incident(
                "Test", "Test"
            )


if __name__ == "__main__":
    unittest.main()
