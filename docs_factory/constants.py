"""Shared text and deterministic settings for Docs Factory."""

TOOL_NAME = "Docs Factory"
DETERMINISTIC_SEED = 0
HONESTY_BOUNDARY = (
    "Docs Factory generates documentation only for fictional synthetic fixture repos. "
    "It reads static Python evidence and fills deterministic templates; no language model "
    "writes the prose. No real open-source project has been documented by this tool."
)


def honesty_markdown() -> str:
    return (
        "> **HONESTY BOUNDARY:** This page was generated for a fictional synthetic fixture. "
        "Docs Factory reads static evidence and fills deterministic templates; no language "
        "model writes this prose. No real open-source project has been documented by this tool."
    )
