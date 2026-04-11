# Security

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly.
**Do not open a public GitHub issue.**

Instead, email the maintainers directly or use GitHub's private vulnerability
reporting feature.

## Security Design

This lab uses the following security practices:

- **Managed Identity** for all service-to-service authentication
- **No secrets in code** — all credentials via Azure Key Vault or `azd env`
- **RBAC** for all Azure resource access
- **Entra ID** for authentication throughout
- Container images pulled via Managed Identity (AcrPull role)

## Important Notes

- This is a **demo lab** — do not use it for production workloads
- The break/fix scenarios intentionally introduce failures
- Always run `azd down --purge` when done to clean up resources
- ServiceNow developer instances are free but should not contain real data
