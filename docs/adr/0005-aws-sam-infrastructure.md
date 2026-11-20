# ADR 0005: AWS SAM as the infrastructure tool

## Status

Accepted (2026-11-19).

## Date

2026-11-19 (spec 001-create-baseline, task 2.8; requirement 4.1 (e)).

## Context

The backend is Python code that runs on AWS Lambda (ADR 0001) and the repository packages that code together with its infrastructure. The project needs one tool that describes the functions, their triggers and the resources around them, and that builds and packages the Lambda code. The project runs in two environments, `dev` and `prod`. Spec 001 builds no infrastructure.

## Decision

1. The infrastructure tool is the AWS Serverless Application Model (SAM). The template and its configuration are written in spec 002.
2. The Lambda runtime is Python 3.14 (`python3.14`), the newest generally available version; Python 3.15 is in public preview only and is not used (owner decision, 2026-11-19).
3. There are two environments, `dev` and `prod`, and no others.
4. SAM was chosen because the repository packages Lambda code: SAM builds and packages the functions and describes the resources in one template, with less to write and maintain than a general-purpose tool for this size of project.
5. Spec 001 contains no template and no SAM or CloudFormation CI job.

## Consequences

- The tool is tied to AWS; a move to another cloud would mean rewriting the infrastructure description.
- Resources that SAM does not cover well may need plain CloudFormation inside the same template.
- Open items, not decided here: the template, its CI jobs (SAM validation and CloudFormation linting) and the exact resources are decided in spec 002; deployment of `dev` is decided in spec 003; the AWS Region and the Bedrock model are decided in spec 002.

## Sources

- Owner decisions of 2026-11-19 (SAM, environments, Python 3.14).
- AWS Lambda runtimes (`python3.14` generally available on Amazon Linux 2023, projected deprecation 2029-06-30): https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html, consulted 2026-11-19.
- Python 3.15 public preview runtime (August 2026, no SLA, not for production): https://aws.amazon.com/about-aws/whats-new/2026/08/aws-lambda-node-js-python-public-preview/, consulted 2026-11-19.
