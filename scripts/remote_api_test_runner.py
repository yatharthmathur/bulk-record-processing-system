from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias, TypeGuard, cast
from uuid import uuid4

import httpx

BASE_URL = "https://bulk-record-processing-system.onrender.com"
REPORTS_DIR = Path("reports")
TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 1.0
MAX_POLL_ATTEMPTS = 40

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(slots=True)
class CaseResult:
    name: str
    passed: bool
    summary: str
    request_description: str
    expected: str
    actual_status_code: int | None
    actual_response: JSONValue


def is_json_object(value: JSONValue) -> TypeGuard[JSONObject]:
    return isinstance(value, dict)


def to_pretty_json(payload: JSONValue) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def parse_response(response: httpx.Response) -> JSONValue:
    try:
        return cast(JSONValue, response.json())
    except ValueError:
        return response.text


def post_csv(client: httpx.Client, filename: str, content: str) -> httpx.Response:
    return client.post(
        "/hospitals/bulk",
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
    )


def require_json_object(payload: JSONValue, *, context: str) -> JSONObject:
    if not is_json_object(payload):
        raise TypeError(f"Expected JSON object for {context}.")
    return payload


def poll_batch_until_finished(client: httpx.Client, batch_id: str) -> httpx.Response:
    latest_response: httpx.Response | None = None
    for _ in range(MAX_POLL_ATTEMPTS):
        latest_response = client.get(f"/batches/{batch_id}")
        payload = parse_response(latest_response)
        if is_json_object(payload) and payload.get("status") in {
            "completed",
            "partial_failure",
            "activation_failed",
        }:
            return latest_response
        time.sleep(POLL_INTERVAL_SECONDS)

    if latest_response is None:
        raise RuntimeError("Batch polling did not execute any requests.")
    return latest_response


def run() -> list[CaseResult]:
    results: list[CaseResult] = []
    with httpx.Client(
        base_url=BASE_URL,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        health = client.get("/health")
        health_payload = parse_response(health)
        results.append(
            CaseResult(
                name="health_check",
                passed=health.status_code == 200
                and is_json_object(health_payload)
                and health_payload.get("status") == "ok",
                summary="Health endpoint responds successfully.",
                request_description="GET /health",
                expected="200 with status=ok",
                actual_status_code=health.status_code,
                actual_response=health_payload,
            )
        )

        unique_suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        valid_single_csv = (
            "name,address,phone\n"
            f"Remote Test General {unique_suffix},123 Integration Street,555-0001\n"
        )
        submit_single = post_csv(client, "valid-single.csv", valid_single_csv)
        submit_single_payload = parse_response(submit_single)
        single_submit_object: JSONObject | None = None
        single_passed = submit_single.status_code == 202 and is_json_object(
            submit_single_payload
        )
        if single_passed:
            single_submit_object = require_json_object(
                submit_single_payload,
                context="single-row submit response",
            )

        final_single_payload: JSONValue = None
        final_single_status_code: int | None = None
        if single_submit_object is not None:
            batch_id = str(single_submit_object["batch_id"])
            final_single = poll_batch_until_finished(client, batch_id)
            final_single_status_code = final_single.status_code
            final_single_payload = parse_response(final_single)
            single_passed = (
                final_single.status_code == 200
                and is_json_object(final_single_payload)
                and final_single_payload.get("status") == "completed"
                and final_single_payload.get("processed_hospitals") == 1
                and final_single_payload.get("failed_hospitals") == 0
            )
        results.append(
            CaseResult(
                name="bulk_create_single_valid_row",
                passed=single_passed,
                summary=(
                    "Single-row CSV is accepted, queued, and eventually completed."
                ),
                request_description=(
                    "POST /hospitals/bulk then poll GET /batches/{batch_id}"
                ),
                expected=(
                    "202 on submit, then 200 completed batch with 1 processed hospital"
                ),
                actual_status_code=final_single_status_code
                or submit_single.status_code,
                actual_response={
                    "submit": submit_single_payload,
                    "final": final_single_payload,
                },
            )
        )

        valid_two_rows_csv = (
            "name,address\n"
            f"Remote Test Clinic A {unique_suffix},10 Queue Road\n"
            f"Remote Test Clinic B {unique_suffix},11 Queue Road\n"
        )
        submit_two = post_csv(client, "valid-two.csv", valid_two_rows_csv)
        submit_two_payload = parse_response(submit_two)
        two_submit_object: JSONObject | None = None
        two_passed = submit_two.status_code == 202 and is_json_object(
            submit_two_payload
        )
        if two_passed:
            two_submit_object = require_json_object(
                submit_two_payload,
                context="two-row submit response",
            )

        final_two_payload: JSONValue = None
        final_two_status_code: int | None = None
        if two_submit_object is not None:
            batch_id = str(two_submit_object["batch_id"])
            final_two = poll_batch_until_finished(client, batch_id)
            final_two_status_code = final_two.status_code
            final_two_payload = parse_response(final_two)
            two_passed = (
                final_two.status_code == 200
                and is_json_object(final_two_payload)
                and final_two_payload.get("status") == "completed"
                and final_two_payload.get("processed_hospitals") == 2
                and final_two_payload.get("failed_hospitals") == 0
            )
        results.append(
            CaseResult(
                name="bulk_create_two_rows_without_phone_column",
                passed=two_passed,
                summary=(
                    "CSV without the optional phone column is accepted and processed."
                ),
                request_description=(
                    "POST /hospitals/bulk with name,address header then poll batch"
                ),
                expected=(
                    "202 on submit, then 200 completed batch with 2 processed hospitals"
                ),
                actual_status_code=final_two_status_code or submit_two.status_code,
                actual_response={
                    "submit": submit_two_payload,
                    "final": final_two_payload,
                },
            )
        )

        duplicate_csv = (
            "name,address,phone\n"
            f"Remote Dedup Test {unique_suffix},456 Duplicate Lane,555-0002\n"
        )
        first_duplicate = post_csv(client, "duplicate-a.csv", duplicate_csv)
        second_duplicate = post_csv(client, "duplicate-b.csv", duplicate_csv)
        first_duplicate_payload = parse_response(first_duplicate)
        second_duplicate_payload = parse_response(second_duplicate)
        first_duplicate_object: JSONObject | None = None
        duplicate_passed = (
            first_duplicate.status_code == 202
            and second_duplicate.status_code == 202
            and is_json_object(first_duplicate_payload)
            and is_json_object(second_duplicate_payload)
        )
        if duplicate_passed:
            first_duplicate_object = require_json_object(
                first_duplicate_payload,
                context="first duplicate submit response",
            )
            second_duplicate_object = require_json_object(
                second_duplicate_payload,
                context="second duplicate submit response",
            )
            duplicate_passed = (
                first_duplicate_object["batch_id"]
                == second_duplicate_object["batch_id"]
            )

        final_duplicate_payload: JSONValue = None
        final_duplicate_status_code: int | None = None
        resubmit_duplicate_payload: JSONValue = None
        if duplicate_passed and first_duplicate_object is not None:
            batch_id = str(first_duplicate_object["batch_id"])
            final_duplicate = poll_batch_until_finished(client, batch_id)
            final_duplicate_status_code = final_duplicate.status_code
            final_duplicate_payload = parse_response(final_duplicate)
            duplicate_passed = (
                final_duplicate.status_code == 200
                and is_json_object(final_duplicate_payload)
                and final_duplicate_payload.get("status") == "completed"
                and final_duplicate_payload.get("processed_hospitals") == 1
                and final_duplicate_payload.get("failed_hospitals") == 0
            )

            resubmit_duplicate = post_csv(
                client, "duplicate-resubmit.csv", duplicate_csv
            )
            resubmit_duplicate_payload = parse_response(resubmit_duplicate)
            if duplicate_passed and is_json_object(resubmit_duplicate_payload):
                duplicate_passed = (
                    resubmit_duplicate.status_code == 202
                    and resubmit_duplicate_payload["batch_id"] != batch_id
                )
            else:
                duplicate_passed = False

        results.append(
            CaseResult(
                name="duplicate_in_flight_upload_returns_same_batch",
                passed=duplicate_passed,
                summary=(
                    "Identical CSV uploads while in-flight deduplicate to one batch; "
                    "after completion the same file can be submitted again."
                ),
                request_description=(
                    "POST /hospitals/bulk twice with identical CSV bytes, poll batch, "
                    "then POST the same CSV again"
                ),
                expected=(
                    "Both initial submits return 202 with the same batch_id; polled "
                    "batch completes once; third submit returns 202 with a new batch_id"
                ),
                actual_status_code=final_duplicate_status_code
                or second_duplicate.status_code,
                actual_response={
                    "first_submit": first_duplicate_payload,
                    "second_submit": second_duplicate_payload,
                    "final": final_duplicate_payload,
                    "resubmit_after_terminal": resubmit_duplicate_payload,
                },
            )
        )

        invalid_header = post_csv(
            client,
            "invalid-header.csv",
            "hospital_name,address\nBad Hospital,Unknown Street\n",
        )
        invalid_header_payload = parse_response(invalid_header)
        results.append(
            CaseResult(
                name="invalid_csv_header",
                passed=invalid_header.status_code == 422
                and is_json_object(invalid_header_payload)
                and "detail" in invalid_header_payload,
                summary="Bulk endpoint rejects a CSV with invalid headers.",
                request_description=(
                    "POST /hospitals/bulk with hospital_name,address header"
                ),
                expected="422 with validation details",
                actual_status_code=invalid_header.status_code,
                actual_response=invalid_header_payload,
            )
        )

        missing_required = post_csv(
            client,
            "missing-required.csv",
            "name,address\nHospital Missing Address,\n",
        )
        missing_required_payload = parse_response(missing_required)
        results.append(
            CaseResult(
                name="invalid_csv_missing_required_field",
                passed=missing_required.status_code == 422
                and is_json_object(missing_required_payload)
                and "detail" in missing_required_payload,
                summary="Bulk endpoint rejects rows missing required values.",
                request_description="POST /hospitals/bulk with blank address",
                expected="422 with row-specific validation detail",
                actual_status_code=missing_required.status_code,
                actual_response=missing_required_payload,
            )
        )

        over_limit_rows = (
            "name,address\n"
            + "\n".join(f"Hospital {index},Address {index}" for index in range(1, 22))
            + "\n"
        )
        over_limit = post_csv(client, "over-limit.csv", over_limit_rows)
        over_limit_payload = parse_response(over_limit)
        results.append(
            CaseResult(
                name="invalid_csv_over_20_rows",
                passed=over_limit.status_code == 422
                and is_json_object(over_limit_payload)
                and "detail" in over_limit_payload,
                summary="Bulk endpoint enforces the maximum 20-hospital limit.",
                request_description="POST /hospitals/bulk with 21 rows",
                expected="422 with max-row validation detail",
                actual_status_code=over_limit.status_code,
                actual_response=over_limit_payload,
            )
        )

        unknown_batch = client.get(f"/batches/{uuid4()}")
        unknown_batch_payload = parse_response(unknown_batch)
        results.append(
            CaseResult(
                name="unknown_batch_id",
                passed=unknown_batch.status_code == 404
                and is_json_object(unknown_batch_payload)
                and "detail" in unknown_batch_payload,
                summary="Unknown batch IDs return not found.",
                request_description="GET /batches/{random_uuid}",
                expected="404 with batch not found detail",
                actual_status_code=unknown_batch.status_code,
                actual_response=unknown_batch_payload,
            )
        )

        invalid_batch_id = client.get("/batches/not-a-uuid")
        invalid_batch_id_payload = parse_response(invalid_batch_id)
        results.append(
            CaseResult(
                name="invalid_batch_id_format",
                passed=invalid_batch_id.status_code == 422,
                summary=(
                    "Invalid UUID path parameters are rejected by FastAPI validation."
                ),
                request_description="GET /batches/not-a-uuid",
                expected="422 validation error",
                actual_status_code=invalid_batch_id.status_code,
                actual_response=invalid_batch_id_payload,
            )
        )

    return results


def build_report(results: list[CaseResult]) -> str:
    generated_at = datetime.now(UTC).isoformat()
    passed_count = sum(1 for result in results if result.passed)
    lines: list[str] = []
    lines.append("# Remote API Testing Report")
    lines.append("")
    lines.append(f"- Target: `{BASE_URL}`")
    lines.append(f"- Generated at (UTC): `{generated_at}`")
    lines.append(f"- Total cases: `{len(results)}`")
    lines.append(f"- Passed: `{passed_count}`")
    lines.append(f"- Failed: `{len(results) - passed_count}`")
    lines.append("")
    lines.append(
        "> Note: valid bulk-create cases create real upstream hospital "
        + "records via the deployed service."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Case | Result | HTTP Status | Summary |")
    lines.append("| --- | --- | --- | --- |")

    for result in results:
        status_code = (
            "n/a"
            if result.actual_status_code is None
            else str(result.actual_status_code)
        )
        icon = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| `{result.name}` | {icon} | `{status_code}` | {result.summary} |"
        )

    for result in results:
        lines.append("")
        lines.append(f"## Case: `{result.name}`")
        lines.append("")
        lines.append(f"- Result: **{'PASS' if result.passed else 'FAIL'}**")
        lines.append(f"- Request: `{result.request_description}`")
        lines.append(f"- Expected: {result.expected}")
        lines.append(f"- Actual HTTP status: `{result.actual_status_code}`")
        lines.append("")
        lines.append("### Response")
        lines.append("")
        lines.append("```json")
        lines.append(to_pretty_json(result.actual_response))
        lines.append("```")

    return "\n".join(lines) + "\n"


def build_report_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return REPORTS_DIR / f"remote-api-test-report-{timestamp}.md"


if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    case_results = run()
    report_path = build_report_path()
    _ = report_path.write_text(build_report(case_results), encoding="utf-8")
    print(report_path)
