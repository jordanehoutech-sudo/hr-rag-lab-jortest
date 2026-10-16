# HR policy assistant: evaluation and delivery

An AWS HR application with a React frontend, Python backend, authenticated policy retrieval, LiteLLM model routing, Langfuse tracing and automated release evaluations.

## Start here

Follow [the complete setup and delivery guide](docs/HR-LAB-START-TO-FINISH.md) in order. It includes repository import, automated AWS setup, Langfuse, Cognito, GitHub-to-AWS access, workflow code, evaluation results, failure exercises and implementation references.

Import this public repository into your own GitHub account before cloning. Your copy must own its Actions settings, environments and secrets. The guide provides the exact steps.

## What the repository provides

- `frontend/`: the React application.
- `lambda/`: the Python backend, versioned prompt, synthetic employee/policy data and reference cases.
- `infra/terraform/`: infrastructure for initial setup, including the private model gateway.
- `scripts/`: automated application setup and configuration helpers.
- `ci/`: authenticated API tests, evaluation adapters, deployment and reporting helpers.
- `docs/HR-LAB-START-TO-FINISH.md`: the single project walkthrough.

The starter contains no active GitHub Actions workflow. Create it using the code inside the guide. Model and tool permissions remain enforced by the backend; evaluation scores do not grant access.

## Delivery boundary

Reviewed changes deploy to one synthetic staging environment. Required evaluation failures block release approval. The production handoff is a dry run; it does not provision a separate production stack or move production traffic.
