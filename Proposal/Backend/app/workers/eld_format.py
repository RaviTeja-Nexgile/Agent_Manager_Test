"""ELD / eRODS output-file decoding and extraction (BRD Appendix E, §8.7).

Pure functions: no database, no filesystem, no HTTP. Everything here takes bytes
or text plus a resolved mapping and returns an :class:`ExtractionResult` — which
makes the whole extraction unit-testable without a session and lets the same code
back both the background parse (``workers.tasks.parse_eld_file``) and the
synchronous pre-upload validation endpoint.

Two file shapes are supported.

**FMCSA standard output file** (49 CFR 395 Appendix A to Subpart B). This is what
a driver actually transfers to eRODS and what an MCSAP CMV Inspector saves at
roadside: a *sectioned* CSV, not a table. A file header segment identifies the
driver, co-driver, carrier, power unit, VIN, time-zone offset, ELD registration
and the **Output File Comment** — the field the study asks drivers/carriers to
carry the CCFP code in. After it come the User List, CMV List, ELD Event List,
event annotations, driver certifications, malfunction/diagnostic events, the
login/logout report, engine power-up/shut-down activity, unidentified-driver
records and an end-of-file check value.

**Flat CSV**: a single header row of tabular hours-of-service rows, mapped
through the configurable ``eld_field_mappings`` / ``eld_duty_code_mappings``
tables (RECO-5). This is the shape the parser understood before and it keeps
working byte-for-byte.

Nothing fails silently. Every decode fallback, unrecognized section, unmappable
column, unparseable value, duplicate sequence number, truncation and deadline
overrun is recorded on an :class:`IssueLog` with a stable code, a message that
names the fix, and the offending line. Issues are *aggregated by code* so a
50,000-row file with one systematically bad column yields one issue with an
occurrence count and sample lines rather than 50,000 rows.
"""
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import io
import re
import time
from typing import Any, Iterable, Sequence

from app.enums import DutyStatus, EldFileFormat, EldIssueSeverity

# ---------------------------------------------------------------------------
# Limits. Kept as module constants (overridable per call) so a future phase can
# raise them from configuration without touching the parsing logic (§3.4).
# ---------------------------------------------------------------------------
#: Largest upload accepted. An ELD output file for a driver's 8-day record is
#: kilobytes; megabytes means a wrong file was picked.
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
#: Largest number of events stored from one file. Exceeding it is reported as an
#: ERROR (never a silent truncation).
DEFAULT_MAX_EVENTS = 200_000
#: Wall-clock budget for one extraction. Exceeding it is reported as an ERROR.
DEFAULT_TIME_BUDGET_SECONDS = 120.0
#: Sample line numbers / values retained per aggregated issue.
MAX_ISSUE_SAMPLES = 20
#: Longest single CSV field accepted (guards a pathological quoted field).
MAX_FIELD_SIZE = 1 * 1024 * 1024


# ---------------------------------------------------------------------------
# Stable issue / error codes. Referenced by tests, the API and the UI, so they
# are part of the contract — add, do not rename.
# ---------------------------------------------------------------------------
class EldErrorCode:
    EMPTY_FILE = "ELD_EMPTY_FILE"
    TOO_LARGE = "ELD_FILE_TOO_LARGE"
    BINARY_FORMAT = "ELD_BINARY_FORMAT"
    UNDECODABLE = "ELD_UNDECODABLE"
    NOT_TABULAR = "ELD_NOT_TABULAR"
    NO_DATA_ROWS = "ELD_NO_DATA_ROWS"
    NO_MAPPABLE_COLUMNS = "ELD_NO_MAPPABLE_COLUMNS"
    NO_EVENTS_EXTRACTED = "ELD_NO_EVENTS_EXTRACTED"
    CSV_MALFORMED = "ELD_CSV_MALFORMED"
    TRUNCATED = "ELD_TRUNCATED"
    TIME_BUDGET_EXCEEDED = "ELD_TIME_BUDGET_EXCEEDED"
    OBJECT_UNREADABLE = "ELD_OBJECT_UNREADABLE"
    INTERNAL = "ELD_INTERNAL_ERROR"

    # Non-blocking (WARNING / INFO) diagnostics.
    ENCODING_FALLBACK = "ELD_ENCODING_FALLBACK"
    ENCODING_REPLACED = "ELD_ENCODING_REPLACED"
    NUL_BYTES_STRIPPED = "ELD_NUL_BYTES_STRIPPED"
    NO_CCFP_CODE = "ELD_NO_CCFP_CODE"
    DUPLICATE_HEADER = "ELD_DUPLICATE_HEADER"
    RAGGED_ROW = "ELD_RAGGED_ROW"
    BLANK_ROW = "ELD_BLANK_ROW"
    BAD_SEQUENCE = "ELD_BAD_SEQUENCE"
    BAD_TIMESTAMP = "ELD_BAD_TIMESTAMP"
    MISSING_TIMESTAMP = "ELD_MISSING_TIMESTAMP"
    BAD_NUMBER = "ELD_BAD_NUMBER"
    BAD_COORDINATE = "ELD_BAD_COORDINATE"
    COORDINATE_UNAVAILABLE = "ELD_COORDINATE_UNAVAILABLE"
    UNMAPPED_DUTY_CODE = "ELD_UNMAPPED_DUTY_CODE"
    UNKNOWN_EVENT_CODE = "ELD_UNKNOWN_EVENT_CODE"
    DUPLICATE_SEQUENCE = "ELD_DUPLICATE_SEQUENCE"
    UNRECOGNIZED_SECTION = "ELD_UNRECOGNIZED_SECTION"
    SECTION_UNMAPPED = "ELD_SECTION_UNMAPPED"
    SECTION_EMPTY = "ELD_SECTION_EMPTY"
    HEADER_FIELD_MISSING = "ELD_HEADER_FIELD_MISSING"
    HEADER_POSITIONAL = "ELD_HEADER_POSITIONAL"
    NO_TIME_ZONE = "ELD_NO_TIME_ZONE"
    NO_HEADER_SEGMENT = "ELD_NO_HEADER_SEGMENT"
    ANNOTATION_UNMATCHED = "ELD_ANNOTATION_UNMATCHED"
    INACTIVE_RECORDS = "ELD_INACTIVE_RECORDS"


class EldParseError(Exception):
    """A blocking failure: the file cannot yield events at all.

    Carries a stable ``code`` plus a ``message`` written for the person who
    uploaded the file — the upload endpoint returns it as a 400 detail and the
    worker stores it on ``eld_files.error_code`` / ``error_message``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        # Diagnostics gathered before the blocking failure (encoding fallback,
        # stripped NUL bytes, ...). Attached by `extract` so a FAILED file still
        # shows everything the parser learned, not just the fatal line.
        self.issues: list[Issue] = []


# ---------------------------------------------------------------------------
# Issue collection
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class Issue:
    severity: str
    code: str
    message: str
    section: str | None = None
    line_number: int | None = None
    column_name: str | None = None
    raw_value: str | None = None
    occurrences: int = 1
    details: dict[str, Any] = dataclasses.field(default_factory=dict)


class IssueLog:
    """Aggregating collector: one entry per (code, section, column).

    The first occurrence supplies the line number, raw value and message; later
    occurrences bump ``occurrences`` and contribute sample lines/values up to
    ``MAX_ISSUE_SAMPLES``. This keeps a pathological file's diagnostics complete
    in kind (every distinct problem is reported) while bounded in volume.
    """

    def __init__(self, max_samples: int = MAX_ISSUE_SAMPLES) -> None:
        self._by_key: dict[tuple[str, str | None, str | None], Issue] = {}
        self._order: list[tuple[str, str | None, str | None]] = []
        self._max_samples = max_samples

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        *,
        section: str | None = None,
        line_number: int | None = None,
        column_name: str | None = None,
        raw_value: Any = None,
    ) -> None:
        key = (code, section, column_name)
        raw = None if raw_value is None else str(raw_value)[:200]
        existing = self._by_key.get(key)
        if existing is None:
            issue = Issue(
                severity=severity, code=code, message=message, section=section,
                line_number=line_number, column_name=column_name, raw_value=raw,
                details={
                    "sample_lines": [line_number] if line_number is not None else [],
                    "sample_values": [raw] if raw is not None else [],
                },
            )
            self._by_key[key] = issue
            self._order.append(key)
            return
        existing.occurrences += 1
        # Severity is monotonic: if the same code later proves blocking, keep the
        # worse severity so a summary count never understates the problem.
        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[existing.severity]:
            existing.severity = severity
            existing.message = message
        samples = existing.details.setdefault("sample_lines", [])
        if line_number is not None and len(samples) < self._max_samples:
            samples.append(line_number)
        values = existing.details.setdefault("sample_values", [])
        if raw is not None and len(values) < self._max_samples:
            values.append(raw)

    def error(self, code: str, message: str, **kw: Any) -> None:
        self.add(EldIssueSeverity.ERROR.value, code, message, **kw)

    def warning(self, code: str, message: str, **kw: Any) -> None:
        self.add(EldIssueSeverity.WARNING.value, code, message, **kw)

    def info(self, code: str, message: str, **kw: Any) -> None:
        self.add(EldIssueSeverity.INFO.value, code, message, **kw)

    def issues(self) -> list[Issue]:
        return [self._by_key[k] for k in self._order]

    def count(self, severity: str) -> int:
        """Total OCCURRENCES at a severity (not the number of aggregated rows)."""
        return sum(i.occurrences for i in self._by_key.values() if i.severity == severity)

    @property
    def error_count(self) -> int:
        return self.count(EldIssueSeverity.ERROR.value)

    @property
    def warning_count(self) -> int:
        return self.count(EldIssueSeverity.WARNING.value)

    def has_errors(self) -> bool:
        return any(i.severity == EldIssueSeverity.ERROR.value for i in self._by_key.values())

    def first_error(self) -> Issue | None:
        for key in self._order:
            issue = self._by_key[key]
            if issue.severity == EldIssueSeverity.ERROR.value:
                return issue
        return None


_SEVERITY_RANK = {
    EldIssueSeverity.INFO.value: 0,
    EldIssueSeverity.WARNING.value: 1,
    EldIssueSeverity.ERROR.value: 2,
}


# ---------------------------------------------------------------------------
# Extracted shapes
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class EldEventRow:
    """One extracted event, shaped for the ``eld_events`` table."""

    event_sequence: int
    line_number: int | None = None
    section: str | None = None
    event_timestamp: dt.datetime | None = None
    duty: str | None = None
    event_type: str | None = None
    event_type_code: int | None = None
    event_code: int | None = None
    record_status: str | None = None
    record_origin: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    miles_driven: float | None = None
    engine_hours: float | None = None
    distance_since_last_coords: float | None = None
    ignition_status: str | None = None
    malfunction_indicator: str | None = None
    diagnostic_indicator: str | None = None
    annotation: str | None = None
    driver_identifier: str | None = None
    cmv_identifier: str | None = None
    data_check_value: str | None = None
    is_duplicate: bool = False
    raw: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ExtractionResult:
    file_format: str
    encoding: str
    delimiter: str
    line_count: int
    row_count: int
    events: list[EldEventRow]
    header: dict[str, Any]
    sections: dict[str, int]
    ccfp_code: str | None
    hos_summary: dict[str, Any]
    issues: list[Issue]
    error_count: int
    warning_count: int
    truncated: bool = False

    @property
    def has_errors(self) -> bool:
        return any(i.severity == EldIssueSeverity.ERROR.value for i in self.issues)

    def first_error(self) -> Issue | None:
        for issue in self.issues:
            if issue.severity == EldIssueSeverity.ERROR.value:
                return issue
        return None


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------
#: Leading byte signatures of formats an ELD output file is often confused with.
#: Detected up-front so the uploader is told "this is a PDF" rather than watching
#: the parser mangle binary into rows of garbage.
_BINARY_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "PDF document", "Export the ELD output file as CSV from eRODS or the ELD provider portal."),
    (b"PK\x03\x04", "ZIP archive or Office document (.xlsx/.docx)",
     "If this is a spreadsheet, use File > Save As > CSV and upload the .csv file."),
    (b"\xd0\xcf\x11\xe0", "legacy Microsoft Office document (.xls/.doc)",
     "Save the workbook as CSV and upload the .csv file."),
    (b"\x1f\x8b", "gzip archive", "Decompress the archive and upload the .csv file inside it."),
    (b"\x89PNG", "PNG image", "Upload the ELD output file itself, not a screenshot."),
    (b"\xff\xd8\xff", "JPEG image", "Upload the ELD output file itself, not a photo of it."),
    (b"SQLite format 3", "SQLite database", "Export the hours-of-service records to CSV first."),
    (b"{\\rtf", "RTF document", "Save the report as CSV and upload the .csv file."),
)

#: BOM -> codec. Excel's "Unicode text" export is UTF-16-LE with a BOM and used
#: to decode to mojibake under a blind utf-8 read.
_BOM_CODECS: tuple[tuple[bytes, str], ...] = (
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xff\xfe", "utf-16-le"),
)


def detect_binary_format(content: bytes) -> tuple[str, str] | None:
    """Return ``(format_name, remedy)`` when the payload is a known non-CSV file."""
    head = content[:64]
    for signature, name, remedy in _BINARY_SIGNATURES:
        if head.startswith(signature):
            return name, remedy
    return None


def decode_payload(content: bytes, issues: IssueLog | None = None) -> tuple[str, str]:
    """Decode ELD bytes to text, returning ``(text, encoding_name)``.

    Order: BOM-declared codec, UTF-8, then the Windows/Latin single-byte codecs
    an ELD vendor export realistically uses. A fallback is *reported*, never
    assumed — the previous implementation decoded everything as UTF-8 with
    ``errors="replace"``, which turned a UTF-16 or CP1252 file into replacement
    characters and produced a "successful" parse of nonsense.
    """
    if not content:
        raise EldParseError(
            EldErrorCode.EMPTY_FILE,
            "The uploaded file is empty (0 bytes). Re-export the ELD output file "
            "from eRODS or the ELD provider portal and upload it again.",
        )

    binary = detect_binary_format(content)
    if binary:
        name, remedy = binary
        raise EldParseError(
            EldErrorCode.BINARY_FORMAT,
            f"The uploaded file is a {name}, not an ELD output CSV. {remedy}",
        )

    for bom, codec in _BOM_CODECS:
        if content.startswith(bom):
            try:
                text = content.decode(codec)
            except UnicodeDecodeError as exc:
                raise EldParseError(
                    EldErrorCode.UNDECODABLE,
                    f"The file declares a {codec} byte-order mark but its bytes are not "
                    f"valid {codec} (at byte {exc.start}). Re-export the ELD output file as CSV.",
                ) from exc
            if issues is not None and codec != "utf-8-sig":
                issues.info(
                    EldErrorCode.ENCODING_FALLBACK,
                    f"File decoded as {codec} from its byte-order mark. UTF-8 is the "
                    "expected encoding for an ELD output CSV.",
                )
            return text, codec

    try:
        return content.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    # A UTF-16 file without a BOM shows as alternating NUL bytes. Detect it
    # before the single-byte codecs, which would "succeed" into interleaved NULs.
    sample = content[:4096]
    if sample.count(b"\x00") > len(sample) // 3:
        for codec in ("utf-16-le", "utf-16-be"):
            try:
                text = content.decode(codec)
            except UnicodeDecodeError:
                continue
            if issues is not None:
                issues.warning(
                    EldErrorCode.ENCODING_FALLBACK,
                    f"File is not valid UTF-8; decoded as {codec} (no byte-order mark). "
                    "Re-export as UTF-8 CSV if characters look wrong.",
                )
            return text, codec

    for codec in ("cp1252", "latin-1"):
        try:
            text = content.decode(codec)
        except UnicodeDecodeError:
            continue
        if issues is not None:
            issues.warning(
                EldErrorCode.ENCODING_FALLBACK,
                f"File is not valid UTF-8; decoded as {codec}. Non-ASCII characters "
                "(names, city names) may not be exact — re-export as UTF-8 CSV to be sure.",
            )
        return text, codec

    # latin-1 maps every byte, so reaching here means the payload is unusable.
    raise EldParseError(
        EldErrorCode.UNDECODABLE,
        "The file could not be decoded as text in any supported encoding "
        "(UTF-8, UTF-16, CP1252, Latin-1). Re-export the ELD output file as a CSV.",
    )


def preflight(content: bytes, file_name: str | None = None, *, max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
    """Reject uploads that cannot possibly be an ELD output CSV.

    Runs synchronously in the upload request so the uploader gets an immediate,
    specific 400 instead of a file that lands in the system and quietly fails
    minutes later. Only *structural* impossibility is rejected here (empty,
    oversize, binary, undecodable, no delimiter-separated content at all) —
    anything that depends on the per-study/provider column mapping is decided by
    the real extraction, whose diagnostics are stored against the file.
    """
    if len(content) > max_bytes:
        raise EldParseError(
            EldErrorCode.TOO_LARGE,
            f"The uploaded file is {len(content) / (1024 * 1024):.1f} MB, above the "
            f"{max_bytes // (1024 * 1024)} MB limit for an ELD output file. Confirm you "
            "selected the ELD output CSV and not a full data export.",
        )
    text, _ = decode_payload(content)
    stripped = text.replace("\x00", "").strip()
    if not stripped:
        raise EldParseError(
            EldErrorCode.EMPTY_FILE,
            "The uploaded file contains no text. Re-export the ELD output file from "
            "eRODS or the ELD provider portal and upload it again.",
        )
    if not any(d in stripped for d in (",", ";", "\t", "|")):
        suffix = f" ({file_name})" if file_name else ""
        raise EldParseError(
            EldErrorCode.NOT_TABULAR,
            f"The uploaded file{suffix} has no delimited columns, so it is not an ELD "
            "output CSV. Upload the CSV produced by eRODS or the ELD provider.",
        )


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def norm(key: str | None) -> str:
    """Lowercase, collapse non-alphanumerics to ``_``. ``None`` -> ``""``.

    Shared with ``workers.tasks`` so configured ``source_header`` values, the
    parser's own alias tables and the file's actual headers agree exactly.
    """
    if key is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


#: A CCFP code carried in an ELD output-file comment (RECO-2). Matches the
#: ``CCFP-<year>-<STATE>-<seq>`` identifier shape without pinning a state or year.
CCFP_CODE_RE = re.compile(r"\bCCFP-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b")

#: Normalized column names that can carry the output-file comment on a data row.
CCFP_COMMENT_COLUMNS = ("output_file_comment", "ccfp_code", "comment", "file_comment")

_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_USDOT_RE = re.compile(r"(?:us\s*dot|usdot|dot)\D{0,12}(\d{1,8})", re.IGNORECASE)


def extract_ccfp_code(text: str | None) -> str | None:
    """First CCFP code token in a blob of ELD text, or ``None``."""
    if not text:
        return None
    match = CCFP_CODE_RE.search(text)
    return match.group(0) if match else None


def sniff_delimiter(text: str, issues: IssueLog | None = None) -> str:
    """Pick the delimiter by counting candidates on the first non-blank lines.

    ``csv.Sniffer`` throws on the sectioned ELD layout (section title lines have
    no delimiter at all), so this counts instead: the candidate appearing most
    often across the sample wins, ties break toward the comma the spec uses.
    """
    sample_lines = [ln for ln in text.splitlines()[:50] if ln.strip()]
    if not sample_lines:
        return ","
    counts = {d: sum(ln.count(d) for ln in sample_lines) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: (counts[d], d == ","))
    if counts[best] == 0:
        return ","
    if best != "," and issues is not None:
        label = {";": "semicolon", "\t": "tab", "|": "pipe"}[best]
        issues.info(
            EldErrorCode.ENCODING_FALLBACK,
            f"File uses a {label} delimiter rather than the comma the ELD output-file "
            "standard specifies; parsed accordingly.",
        )
    return best


def _read_rows(text: str, delimiter: str, issues: IssueLog) -> list[tuple[int, list[str]]]:
    """Split the payload into ``(line_number, cells)`` with the csv module.

    Line numbers are 1-based over the ORIGINAL file so an issue can point the
    uploader at a line they can open in a text editor. A quoted field spanning
    several physical lines advances the counter by the lines it consumed, which
    ``csv.reader.line_num`` tracks for us.
    """
    csv.field_size_limit(MAX_FIELD_SIZE)
    if "\x00" in text:
        text = text.replace("\x00", "")
        issues.warning(
            EldErrorCode.NUL_BYTES_STRIPPED,
            "The file contained NUL bytes, which are not valid in a CSV. They were "
            "removed before parsing — check the export settings on the ELD device.",
        )
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows: list[tuple[int, list[str]]] = []
    previous_line = 0
    while True:
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            # A malformed quote sequence kills the rest of the stream; report the
            # line and stop rather than pretending the file ended cleanly.
            issues.error(
                EldErrorCode.CSV_MALFORMED,
                f"The file is not valid CSV at line {previous_line + 1}: {exc}. "
                "Check for an unbalanced quote character and re-export the file.",
                line_number=previous_line + 1,
            )
            break
        rows.append((previous_line + 1, [c.strip() for c in cells]))
        previous_line = reader.line_num
    return rows


# ---------------------------------------------------------------------------
# FMCSA section recognition
# ---------------------------------------------------------------------------
#: ``section key -> pattern matched against the normalized single-cell title``.
#: Order matters: the first match wins, so more specific patterns come first.
_SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("HEADER", re.compile(r"^(eld_)?(file_)?header(_segment)?$")),
    ("USER_LIST", re.compile(r"^(eld_)?user(s)?_list$")),
    ("CMV_LIST", re.compile(r"^(cmv|vehicle)(s)?_list$")),
    ("UNIDENTIFIED_DRIVER", re.compile(r"unidentified")),
    ("EVENT_ANNOTATIONS", re.compile(r"annotation|(^|_)comment")),
    ("CERTIFICATIONS", re.compile(r"certif")),
    ("MALFUNCTIONS", re.compile(r"malfunction|diagnostic")),
    ("LOGIN_LOGOUT", re.compile(r"log_?in|log_?out")),
    ("ENGINE_POWER", re.compile(r"power_?up|power_?down|shut_?down|engine_power")),
    ("EVENT_LIST", re.compile(r"^(eld_)?event(s)?(_list)?$|event_list")),
    ("END_OF_FILE", re.compile(r"^end_of_file$|file_data_check")),
)

#: Sections whose rows become ``eld_events``.
_EVENT_SECTIONS = frozenset(
    {"EVENT_LIST", "UNIDENTIFIED_DRIVER", "ENGINE_POWER", "LOGIN_LOGOUT",
     "MALFUNCTIONS", "CERTIFICATIONS"}
)

_SECTION_LABELS = {
    "HEADER": "ELD File Header Segment",
    "USER_LIST": "User List",
    "CMV_LIST": "CMV List",
    "EVENT_LIST": "ELD Event List",
    "EVENT_ANNOTATIONS": "Event Annotations or Comments",
    "CERTIFICATIONS": "Driver's Certification/Recertification Actions",
    "MALFUNCTIONS": "Malfunction and Data Diagnostic Events",
    "LOGIN_LOGOUT": "ELD Login/Logout Report",
    "ENGINE_POWER": "CMV Engine Power-Up and Shut-Down Activity",
    "UNIDENTIFIED_DRIVER": "Unidentified Driver Records",
    "END_OF_FILE": "End of File",
}


def _section_title(cells: Sequence[str]) -> str | None:
    """Return the section key when ``cells`` is a section title line.

    A title line carries exactly one non-empty cell (``ELD Event List:`` or
    ``ELD Event List:,,,,`` — trailing empty cells are normal when a vendor pads
    every line to the widest row) whose text matches a known section name. A
    ``#``-prefixed line is a comment, never a title, and a long cell is prose
    (an output-file comment carrying the CCFP code) rather than a section name.
    """
    non_empty = [c for c in cells if c.strip()]
    if len(non_empty) != 1:
        return None
    text = non_empty[0].strip()
    if text.startswith("#") or len(text) > 60 or CCFP_CODE_RE.search(text):
        return None
    key = norm(text.rstrip(":").strip())
    if not key:
        return None
    for name, pattern in _SECTION_PATTERNS:
        if pattern.search(key):
            return name
    return None


# ---------------------------------------------------------------------------
# ELD event vocabulary (49 CFR 395 Appendix A to Subpart B)
# ---------------------------------------------------------------------------
EVENT_TYPE_NAMES = {
    1: "DUTY_STATUS_CHANGE",
    2: "INTERMEDIATE_LOG",
    3: "PERSONAL_USE_YARD_MOVE",
    4: "CERTIFICATION",
    5: "LOGIN_LOGOUT",
    6: "ENGINE_POWER",
    7: "MALFUNCTION_DIAGNOSTIC",
}

#: Event type 1 (duty-status change) event codes -> canonical DutyStatus.
_DUTY_BY_EVENT_CODE = {
    1: DutyStatus.OFF_DUTY.value,
    2: DutyStatus.SLEEPER_BERTH.value,
    3: DutyStatus.DRIVING.value,
    4: DutyStatus.ON_DUTY_NOT_DRIVING.value,
}
#: Event type 3 (driver's indication of personal conveyance / yard moves).
#: Personal conveyance is recorded while off duty; a yard move is on-duty
#: not-driving. Code 0 clears the indication and asserts no duty status.
_DUTY_BY_PC_YM_CODE = {
    1: DutyStatus.OFF_DUTY.value,
    2: DutyStatus.ON_DUTY_NOT_DRIVING.value,
}

RECORD_STATUS_NAMES = {
    1: "ACTIVE",
    2: "INACTIVE_CHANGED",
    3: "INACTIVE_CHANGE_REQUESTED",
    4: "INACTIVE_CHANGE_REJECTED",
}
RECORD_ORIGIN_NAMES = {
    1: "AUTOMATIC",
    2: "DRIVER_EDIT",
    3: "OTHER_USER_EDIT",
    4: "UNIDENTIFIED_DRIVER",
}
#: Event type 6 codes -> ignition state.
_IGNITION_BY_POWER_CODE = {1: "POWER_UP", 2: "POWER_UP", 3: "SHUT_DOWN", 4: "SHUT_DOWN"}

#: Canonical field -> header aliases for every event-bearing section. Covers the
#: spec's column names plus the abbreviations vendors ship. Values are ``norm``ed.
_EVENT_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "event_sequence": (
        "event_sequence_id_number", "event_sequence_id", "event_sequence",
        "sequence_id_number", "sequence_number", "sequence_id", "event_seq",
        "sequence", "seq_no", "seq", "line", "line_number", "record_number",
    ),
    "record_status": ("event_record_status", "record_status", "status_code"),
    "record_origin": ("event_record_origin", "record_origin", "origin"),
    "event_type_code": ("event_type", "event_type_code", "type_code"),
    "event_code": ("event_code", "eventcode", "status", "duty_status_code"),
    "event_date": ("event_date", "date", "record_date", "log_date"),
    "event_time": ("event_time", "time", "record_time", "log_time"),
    "event_timestamp": ("event_timestamp", "timestamp", "datetime", "date_time"),
    "miles_driven": (
        "accumulated_vehicle_miles", "total_vehicle_miles", "accumulated_miles",
        "vehicle_miles", "miles_driven", "odometer", "miles",
    ),
    "engine_hours": (
        "elapsed_engine_hours", "total_engine_hours", "engine_hours", "engine_hrs",
    ),
    "latitude": ("event_latitude", "latitude", "lat", "gps_lat"),
    "longitude": ("event_longitude", "longitude", "lon", "lng", "long", "gps_lng", "gps_lon"),
    "distance_since_last_coords": (
        "distance_since_last_valid_coordinates", "distance_since_last_valid_coords",
        "distance_since_last_coordinates", "dslc",
    ),
    "cmv_identifier": (
        "cmv_order_number", "cmv_power_unit_number", "cmv_number", "cmv_id",
        "vehicle_id", "power_unit_number", "truck_number", "tractor_number",
    ),
    "driver_identifier": (
        "user_order_number", "driver_id", "driver_identifier", "user_id",
        "username", "driver_username",
    ),
    "malfunction_indicator": (
        "malfunction_indicator_status", "malfunction_indicator", "malfunction_status",
    ),
    "diagnostic_indicator": (
        "data_diagnostic_event_indicator_status", "data_diagnostic_indicator_status",
        "data_diagnostic_indicator", "diagnostic_indicator", "diagnostic_status",
    ),
    "data_check_value": (
        "event_data_check_value", "line_data_check_value", "data_check_value", "check_value",
    ),
    "location": (
        "event_location_description", "location_description", "event_location",
        "location", "geo_location", "city_state", "place",
    ),
    "annotation": (
        "event_comment_annotation", "comment_annotation", "annotation", "event_comment",
        "comment", "remark", "note",
    ),
    "ignition_status": ("ignition_status", "ignition", "power_state"),
}

#: The ELD Event List / Unidentified Driver Records column order from the spec,
#: used when a section carries data rows but no recognizable header row.
_EVENT_POSITIONAL_ORDER: tuple[str, ...] = (
    "event_sequence", "record_status", "record_origin", "event_type_code", "event_code",
    "event_date", "event_time", "miles_driven", "engine_hours", "latitude", "longitude",
    "distance_since_last_coords", "cmv_identifier", "driver_identifier",
    "malfunction_indicator", "diagnostic_indicator", "data_check_value",
)

#: Header-segment field -> label aliases (``norm``ed).
_HEADER_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "driver_last_name": ("driver_last_name", "drivers_last_name", "last_name"),
    "driver_first_name": ("driver_first_name", "drivers_first_name", "first_name"),
    "driver_name": ("driver_name", "drivers_name", "driver"),
    "driver_license_state": (
        "driver_license_state", "drivers_license_state", "license_state", "cdl_state",
        "driver_s_license_state",
    ),
    "driver_license_number": (
        "driver_license_number", "drivers_license_number", "license_number", "cdl_number",
        "driver_s_license_number", "cdl",
    ),
    "co_driver_name": ("co_driver_name", "co_driver", "codriver_name", "codriver"),
    "co_driver_last_name": ("co_driver_last_name", "codriver_last_name"),
    "co_driver_first_name": ("co_driver_first_name", "codriver_first_name"),
    "carrier_name": ("carrier_name", "motor_carrier_name", "carrier"),
    "carrier_usdot": (
        "carrier_usdot_number", "usdot_number", "us_dot_number", "usdot", "dot_number",
        "current_carrier_usdot_number",
    ),
    "vin": ("vin", "vehicle_vin", "cmv_vin", "current_vehicle_vin", "vehicle_identification_number"),
    "power_unit_number": (
        "cmv_power_unit_number", "power_unit_number", "current_vehicle_cmv_power_unit_number",
        "truck_number", "unit_number",
    ),
    "trailer_numbers": ("trailer_number", "trailer_numbers", "current_trailer_numbers", "trailers"),
    "time_zone_offset": (
        "time_zone_offset_from_utc", "time_zone_offset", "timezone_offset", "utc_offset", "tz_offset",
    ),
    "shipping_document_number": ("shipping_document_number", "shipping_doc", "bol_number"),
    "eld_registration_id": ("eld_registration_id", "registration_id", "eld_registration"),
    "eld_identifier": ("eld_identifier", "eld_id", "eld_provider_identifier"),
    "eld_provider": ("eld_provider", "provider", "eld_manufacturer", "manufacturer"),
    "eld_authentication_value": ("eld_authentication_value", "authentication_value"),
    "output_file_comment": ("output_file_comment", "file_comment", "comment", "ccfp_code"),
    "multiday_basis": ("multiday_basis_used", "multiday_basis", "multi_day_basis"),
    "period_start_time": ("24_hour_period_starting_time", "period_starting_time", "period_start_time"),
    "record_date": ("current_date", "date_of_record", "report_date", "date"),
    "file_data_check_value": ("file_data_check_value", "file_check_value", "data_check_value"),
}

#: Positional layout of the spec's header segment, used when the block carries no
#: labels at all. Recorded as an INFO issue when applied, so a mis-shaped vendor
#: header is visible rather than silently mis-assigned.
_HEADER_POSITIONAL_LINES: tuple[tuple[str, ...], ...] = (
    ("driver_last_name", "driver_first_name", "driver_username", "driver_license_state", "driver_license_number"),
    ("co_driver_last_name", "co_driver_first_name", "co_driver_username"),
    ("power_unit_number", "vin", "trailer_numbers"),
    ("carrier_usdot", "carrier_name", "multiday_basis", "period_start_time", "time_zone_offset"),
    ("record_date", "eld_registration_id", "eld_identifier", "eld_authentication_value", "output_file_comment"),
)

#: Header fields worth an explicit "not found" note when absent — the ones an
#: analyst needs to tie hours-of-service data to the crash.
_EXPECTED_HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("driver_name", "driver name"),
    ("carrier_name", "carrier name"),
    ("carrier_usdot", "carrier U.S. DOT number"),
    ("vin", "vehicle identification number (VIN)"),
    ("time_zone_offset", "time-zone offset from UTC"),
)


# ---------------------------------------------------------------------------
# Value parsers
# ---------------------------------------------------------------------------
_DATE_FORMATS = ("%m%d%y", "%m%d%Y", "%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%Y%m%d", "%d-%b-%Y", "%m-%d-%Y")
_TIME_FORMATS = ("%H%M%S", "%H:%M:%S", "%H%M", "%H:%M", "%H:%M:%S.%f")
_TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M",
    "%Y-%m-%dT%H:%M", "%Y%m%d%H%M%S",
)


def parse_timestamp(value: str | None) -> dt.datetime | None:
    """Parse a whole timestamp string; ``None`` when it matches no known format."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+0000"
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    # Last resort: ISO-8601 variants strptime does not enumerate (offsets with a
    # colon, fractional seconds).
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_date_time(date_value: str | None, time_value: str | None) -> dt.datetime | None:
    """Combine the spec's separate ``MMDDYY`` date and ``HHMMSS`` time fields."""
    if not date_value:
        return None
    date_text = str(date_value).strip()
    parsed_date: dt.date | None = None
    for fmt in _DATE_FORMATS:
        try:
            parsed_date = dt.datetime.strptime(date_text, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        return None
    time_text = (str(time_value).strip() if time_value else "")
    parsed_time = dt.time(0, 0, 0)
    if time_text:
        for fmt in _TIME_FORMATS:
            try:
                parsed_time = dt.datetime.strptime(time_text, fmt).time()
                break
            except ValueError:
                continue
        else:
            return None
    return dt.datetime.combine(parsed_date, parsed_time)


#: Values the ELD rule allows in a coordinate field when a real fix is absent:
#: ``X`` = position unavailable (reduced precision / personal conveyance),
#: ``M`` = position could not be captured because of a malfunction, ``E`` = a
#: coordinate entry error.
_COORDINATE_SENTINELS = {"X", "M", "E", "N/A", "NA", "-", "--", "UNKNOWN"}


def parse_coordinate(value: str | None, *, is_latitude: bool) -> tuple[float | None, str | None]:
    """Parse an ELD coordinate. Returns ``(value, sentinel)``.

    Accepts a signed decimal (``-93.1234``) and the hemisphere-suffixed form the
    spec uses (``41.2345N`` / ``93.1234W``). A recognized sentinel comes back as
    ``(None, sentinel)`` so the caller can log "position unavailable" rather than
    "unparseable"; anything else unparseable is ``(None, None)``.
    """
    if value is None:
        return None, None
    text = str(value).strip().upper()
    if not text:
        return None, None
    if text in _COORDINATE_SENTINELS:
        return None, text
    hemisphere = ""
    if text[-1] in "NSEW":
        hemisphere, text = text[-1], text[:-1].strip()
    try:
        number = float(text)
    except ValueError:
        return None, None
    if hemisphere in ("S", "W"):
        number = -abs(number)
    elif hemisphere in ("N", "E"):
        number = abs(number)
    limit = 90.0 if is_latitude else 180.0
    if not -limit <= number <= limit:
        return None, None
    return number, None


def parse_number(value: Any) -> float | None:
    """Parse a decimal, tolerating thousands separators and a trailing unit."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.match(r"^[+-]?\d*\.?\d+", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


#: PostgreSQL INTEGER bounds. A value outside them is rejected rather than
#: written, so a junk column cannot abort the whole file with a database error.
_INT32_MIN, _INT32_MAX = -(2 ** 31), 2 ** 31 - 1
#: NUMERIC(10,2) bound for the mileage / engine-hour / distance columns.
_NUMERIC_10_2_MAX = 99_999_999.99


def parse_int(value: Any) -> int | None:
    """Parse an integer code; accepts the spec's hexadecimal sequence numbers.

    Returns ``None`` for anything outside PostgreSQL's INTEGER range so a corrupt
    column degrades to "unusable value" (reported, row still stored) instead of
    an integer-overflow error that would fail the entire upload.
    """
    if value is None:
        return None
    text = str(value).strip()
    parsed: int | None = None
    if not text:
        return None
    try:
        parsed = int(text, 10)
    except ValueError:
        if re.fullmatch(r"[0-9A-Fa-f]{1,8}", text):
            try:
                parsed = int(text, 16)
            except ValueError:
                parsed = None
        else:
            match = re.match(r"^[+-]?\d+", text)
            parsed = int(match.group(0)) if match else None
    if parsed is None or not (_INT32_MIN <= parsed <= _INT32_MAX):
        return None
    return parsed


def parse_tz_offset(value: str | None) -> int | None:
    """Interpret the header's "Time Zone Offset from UTC" as whole hours.

    The ELD rule records the offset as the number of hours to SUBTRACT from UTC
    to obtain the driver's home-terminal time (5 for Eastern Standard Time), so
    UTC = local + offset. ``-05:00``/``UTC-5`` forms are accepted too and
    normalized to the same sign convention.
    """
    if value is None:
        return None
    text = str(value).strip().upper().replace("UTC", "").replace("GMT", "").strip()
    if not text:
        return None
    match = re.match(r"^([+-]?)(\d{1,2})(?::?(\d{2}))?$", text)
    if not match:
        return None
    sign, hours, _minutes = match.groups()
    offset = int(hours)
    if offset > 14:
        return None
    # A leading '-' is the ISO form (UTC-05:00) — the same zone the spec writes
    # as a bare 5, so both normalize to +5 "hours behind UTC".
    return offset if sign != "+" else -offset


# ---------------------------------------------------------------------------
# Header-segment extraction
# ---------------------------------------------------------------------------
def _extract_header(block: list[tuple[int, list[str]]], issues: IssueLog) -> dict[str, Any]:
    """Pull identifiers out of the ELD file header segment.

    Labelled layouts win (``Carrier Name,ACME Trucking`` or
    ``Carrier Name: ACME Trucking`` in one cell); a wholly unlabelled block falls
    back to the spec's positional layout, which is recorded as an INFO issue so
    the interpretation is never invisible. Pattern extraction (CCFP code, VIN,
    U.S. DOT) then fills anything still missing, and the raw lines are kept so
    no header content is discarded.
    """
    header: dict[str, Any] = {}
    label_lookup = {alias: field for field, aliases in _HEADER_LABEL_ALIASES.items() for alias in aliases}
    raw_lines: list[str] = []
    # Cell indices already claimed by an explicit label, per header line. The
    # positional fallback below skips exactly those cells rather than the whole
    # line: a real export commonly labels only the Output File Comment and leaves
    # the rest of that same line positional.
    consumed: dict[int, set[int]] = {}

    for position, (_line_no, cells) in enumerate(block):
        raw_lines.append(", ".join(c for c in cells))
        claimed = consumed.setdefault(position, set())
        index = 0
        while index < len(cells):
            cell = cells[index].strip()
            if not cell:
                index += 1
                continue
            inline = re.split(r"\s*[:=]\s*", cell, maxsplit=1)
            if len(inline) == 2 and inline[1].strip():
                field = label_lookup.get(norm(inline[0]))
                if field:
                    header.setdefault(field, inline[1].strip())
                    claimed.add(index)
                    index += 1
                    continue
            field = label_lookup.get(norm(cell.rstrip(":")))
            if field:
                value = ""
                probe = index + 1
                while probe < len(cells) and not cells[probe].strip():
                    probe += 1
                if probe < len(cells):
                    value = cells[probe].strip()
                if value:
                    header.setdefault(field, value)
                    claimed.update(range(index, probe + 1))
                    index = probe + 1
                    continue
            index += 1

    # The spec's header segment is positional. Every cell no label claimed is
    # read by its position in the 49 CFR 395 Appendix A layout; `setdefault`
    # means an explicit label always wins over the positional guess.
    positional_used = False
    for position, ((_line_no, cells), fields) in enumerate(zip(block, _HEADER_POSITIONAL_LINES)):
        claimed = consumed.get(position, set())
        for index, (field, cell) in enumerate(zip(fields, cells)):
            if index in claimed or not cell.strip():
                continue
            header.setdefault(field, cell.strip())
            positional_used = True
    if positional_used:
        issues.info(
            EldErrorCode.HEADER_POSITIONAL,
            "Part of the ELD file header segment carries no field labels; those lines were read "
            "using the column order defined by 49 CFR 395 Appendix A. Verify the driver, carrier "
            "and vehicle values shown against the source file.",
            section="HEADER",
            line_number=block[0][0] if block else None,
        )

    blob = "\n".join(raw_lines)
    if not header.get("output_file_comment"):
        code = extract_ccfp_code(blob)
        if code:
            header["output_file_comment"] = code
    if not header.get("vin"):
        vin_match = _VIN_RE.search(blob.upper())
        if vin_match:
            header["vin"] = vin_match.group(0)
    if not header.get("carrier_usdot"):
        dot_match = _USDOT_RE.search(blob)
        if dot_match:
            header["carrier_usdot"] = dot_match.group(1)

    # Compose the display names the eld_files columns hold.
    if not header.get("driver_name"):
        first, last = header.get("driver_first_name"), header.get("driver_last_name")
        if first or last:
            header["driver_name"] = " ".join(p for p in (first, last) if p)
    if not header.get("co_driver_name"):
        first, last = header.get("co_driver_first_name"), header.get("co_driver_last_name")
        if first or last:
            header["co_driver_name"] = " ".join(p for p in (first, last) if p)

    header["raw_lines"] = raw_lines
    for field, label in _EXPECTED_HEADER_FIELDS:
        if not header.get(field):
            issues.info(
                EldErrorCode.HEADER_FIELD_MISSING,
                f"The ELD file header segment does not carry a {label}; that value is "
                "blank on the crash record and must be supplied another way if it is "
                "needed for analysis.",
                section="HEADER",
                column_name=field,
            )
    return header


# ---------------------------------------------------------------------------
# Event-row mapping
# ---------------------------------------------------------------------------
#: Column names that only ever appear in the User List / CMV List headers. Those
#: two sections carry few columns, so they need their own vocabulary to tell a
#: header row from the first user/vehicle row.
_LIST_HEADER_TOKENS = frozenset({
    "user_order_number", "user_last_name", "user_first_name", "account_type",
    "driver_account_type", "user_id", "username",
    "cmv_order_number", "cmv_power_unit_number", "vin", "cmv_vin", "trailer_number",
})


def _looks_like_header_row(cells: Sequence[str], *, extra_tokens: frozenset[str] = frozenset()) -> bool:
    """True when the row names columns rather than carrying data.

    A header row is mostly non-numeric text that matches known column aliases; a
    spec data row is nearly all numbers. Requiring two alias hits keeps a data
    row whose first cell happens to be text from being eaten as a header —
    ``extra_tokens`` widens the vocabulary for sections (User List, CMV List)
    whose columns are not event fields.
    """
    known = {alias for aliases in _EVENT_HEADER_ALIASES.values() for alias in aliases} | set(extra_tokens)
    normalized = [norm(c) for c in cells if c.strip()]
    if not normalized:
        return False
    hits = sum(1 for c in normalized if c in known)
    return hits >= 2 and hits >= len(normalized) // 3


def _map_headers(cells: Sequence[str], issues: IssueLog, section: str, line_number: int) -> dict[str, int]:
    """Map a section's header row to ``canonical field -> column index``."""
    alias_lookup: dict[str, str] = {}
    for field, aliases in _EVENT_HEADER_ALIASES.items():
        for alias in aliases:
            alias_lookup.setdefault(alias, field)
    mapping: dict[str, int] = {}
    seen: set[str] = set()
    for index, cell in enumerate(cells):
        key = norm(cell)
        if not key:
            continue
        if key in seen:
            issues.warning(
                EldErrorCode.DUPLICATE_HEADER,
                f"Column '{cell}' appears more than once in the {_SECTION_LABELS.get(section, section)} "
                "header; the first occurrence was used.",
                section=section, line_number=line_number, column_name=cell,
            )
            continue
        seen.add(key)
        field = alias_lookup.get(key)
        if field and field not in mapping:
            mapping[field] = index
    return mapping


def _cell(cells: Sequence[str], mapping: dict[str, int], field: str) -> str | None:
    index = mapping.get(field)
    if index is None or index >= len(cells):
        return None
    value = cells[index].strip()
    return value or None


class _EventBuilder:
    """Turns mapped cells into an :class:`EldEventRow`, logging every rejection."""

    def __init__(self, issues: IssueLog, tz_offset_hours: int | None) -> None:
        self.issues = issues
        self.tz_offset_hours = tz_offset_hours

    def _apply_tz(self, moment: dt.datetime | None) -> dt.datetime | None:
        """Resolve an event's wall-clock reading to an absolute instant.

        With a header offset, the ELD rule records it as the hours to SUBTRACT
        from UTC to get home-terminal time, so UTC = local + offset. Without one,
        the reading is anchored to UTC rather than left naive: a naive value would
        be interpreted in whatever time zone the database session happens to be
        in, which makes the same file extract to a different instant on a
        differently-configured server. That is exactly the kind of silent,
        invisible difference this work exists to remove — the anchoring choice is
        recorded as an ELD_NO_TIME_ZONE issue on the file.
        """
        if moment is None or moment.tzinfo is not None:
            return moment
        if self.tz_offset_hours is not None:
            moment = moment + dt.timedelta(hours=self.tz_offset_hours)
        return moment.replace(tzinfo=dt.timezone.utc)

    def _number(self, raw: str | None, field: str, section: str, line_number: int) -> float | None:
        if raw is None:
            return None
        value = parse_number(raw)
        if value is None:
            self.issues.warning(
                EldErrorCode.BAD_NUMBER,
                f"Could not read a number from the '{field}' column; the value was stored as blank. "
                "Check the export for a units suffix or a locale decimal separator.",
                section=section, line_number=line_number, column_name=field, raw_value=raw,
            )
        elif abs(value) > _NUMERIC_10_2_MAX:
            # Outside the column's NUMERIC(10,2) range. Dropping the value with a
            # warning keeps the rest of the row; storing it would fail the whole file.
            self.issues.warning(
                EldErrorCode.BAD_NUMBER,
                f"The '{field}' value is outside the range this field can store "
                f"(±{_NUMERIC_10_2_MAX:,.0f}); it was stored as blank. Check the ELD export "
                "for a corrupt odometer or engine-hour reading.",
                section=section, line_number=line_number, column_name=field, raw_value=raw,
            )
            return None
        return value

    def _coordinate(self, raw: str | None, field: str, section: str, line_number: int) -> float | None:
        if raw is None:
            return None
        value, sentinel = parse_coordinate(raw, is_latitude=field == "latitude")
        if value is None and sentinel is not None:
            self.issues.info(
                EldErrorCode.COORDINATE_UNAVAILABLE,
                "The ELD recorded no usable position for one or more events "
                f"('{sentinel}' in the {field} column) — expected for reduced-precision, "
                "personal-conveyance or malfunction records.",
                section=section, line_number=line_number, column_name=field, raw_value=raw,
            )
        elif value is None:
            self.issues.warning(
                EldErrorCode.BAD_COORDINATE,
                f"Could not read a coordinate from the '{field}' column; the position was "
                "stored as blank. Expected a signed decimal (-95.6779) or a "
                "hemisphere-suffixed value (95.6779W).",
                section=section, line_number=line_number, column_name=field, raw_value=raw,
            )
        return value

    def build(
        self,
        cells: Sequence[str],
        mapping: dict[str, int],
        *,
        section: str,
        line_number: int,
        fallback_sequence: int,
        raw: dict[str, Any],
    ) -> EldEventRow:
        seq_raw = _cell(cells, mapping, "event_sequence")
        sequence = parse_int(seq_raw)
        if seq_raw is not None and sequence is None:
            self.issues.warning(
                EldErrorCode.BAD_SEQUENCE,
                f"Event sequence '{seq_raw}' is not a usable sequence number (not an integer, or "
                "out of range); the row's position in the file was used instead so the event is "
                "still recorded.",
                section=section, line_number=line_number,
                column_name="event_sequence", raw_value=seq_raw,
            )
        if sequence is None:
            sequence = fallback_sequence

        type_code = parse_int(_cell(cells, mapping, "event_type_code"))
        code = parse_int(_cell(cells, mapping, "event_code"))
        status_code = parse_int(_cell(cells, mapping, "record_status"))
        origin_code = parse_int(_cell(cells, mapping, "record_origin"))

        event_type = EVENT_TYPE_NAMES.get(type_code) if type_code is not None else None
        if type_code is not None and event_type is None:
            self.issues.warning(
                EldErrorCode.UNKNOWN_EVENT_CODE,
                f"Event type '{type_code}' is not one of the seven types defined by "
                "49 CFR 395 Appendix A; the event was kept with its numeric type only.",
                section=section, line_number=line_number,
                column_name="event_type_code", raw_value=type_code,
            )

        duty: str | None = None
        if type_code == 1:
            duty = _DUTY_BY_EVENT_CODE.get(code) if code is not None else None
            if duty is None:
                self.issues.warning(
                    EldErrorCode.UNMAPPED_DUTY_CODE,
                    f"Duty-status change carries event code '{code}', which is not one of "
                    "1 (off duty), 2 (sleeper berth), 3 (driving) or 4 (on duty, not driving); "
                    "the event has no duty status and is excluded from the hours-of-service totals.",
                    section=section, line_number=line_number,
                    column_name="event_code", raw_value=code,
                )
        elif type_code == 3 and code is not None:
            duty = _DUTY_BY_PC_YM_CODE.get(code)

        # Timestamp: separate date/time columns first (the spec's shape), then a
        # single combined column, so both vendor layouts resolve.
        date_raw = _cell(cells, mapping, "event_date")
        time_raw = _cell(cells, mapping, "event_time")
        ts_raw = _cell(cells, mapping, "event_timestamp")
        timestamp: dt.datetime | None = None
        if date_raw:
            timestamp = parse_date_time(date_raw, time_raw)
            if timestamp is None:
                self.issues.warning(
                    EldErrorCode.BAD_TIMESTAMP,
                    f"Could not read a date/time from '{date_raw} {time_raw or ''}'.strip(); the event "
                    "has no timestamp and is excluded from the hours-of-service totals. The ELD "
                    "output-file standard writes the date as MMDDYY and the time as HHMMSS.",
                    section=section, line_number=line_number,
                    column_name="event_date", raw_value=f"{date_raw} {time_raw or ''}".strip(),
                )
        elif ts_raw:
            timestamp = parse_timestamp(ts_raw)
            if timestamp is None:
                self.issues.warning(
                    EldErrorCode.BAD_TIMESTAMP,
                    f"Could not read a timestamp from '{ts_raw}'; the event has no timestamp and is "
                    "excluded from the hours-of-service totals. Use an ISO-8601 value "
                    "(2026-05-01T08:00:00) or the standard MMDDYY/HHMMSS columns.",
                    section=section, line_number=line_number,
                    column_name="event_timestamp", raw_value=ts_raw,
                )
        else:
            self.issues.warning(
                EldErrorCode.MISSING_TIMESTAMP,
                "One or more events carry no date/time at all, so they cannot contribute to the "
                "hours-of-service timeline. Confirm the export includes the event date and time columns.",
                section=section, line_number=line_number,
            )

        ignition = _cell(cells, mapping, "ignition_status")
        if ignition is None and type_code == 6 and code is not None:
            ignition = _IGNITION_BY_POWER_CODE.get(code)

        return EldEventRow(
            event_sequence=sequence,
            line_number=line_number,
            section=section,
            event_timestamp=self._apply_tz(timestamp),
            duty=duty,
            event_type=event_type,
            event_type_code=type_code,
            event_code=code,
            record_status=RECORD_STATUS_NAMES.get(status_code) if status_code is not None else None,
            record_origin=RECORD_ORIGIN_NAMES.get(origin_code) if origin_code is not None else None,
            location=_cell(cells, mapping, "location"),
            latitude=self._coordinate(_cell(cells, mapping, "latitude"), "latitude", section, line_number),
            longitude=self._coordinate(_cell(cells, mapping, "longitude"), "longitude", section, line_number),
            miles_driven=self._number(_cell(cells, mapping, "miles_driven"), "miles_driven", section, line_number),
            engine_hours=self._number(_cell(cells, mapping, "engine_hours"), "engine_hours", section, line_number),
            distance_since_last_coords=self._number(
                _cell(cells, mapping, "distance_since_last_coords"),
                "distance_since_last_coords", section, line_number,
            ),
            ignition_status=ignition,
            malfunction_indicator=_cell(cells, mapping, "malfunction_indicator"),
            diagnostic_indicator=_cell(cells, mapping, "diagnostic_indicator"),
            annotation=_cell(cells, mapping, "annotation"),
            driver_identifier=_cell(cells, mapping, "driver_identifier"),
            cmv_identifier=_cell(cells, mapping, "cmv_identifier"),
            data_check_value=_cell(cells, mapping, "data_check_value"),
            raw=raw,
        )


# ---------------------------------------------------------------------------
# Hours-of-service roll-up
# ---------------------------------------------------------------------------
def _comparable(moment: dt.datetime) -> dt.datetime:
    """UTC-normalized copy for ordering/arithmetic only.

    A file can mix naive and aware timestamps — the header time-zone offset is
    applied when known, and an ISO value may carry its own offset — and Python
    refuses to compare the two. Naive values are read as UTC here so the summary
    never raises; the stored event keeps whatever the file actually said.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=dt.timezone.utc)


def summarize_hos(events: Sequence[EldEventRow]) -> dict[str, Any]:
    """Derive the hours-of-service roll-up Appendix E asks to be analyzable.

    Duty hours come from ACTIVE duty-status-change events only: an event the
    driver later edited out (record status INACTIVE_*) must not be counted, or
    the totals would double-count the corrected period. The final open segment
    is not extrapolated — a duty status with no following event has no known end.
    """
    timed = [e for e in events if e.event_timestamp is not None]
    summary: dict[str, Any] = {
        "event_count": len(events),
        "timed_event_count": len(timed),
        "events_by_type": {},
        "events_by_section": {},
        "duty_hours": {},
        "total_driving_hours": 0.0,
        "duty_status_changes": 0,
        "inactive_records": 0,
        "malfunction_events": 0,
        "unidentified_driver_records": 0,
        "personal_conveyance_events": 0,
        "yard_move_events": 0,
        "distinct_days": 0,
        "first_event_at": None,
        "last_event_at": None,
    }
    for event in events:
        label = event.event_type or (f"TYPE_{event.event_type_code}" if event.event_type_code is not None else "UNSPECIFIED")
        summary["events_by_type"][label] = summary["events_by_type"].get(label, 0) + 1
        section = event.section or "UNSPECIFIED"
        summary["events_by_section"][section] = summary["events_by_section"].get(section, 0) + 1
        if event.record_status and event.record_status.startswith("INACTIVE"):
            summary["inactive_records"] += 1
        if event.event_type_code == 1:
            summary["duty_status_changes"] += 1
        if event.event_type_code == 7:
            summary["malfunction_events"] += 1
        if event.section == "UNIDENTIFIED_DRIVER":
            summary["unidentified_driver_records"] += 1
        if event.event_type_code == 3 and event.event_code == 1:
            summary["personal_conveyance_events"] += 1
        if event.event_type_code == 3 and event.event_code == 2:
            summary["yard_move_events"] += 1

    if timed:
        moments = sorted(_comparable(e.event_timestamp) for e in timed)  # type: ignore[arg-type]
        summary["first_event_at"] = moments[0].isoformat()
        summary["last_event_at"] = moments[-1].isoformat()
        summary["distinct_days"] = len({m.date() for m in moments})

    # Duty segments: consecutive ACTIVE duty-bearing events on the main log.
    duty_events = sorted(
        (
            e for e in timed
            if e.duty is not None
            and e.section != "UNIDENTIFIED_DRIVER"
            and (e.record_status is None or e.record_status == "ACTIVE")
        ),
        key=lambda e: (_comparable(e.event_timestamp), e.event_sequence),  # type: ignore[arg-type]
    )
    for current, following in zip(duty_events, duty_events[1:]):
        start = _comparable(current.event_timestamp)  # type: ignore[arg-type]
        end = _comparable(following.event_timestamp)  # type: ignore[arg-type]
        hours = (end - start).total_seconds() / 3600.0
        if hours <= 0:
            continue
        summary["duty_hours"][current.duty] = round(
            summary["duty_hours"].get(current.duty, 0.0) + hours, 3
        )
    summary["total_driving_hours"] = summary["duty_hours"].get(DutyStatus.DRIVING.value, 0.0)
    summary["total_on_duty_hours"] = round(
        summary["duty_hours"].get(DutyStatus.DRIVING.value, 0.0)
        + summary["duty_hours"].get(DutyStatus.ON_DUTY_NOT_DRIVING.value, 0.0),
        3,
    )

    miles = [e.miles_driven for e in events if e.miles_driven is not None]
    if miles:
        summary["accumulated_miles_span"] = round(max(miles) - min(miles), 2)
    hours_values = [e.engine_hours for e in events if e.engine_hours is not None]
    if hours_values:
        summary["engine_hours_span"] = round(max(hours_values) - min(hours_values), 2)

    last_duty = next(
        (e for e in reversed(duty_events)), None
    )
    if last_duty is not None:
        summary["last_duty_status"] = last_duty.duty
        summary["last_duty_status_at"] = last_duty.event_timestamp.isoformat()  # type: ignore[union-attr]
    return summary


# ---------------------------------------------------------------------------
# Extraction entry point
# ---------------------------------------------------------------------------
def extract(
    content: bytes,
    *,
    field_aliases: dict[str, list[str]] | None = None,
    duty_map: dict[str, str] | None = None,
    max_events: int = DEFAULT_MAX_EVENTS,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
) -> ExtractionResult:
    """Decode and extract an ELD output file.

    ``field_aliases`` / ``duty_map`` are the RECO-5 configuration resolved for the
    file's (study, provider); they drive the flat-CSV path. The FMCSA sectioned
    path uses the standard's own column names, but still consults ``duty_map``
    for a textual duty column when a vendor writes one.

    Raises :class:`EldParseError` only when NOTHING can be extracted. Every other
    problem lands in ``result.issues``.
    """
    issues = IssueLog()
    started = time.monotonic()
    deadline = started + time_budget_seconds

    text, encoding = decode_payload(content, issues)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    line_count = normalized.count("\n") + (0 if normalized.endswith("\n") or not normalized else 1)
    delimiter = sniff_delimiter(normalized, issues)
    rows = _read_rows(normalized, delimiter, issues)

    if not rows:
        raise EldParseError(
            EldErrorCode.EMPTY_FILE,
            "The uploaded file contains no rows. Re-export the ELD output file from "
            "eRODS or the ELD provider portal and upload it again.",
        )

    # Reading and splitting the payload happens before any row is interpreted, so
    # a file large enough to exhaust the budget right here would otherwise fail
    # with "no events could be extracted" — true, but it names the symptom rather
    # than the cause. Checking the deadline here reports what actually happened.
    if time.monotonic() > deadline:
        error = EldParseError(
            EldErrorCode.TIME_BUDGET_EXCEEDED,
            f"Reading the file used the whole {time_budget_seconds:g}s extraction budget before any "
            f"event could be interpreted ({len(rows):,} rows over {line_count:,} lines). Split the "
            "export into smaller date ranges and upload them separately.",
        )
        error.issues = issues.issues()
        raise error

    sections = _split_sections(rows)
    recognized = [key for key, _ in sections if key not in (None, "PREAMBLE")]
    is_fmcsa = len(recognized) >= 2

    # A very common real-world export is the ELD Event List ALONE — the standard
    # column names, but no section title lines to recognize. Detecting it by its
    # header keeps it on the structural path, where the numeric Event Type /
    # Event Code pair is interpreted with its full meaning (a code of 3 is
    # "driving" only because the type is 1). Mapping those numbers through the
    # duty-code table instead would be a guess, since the same digits mean
    # different things under a different event type.
    if not is_fmcsa:
        header_index = _standard_event_header_index(rows)
        if header_index is not None:
            is_fmcsa = True
            sections = [("PREAMBLE", rows[:header_index]), ("EVENT_LIST", rows[header_index:])]

    try:
        if is_fmcsa:
            result = _extract_fmcsa(
                sections, issues, duty_map or {},
                max_events=max_events, deadline=deadline, budget=time_budget_seconds,
            )
        else:
            result = _extract_flat(
                rows, issues, field_aliases or {}, duty_map or {},
                max_events=max_events, deadline=deadline,
            )
    except EldParseError as exc:
        # A blocking failure still carries everything learned on the way down
        # (encoding fallback, stripped NULs, malformed-CSV line) so the file's
        # diagnostics are complete rather than just the fatal message.
        exc.issues = issues.issues()
        raise

    result.encoding = encoding
    result.delimiter = delimiter
    result.line_count = line_count
    result.issues = issues.issues()
    result.error_count = issues.error_count
    result.warning_count = issues.warning_count
    result.hos_summary = summarize_hos(result.events)
    result.hos_summary["parse_duration_ms"] = int((time.monotonic() - started) * 1000)

    # Last-resort link: the CCFP code may sit in an annotation, a footer comment
    # or anywhere else in the payload. Scanning the whole text preserves the
    # pre-existing fallback so an oddly-placed comment still links the upload.
    if not result.ccfp_code:
        result.ccfp_code = extract_ccfp_code(normalized)

    if not result.ccfp_code:
        issues.warning(
            EldErrorCode.NO_CCFP_CODE,
            "No CCFP code was found in the file's Output File Comment, so this upload is not "
            "linked to the crash record by the file itself. Ask the driver or motor carrier to "
            "re-submit the ELD output file with the crash's CCFP code as the Output File Comment.",
        )
        result.issues = issues.issues()
        result.warning_count = issues.warning_count
    return result


#: Header names that together identify a bare ELD Event List table: the numeric
#: type/code pair plus a sequence column. Requiring all three keeps a simplified
#: CSV (sequence,timestamp,duty,...) on the configurable flat path.
_STANDARD_EVENT_SEQUENCE_HEADERS = frozenset(
    {"event_sequence_id_number", "event_sequence_id", "event_sequence"}
)


def _standard_event_header_index(rows: list[tuple[int, list[str]]], scan: int = 10) -> int | None:
    """Index of the row that is a standard ELD Event List header, if any."""
    for index, (_line_number, cells) in enumerate(rows[:scan]):
        if not any(c.strip() for c in cells):
            continue
        names = {norm(c) for c in cells if c.strip()}
        if {"event_type", "event_code"} <= names and (names & _STANDARD_EVENT_SEQUENCE_HEADERS):
            return index
    return None


def _split_sections(rows: list[tuple[int, list[str]]]) -> list[tuple[str | None, list[tuple[int, list[str]]]]]:
    """Group rows under their section title. Rows before any title are PREAMBLE."""
    sections: list[tuple[str | None, list[tuple[int, list[str]]]]] = []
    current_key: str | None = "PREAMBLE"
    current_rows: list[tuple[int, list[str]]] = []
    for line_number, cells in rows:
        title = _section_title(cells)
        if title is not None:
            if current_rows or current_key != "PREAMBLE":
                sections.append((current_key, current_rows))
            current_key, current_rows = title, []
            continue
        current_rows.append((line_number, cells))
    sections.append((current_key, current_rows))
    return sections


def _extract_fmcsa(
    sections: list[tuple[str | None, list[tuple[int, list[str]]]]],
    issues: IssueLog,
    duty_map: dict[str, str],
    *,
    max_events: int,
    deadline: float,
    budget: float,
) -> ExtractionResult:
    """Extract a sectioned 49 CFR 395 Appendix A output file."""
    header: dict[str, Any] = {}
    section_counts: dict[str, int] = {}
    events: list[EldEventRow] = []
    annotations: dict[int, str] = {}
    truncated = False

    # The header segment must be read before any event so its time-zone offset can
    # normalize every timestamp, so the sections are walked in two passes. A titled
    # `ELD File Header Segment` wins; otherwise the untitled PREAMBLE rows are the
    # header block, which is how most real exports are laid out.
    header_block = next(
        (
            [r for r in block if any(c.strip() for c in r[1])]
            for key, block in sections
            if key == "HEADER" and any(any(c.strip() for c in r[1]) for r in block)
        ),
        None,
    )
    if header_block is None:
        header_block = next(
            (
                [r for r in block if any(c.strip() for c in r[1])]
                for key, block in sections
                if key == "PREAMBLE" and any(any(c.strip() for c in r[1]) for r in block)
            ),
            None,
        )
    if header_block:
        header = _extract_header(header_block, issues)
    else:
        issues.warning(
            EldErrorCode.NO_HEADER_SEGMENT,
            "The file has no ELD file header segment, so the driver, carrier, vehicle and "
            "time-zone offset could not be extracted. Events were still read, but their "
            "timestamps are stored exactly as recorded.",
        )

    tz_offset = parse_tz_offset(header.get("time_zone_offset"))
    if tz_offset is None:
        issues.info(
            EldErrorCode.NO_TIME_ZONE,
            "No usable time-zone offset was found in the header segment. Event times are stored "
            "exactly as the ELD recorded them, read as UTC — if the driver's home terminal was not "
            "on UTC, compare these times to other sources with that in mind.",
        )
    builder = _EventBuilder(issues, tz_offset)

    for key, block in sections:
        rows = [r for r in block if any(c.strip() for c in r[1])]
        if key in (None, "PREAMBLE", "HEADER"):
            continue
        section_counts[key] = section_counts.get(key, 0)
        if not rows:
            issues.info(
                EldErrorCode.SECTION_EMPTY,
                f"Section '{_SECTION_LABELS.get(key, key)}' is present but carries no rows.",
                section=key,
            )
            continue

        if key == "END_OF_FILE":
            flat = [c for _line, cells in rows for c in cells if c.strip()]
            if flat:
                header.setdefault("file_data_check_value", flat[-1])
            section_counts[key] = len(rows)
            continue

        if key in ("USER_LIST", "CMV_LIST"):
            header.setdefault("users" if key == "USER_LIST" else "cmvs", [])
            data_rows = rows[1:] if _looks_like_header_row(rows[0][1], extra_tokens=_LIST_HEADER_TOKENS) else rows
            header["users" if key == "USER_LIST" else "cmvs"].extend(
                [", ".join(c for c in cells if c.strip()) for _line, cells in data_rows]
            )
            section_counts[key] = len(data_rows)
            # The CMV list carries the VIN and power-unit number when the header
            # segment omitted them.
            if key == "CMV_LIST" and not header.get("vin"):
                for _line, cells in data_rows:
                    match = _VIN_RE.search(" ".join(cells).upper())
                    if match:
                        header["vin"] = match.group(0)
                        break
            continue

        if key == "EVENT_ANNOTATIONS":
            data_rows = rows[1:] if _looks_like_header_row(rows[0][1]) else rows
            section_counts[key] = len(data_rows)
            for _line, cells in data_rows:
                values = [c for c in cells if c.strip()]
                if len(values) < 2:
                    continue
                sequence = parse_int(values[0])
                if sequence is None:
                    continue
                annotations[sequence] = " ".join(values[1:])
            continue

        if key not in _EVENT_SECTIONS:
            issues.warning(
                EldErrorCode.UNRECOGNIZED_SECTION,
                f"Section '{_SECTION_LABELS.get(key, key)}' holds {len(rows)} row(s) that this "
                "release does not extract into events. The rows were not discarded silently — "
                "they remain in the stored source file.",
                section=key, line_number=rows[0][0],
            )
            section_counts[key] = len(rows)
            continue

        has_header = _looks_like_header_row(rows[0][1])
        header_row = rows[0][1] if has_header else []
        data_rows = rows[1:] if has_header else rows
        mapping = _map_headers(header_row, issues, key, rows[0][0]) if has_header else {}
        if not mapping:
            if key in ("EVENT_LIST", "UNIDENTIFIED_DRIVER"):
                # No header row: fall back to the standard's column order.
                mapping = {field: index for index, field in enumerate(_EVENT_POSITIONAL_ORDER)}
                issues.info(
                    EldErrorCode.HEADER_POSITIONAL,
                    f"Section '{_SECTION_LABELS.get(key, key)}' has no column-header row; its "
                    "columns were read in the order defined by 49 CFR 395 Appendix A.",
                    section=key, line_number=rows[0][0],
                )
            else:
                issues.warning(
                    EldErrorCode.SECTION_UNMAPPED,
                    f"Section '{_SECTION_LABELS.get(key, key)}' has {len(data_rows)} row(s) whose "
                    f"columns ({', '.join(c for c in header_row if c) or 'unnamed'}) matched no known "
                    "ELD field, so no events were extracted from it. Add the column names to the "
                    "ELD field mapping configuration if these rows are needed.",
                    section=key, line_number=rows[0][0],
                )
                section_counts[key] = len(data_rows)
                continue

        seen_sequences: set[int] = set()
        extracted_here = 0
        for index, (line_number, cells) in enumerate(data_rows, start=1):
            if time.monotonic() > deadline:
                issues.error(
                    EldErrorCode.TIME_BUDGET_EXCEEDED,
                    f"Extraction stopped at line {line_number} after exceeding its {budget:g}s time "
                    "budget; the remaining rows were NOT stored. Split the export into smaller date "
                    "ranges and upload them separately.",
                    section=key, line_number=line_number,
                )
                truncated = True
                break
            if len(events) >= max_events:
                issues.error(
                    EldErrorCode.TRUNCATED,
                    f"The file holds more than the {max_events:,}-event limit; extraction stopped at "
                    f"line {line_number} and the remaining rows were NOT stored. Split the export "
                    "into smaller date ranges and upload them separately.",
                    section=key, line_number=line_number,
                )
                truncated = True
                break
            raw = _raw_dict(header_row, cells, key)
            event = builder.build(
                cells, mapping, section=key, line_number=line_number,
                fallback_sequence=index, raw=raw,
            )
            if event.duty is None and event.event_type_code is None:
                # A vendor variant with a textual duty column instead of the
                # numeric event type/code pair: resolve it through the configured
                # duty map so provider mappings apply here too.
                duty_text = norm(_cell(cells, mapping, "event_code") or "")
                if duty_text:
                    event.duty = duty_map.get(duty_text)
            if event.event_sequence in seen_sequences:
                event.is_duplicate = True
                issues.warning(
                    EldErrorCode.DUPLICATE_SEQUENCE,
                    f"Event sequence {event.event_sequence} appears more than once in "
                    f"'{_SECTION_LABELS.get(key, key)}'. Both rows were kept and flagged so no data "
                    "is lost — confirm with the ELD provider whether the export is duplicated.",
                    section=key, line_number=line_number, raw_value=event.event_sequence,
                )
            seen_sequences.add(event.event_sequence)
            if len(cells) != len(header_row) and has_header:
                issues.warning(
                    EldErrorCode.RAGGED_ROW,
                    f"Line has {len(cells)} value(s) but the '{_SECTION_LABELS.get(key, key)}' header "
                    f"declares {len(header_row)} column(s). The row was read as far as it goes; "
                    "check the export for an unescaped delimiter inside a value.",
                    section=key, line_number=line_number,
                )
            events.append(event)
            extracted_here += 1
        section_counts[key] = extracted_here
        if truncated:
            break

    for event in events:
        if event.annotation is None and event.event_sequence in annotations:
            event.annotation = annotations[event.event_sequence]
    unmatched = set(annotations) - {e.event_sequence for e in events}
    if unmatched:
        issues.warning(
            EldErrorCode.ANNOTATION_UNMATCHED,
            f"{len(unmatched)} annotation/comment row(s) reference event sequence numbers that do "
            "not appear in the event list (e.g. "
            f"{', '.join(str(s) for s in sorted(unmatched)[:5])}). The annotations were not attached.",
            section="EVENT_ANNOTATIONS",
        )

    inactive = sum(1 for e in events if e.record_status and e.record_status.startswith("INACTIVE"))
    if inactive:
        issues.info(
            EldErrorCode.INACTIVE_RECORDS,
            f"{inactive} event(s) are recorded as inactive (edited or rejected). They are stored for "
            "provenance but excluded from the hours-of-service duty totals.",
        )

    if not events:
        issues.error(
            EldErrorCode.NO_EVENTS_EXTRACTED,
            "The file was recognized as an ELD output file but no events could be extracted from it. "
            "Confirm the export includes the ELD Event List section with its event rows.",
        )

    return ExtractionResult(
        file_format=EldFileFormat.FMCSA_ELD_OUTPUT.value,
        encoding="", delimiter="", line_count=0,
        row_count=sum(section_counts.values()),
        events=events,
        header=header,
        sections=section_counts,
        ccfp_code=extract_ccfp_code(header.get("output_file_comment"))
        or extract_ccfp_code("\n".join(header.get("raw_lines", []))),
        hos_summary={},
        issues=[],
        error_count=0,
        warning_count=0,
        truncated=truncated,
    )


def _raw_dict(header_row: Sequence[str], cells: Sequence[str], section: str) -> dict[str, Any]:
    """Preserve the source row verbatim so provenance survives extraction."""
    if header_row:
        raw = {(h or f"column_{i + 1}"): (cells[i] if i < len(cells) else None) for i, h in enumerate(header_row)}
        if len(cells) > len(header_row):
            raw["_extra"] = list(cells[len(header_row):])
    else:
        raw = {f"column_{i + 1}": value for i, value in enumerate(cells)}
    raw["_section"] = section
    return raw


def _extract_flat(
    rows: list[tuple[int, list[str]]],
    issues: IssueLog,
    field_aliases: dict[str, list[str]],
    duty_map: dict[str, str],
    *,
    max_events: int,
    deadline: float,
) -> ExtractionResult:
    """Extract a single-header tabular CSV through the configured mapping (RECO-5).

    This is the pre-existing shape and behaviour: header aliases and duty codes
    come from ``eld_field_mappings`` / ``eld_duty_code_mappings``. What changed is
    that a row-level problem is now *reported* instead of aborting the file or
    vanishing, and a header that maps to nothing is a blocking error rather than
    a run of empty events.
    """
    # Peel leading non-tabular comment lines (a `#`-prefixed line, a labelled
    # `Output File Comment: <code>` line, or a bare CCFP token) so the real header
    # reaches the mapper. A comma-bearing line is left alone: that is either the
    # header itself or a data row carrying a comment column.
    leading: list[str] = []
    body_start = 0
    for _line_number, cells in rows:
        joined = ",".join(cells).strip()
        non_empty = [c for c in cells if c.strip()]
        low = joined.lower()
        labelled = ("output file comment" in low or "output_file_comment" in low) and (
            ":" in low or "=" in low
            # `Output File Comment,CCFP-...` — the label and its value as two
            # cells. Only a short two-cell line qualifies, so a HEADER ROW naming
            # a comment column (sequence,duty,output_file_comment) is left for
            # the mapper, and its data rows keep the per-row column fallback.
            or (len(non_empty) == 2 and norm(non_empty[0]) in CCFP_COMMENT_COLUMNS)
        )
        bare_code = len(non_empty) <= 1 and CCFP_CODE_RE.search(joined) is not None
        if joined.startswith("#") or labelled or bare_code:
            leading.append(joined)
            body_start += 1
            continue
        break
    body = rows[body_start:]

    ccfp_code = extract_ccfp_code("\n".join(leading))

    if not body:
        raise EldParseError(
            EldErrorCode.NO_DATA_ROWS,
            "The file has no column header row. An ELD output CSV must either follow the "
            "sectioned 49 CFR 395 Appendix A layout or start with a header row naming its "
            "columns (for example: sequence,timestamp,duty,location).",
        )

    header_line, header_cells = body[0]
    normalized_header = [norm(c) for c in header_cells]
    data_rows = body[1:]

    mapping: dict[str, int] = {}
    for canonical, aliases in field_aliases.items():
        for alias in aliases:
            if alias in normalized_header:
                mapping[canonical] = normalized_header.index(alias)
                break

    if not mapping:
        shown = ", ".join(c for c in header_cells if c) or "(no column names)"
        raise EldParseError(
            EldErrorCode.NO_MAPPABLE_COLUMNS,
            f"None of this file's columns [{shown}] matched a known ELD field, so no "
            "hours-of-service data could be extracted. Upload the ELD output file produced by "
            "eRODS or the ELD provider, or configure the provider's column names under ELD field "
            "mappings.",
        )

    if not data_rows:
        raise EldParseError(
            EldErrorCode.NO_DATA_ROWS,
            "The file has a header row but no data rows, so there are no hours-of-service events "
            "to extract. Re-export the ELD output file covering the crash date.",
        )

    duplicates = [c for c in normalized_header if c and normalized_header.count(c) > 1]
    for column in sorted(set(duplicates)):
        issues.warning(
            EldErrorCode.DUPLICATE_HEADER,
            f"Column '{column}' appears more than once in the header row; the first occurrence "
            "was used and the later one ignored.",
            line_number=header_line, column_name=column,
        )

    builder = _EventBuilder(issues, None)
    events: list[EldEventRow] = []
    seen_sequences: set[int] = set()
    truncated = False

    for index, (line_number, cells) in enumerate(data_rows, start=1):
        if time.monotonic() > deadline:
            issues.error(
                EldErrorCode.TIME_BUDGET_EXCEEDED,
                f"Extraction stopped at line {line_number} after exceeding the time budget. Split "
                "the export into smaller files and upload them separately.",
                line_number=line_number,
            )
            truncated = True
            break
        if len(events) >= max_events:
            issues.error(
                EldErrorCode.TRUNCATED,
                f"The file holds more than the {max_events:,}-event limit; extraction stopped at line "
                f"{line_number} and the remaining rows were NOT stored. Split the export into smaller "
                "date ranges and upload them separately.",
                line_number=line_number,
            )
            truncated = True
            break
        if not any(c.strip() for c in cells):
            issues.info(
                EldErrorCode.BLANK_ROW,
                "Blank line(s) in the data rows were skipped.",
                line_number=line_number,
            )
            continue
        if len(cells) != len(header_cells):
            issues.warning(
                EldErrorCode.RAGGED_ROW,
                f"Line has {len(cells)} value(s) but the header declares {len(header_cells)} column(s). "
                "The row was read as far as it goes; check the export for an unescaped delimiter "
                "inside a value.",
                line_number=line_number,
            )

        raw = _raw_dict(header_cells, cells, "FLAT_CSV")
        if ccfp_code is None:
            for column in CCFP_COMMENT_COLUMNS:
                if column in normalized_header:
                    cell = cells[normalized_header.index(column)] if normalized_header.index(column) < len(cells) else ""
                    if cell:
                        ccfp_code = extract_ccfp_code(cell) or (cell if CCFP_CODE_RE.fullmatch(cell) else None)
                        if ccfp_code:
                            break

        event = builder.build(
            cells, mapping, section="FLAT_CSV", line_number=line_number,
            fallback_sequence=index, raw=raw,
        )
        # The flat shape carries duty as a textual code and event type as free
        # text, so both come from the configured mapping rather than the numeric
        # 49 CFR vocabulary.
        duty_index = mapping.get("duty")
        if duty_index is not None:
            duty_raw = norm(cells[duty_index]) if duty_index < len(cells) else ""
            event.duty = duty_map.get(duty_raw)
            if duty_raw and event.duty is None:
                issues.warning(
                    EldErrorCode.UNMAPPED_DUTY_CODE,
                    f"Duty code '{cells[duty_index]}' has no mapping to a CCFP duty status, so the "
                    "event has no duty status and is excluded from the hours-of-service totals. Add "
                    "the code under ELD duty-code mappings for this provider.",
                    line_number=line_number, column_name="duty", raw_value=cells[duty_index],
                )
        type_index = mapping.get("event_type")
        if type_index is not None and type_index < len(cells) and cells[type_index].strip():
            event.event_type = cells[type_index].strip()
            event.event_type_code = None
        if event.event_sequence in seen_sequences:
            event.is_duplicate = True
            issues.warning(
                EldErrorCode.DUPLICATE_SEQUENCE,
                f"Event sequence {event.event_sequence} appears more than once. Both rows were kept "
                "and flagged so no data is lost — confirm whether the export is duplicated.",
                line_number=line_number, raw_value=event.event_sequence,
            )
        seen_sequences.add(event.event_sequence)
        events.append(event)

    if not events:
        raise EldParseError(
            EldErrorCode.NO_EVENTS_EXTRACTED,
            "No hours-of-service events could be extracted from the file's data rows. Re-export the "
            "ELD output file and upload it again.",
        )

    # A flat export carries no header segment, so there is no declared time-zone
    # offset to normalize with. Say so rather than let the reader assume the
    # stored instants were converted.
    if any(e.event_timestamp is not None for e in events):
        issues.info(
            EldErrorCode.NO_TIME_ZONE,
            "This export carries no ELD file header segment, so it declares no time-zone offset. "
            "Event times without an explicit offset are stored exactly as recorded, read as UTC.",
        )

    return ExtractionResult(
        file_format=EldFileFormat.FLAT_CSV.value,
        encoding="", delimiter="", line_count=0,
        row_count=len(data_rows),
        events=events,
        header={"raw_lines": leading},
        sections={"FLAT_CSV": len(events)},
        ccfp_code=ccfp_code,
        hos_summary={},
        issues=[],
        error_count=0,
        warning_count=0,
        truncated=truncated,
    )


def issues_as_dicts(issues: Iterable[Issue]) -> list[dict[str, Any]]:
    """Serialize issues for an API response or a dry-run validation result."""
    return [dataclasses.asdict(issue) for issue in issues]
