from __future__ import annotations

from app.application.services.csv_parser import CsvHospitalParser
from app.domain.models import CsvValidationSummary


class ValidateCsvUseCase:
    def __init__(self, csv_parser: CsvHospitalParser) -> None:
        self._csv_parser: CsvHospitalParser = csv_parser

    def execute(self, raw_csv: bytes) -> CsvValidationSummary:
        return self._csv_parser.validate(raw_csv)
