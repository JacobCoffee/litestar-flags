# Security Policy

## Supported Versions

We actively support security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

Once we reach 1.0.0, we will maintain a clearer LTS (Long Term Support) policy.

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability within litestar-flags, please report it responsibly.

### Preferred Method: GitHub Security Advisories

1. Go to the [Security tab](https://github.com/JacobCoffee/litestar-flags/security) of this repository
2. Click "Report a vulnerability"
3. Fill out the security advisory form with details about the vulnerability

This method ensures:
- Private communication until a fix is available
- Coordinated disclosure
- Credit for responsible disclosure
- CVE assignment if applicable

### Alternative: Email

If you cannot use GitHub Security Advisories, you may email security concerns to:
- **Email**: jacob@z7x.org
- **Subject**: `[SECURITY] litestar-flags: <brief description>`

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (if available)

### What to Expect

1. **Acknowledgment**: We will acknowledge receipt of your report within 48 hours
2. **Assessment**: We will assess the vulnerability and determine its severity within 7 days
3. **Updates**: We will keep you informed of our progress
4. **Resolution**: We aim to release patches for critical vulnerabilities within 30 days
5. **Credit**: We will credit you in the release notes (unless you prefer anonymity)

### Severity Classifications

We use the following severity levels:

- **Critical**: Remote code execution, authentication bypass, data exposure
- **High**: Privilege escalation, significant information disclosure
- **Medium**: Limited impact vulnerabilities, denial of service
- **Low**: Minor issues with limited security impact

## Security Best Practices for Users

When using litestar-flags in your applications, follow these guidelines:

### Protecting Targeting Keys

Targeting keys (user IDs, etc.) may contain sensitive information. Use the built-in security utilities:

```python
from litestar_flags.security import hash_targeting_key, sanitize_log_context

# Hash targeting keys in logs
hashed_key = hash_targeting_key(user_id)

# Sanitize context before logging
safe_context = sanitize_log_context(evaluation_context.to_dict())
logger.info("Flag evaluated", extra=safe_context)
```

### Configuration Security

1. **Environment Variables**: Store sensitive configuration in environment variables
2. **Secrets Management**: Use your platform's secrets manager for Redis/database credentials
3. **Least Privilege**: Use database accounts with minimal required permissions

### Network Security

1. **TLS/SSL**: Always use encrypted connections to Redis and databases in production
2. **Network Isolation**: Keep storage backends on private networks when possible
3. **Firewall Rules**: Restrict access to storage backends to application servers only

### Input Validation

1. **Flag Keys**: Flag keys should be validated before use
2. **Context Attributes**: User-provided context attributes should be sanitized
3. **Rule Conditions**: Avoid using user input directly in rule conditions

### Logging and Monitoring

1. **Audit Logs**: Enable audit logging for flag changes in production
2. **Anomaly Detection**: Monitor for unusual flag evaluation patterns
3. **Access Logs**: Track who modifies flags and when

### Example Secure Configuration

```python
import os
from litestar_flags import FeatureFlagsConfig

# Secure production configuration
config = FeatureFlagsConfig(
    backend="redis",
    backend_options={
        "url": os.environ["REDIS_URL"],  # Use environment variable
        "ssl": True,  # Enable TLS
    },
    enable_middleware=True,
    audit_logging=True,  # Enable audit logs
)
```

## Known Security Considerations

### Rule Evaluation

- **Regex Patterns**: The `matches` operator uses Python's `re` module. Complex regex patterns could potentially cause ReDoS (Regular Expression Denial of Service). Avoid using untrusted regex patterns in rules.

### Information Disclosure

- **Error Messages**: Error messages do not expose internal system details by default
- **Flag Names**: Flag keys and names may be exposed to clients; avoid using sensitive information in flag identifiers

### Storage Security

- **Memory Backend**: The memory backend stores data in process memory; data is lost on restart and not suitable for production
- **Redis Backend**: Redis does not encrypt data at rest by default; consider using encrypted Redis or Redis Enterprise for sensitive data
- **Database Backend**: Use database-level encryption for sensitive flag configurations

## Security Features

### Built-in Protections

1. **Input Sanitization**: Flag keys and rule attributes are validated
2. **Type Safety**: Pydantic models enforce type constraints
3. **Logging Redaction**: Security utilities help redact sensitive data from logs
4. **No Arbitrary Code Execution**: Rule evaluation does not execute arbitrary code

### Security Utilities

The `litestar_flags.security` module provides:

- `hash_targeting_key()`: Hash sensitive identifiers for logging
- `sanitize_log_context()`: Remove sensitive fields from log data
- `SENSITIVE_FIELDS`: List of fields considered sensitive

## Changelog

### Security Updates

Track security-related updates in our [CHANGELOG.md](CHANGELOG.md) with entries prefixed with `[Security]`.

## Contact

For non-security-related issues, please use [GitHub Issues](https://github.com/JacobCoffee/litestar-flags/issues).

For security vulnerabilities, please use the methods described above.

---

Thank you for helping keep litestar-flags and its users secure!
