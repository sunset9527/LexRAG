# Security policy

LexRAG is an educational legal-information system and is not currently represented as production-ready.

## Reporting a vulnerability

Do not open a public issue for a suspected credential leak, authorization bypass, SSRF path, cross-organization access, unsafe upload path, or sensitive-data logging issue. Contact the repository owner privately with:

- affected commit or release;
- reproduction steps and minimal proof of impact;
- whether real personal, legal, or credential data was involved.

Do not include API keys, JWTs, uploaded documents, legal consultation text, or private database records in the report. Acknowledgement, triage, remediation, and public disclosure timing are agreed case by case.

## Supported baseline

Security fixes target the current `main` branch. Reported findings are assessed against the documented local-demo and Docker boundaries; real production deployment assurance remains a Stage 8 validation item.
