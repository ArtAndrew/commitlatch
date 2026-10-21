# Contributing

Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` from the repository
root. Runtime code uses only the Python standard library and targets Python 3.9+.

Every recovery change needs a test of the failure it addresses. Include the
provider-side effect count; a green local state alone is insufficient evidence.
Document all assumptions that make an external action safe to retry.

Keep UNKNOWN explicit. Do not change a timeout or a negative search result into
permission to execute. Do not introduce automatic retries, telemetry, or external
service calls into tests. Real-provider tests must be separate and use sandbox
credentials supplied by the operator.

Use synthetic examples in issues and reports. Do not submit customer data,
credentials or production action payloads.
