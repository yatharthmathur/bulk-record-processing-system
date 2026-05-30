from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from typing import ClassVar

from app.domain.exceptions import CsvValidationError
from app.domain.models import CsvValidationSummary, HospitalRow


class HospitalCsvParser:
    REQUIRED_HEADERS: ClassVar[tuple[str, str]] = ("name", "address")
    OPTIONAL_HEADERS: ClassVar[tuple[str]] = ("phone",)
    ALLOWED_HEADERS: ClassVar[tuple[str, str, str]] = (
        REQUIRED_HEADERS + OPTIONAL_HEADERS
    )

    def __init__(self, max_hospitals: int) -> None:
        self._max_hospitals: int = max_hospitals

    def parse(self, raw_content: bytes) -> list[HospitalRow]:
        text = self._decode(raw_content)
        reader = csv.DictReader(io.StringIO(text))
        columns = self._validate_headers(reader.fieldnames)

        hospitals: list[HospitalRow] = []
        errors: list[str] = []

        for row_number, raw_row in enumerate(reader, start=1):
            normalized = {
                column: (raw_row.get(column) or "").strip() for column in columns
            }
            if self._is_blank_row(normalized):
                continue

            name = normalized.get("name", "")
            address = normalized.get("address", "")
            phone = normalized.get("phone") or None

            if not name:
                errors.append(f"Row {row_number}: 'name' is required.")
            if not address:
                errors.append(f"Row {row_number}: 'address' is required.")

            hospitals.append(
                HospitalRow(
                    row=row_number,
                    name=name,
                    address=address,
                    phone=phone,
                )
            )

        if not hospitals:
            errors.append("CSV file must contain at least one hospital row.")

        if len(hospitals) > self._max_hospitals:
            errors.append(
                "CSV file contains "
                + f"{len(hospitals)} hospitals. Maximum allowed is "
                + f"{self._max_hospitals}."
            )

        if errors:
            raise CsvValidationError(errors)

        return hospitals

    def validate(self, raw_content: bytes) -> CsvValidationSummary:
        hospitals = self.parse(raw_content)
        return CsvValidationSummary(
            valid=True,
            total_hospitals=len(hospitals),
            max_hospitals=self._max_hospitals,
            columns=self.ALLOWED_HEADERS,
        )

    def _decode(self, raw_content: bytes) -> str:
        if not raw_content:
            raise CsvValidationError(["CSV file is empty."])

        try:
            return raw_content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CsvValidationError(["CSV file must be UTF-8 encoded."]) from exc

    def _validate_headers(self, headers: Sequence[str] | None) -> tuple[str, ...]:
        if headers is None:
            raise CsvValidationError(["CSV header row is missing."])

        normalized_headers = tuple((header or "").strip() for header in headers)
        valid_variants = [
            self.REQUIRED_HEADERS,
            self.ALLOWED_HEADERS,
        ]

        if normalized_headers not in valid_variants:
            raise CsvValidationError(
                [
                    "CSV headers must be exactly "
                    + "'name,address' or 'name,address,phone'.",
                ]
            )

        return normalized_headers

    @staticmethod
    def _is_blank_row(row: dict[str, str]) -> bool:
        return all(not value for value in row.values())
