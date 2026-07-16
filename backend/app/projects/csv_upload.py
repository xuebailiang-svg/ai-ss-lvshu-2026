from __future__ import annotations

import csv
import io
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RentDataRecord, UnifiedCompetitorRecord
from app.projects.service import import_project_data


SUPPORTED_TYPES = {"competitor", "food", "entertainment", "rent"}
REQUIRED_FIELDS = {
    "competitor": {"名称", "距离"},
    "food": {"名称", "距离", "营业时间"},
    "entertainment": {"名称", "距离"},
    "rent": {"面积", "月租金"},
}


class CsvUploadError(ValueError):
    pass


def import_project_csv(db: Session, project_id: str, data_type: str, content: bytes) -> dict[str, Any]:
    normalized_type = str(data_type or "").strip().lower()
    if normalized_type not in SUPPORTED_TYPES:
        raise CsvUploadError("不支持的数据类型")
    if not content:
        raise CsvUploadError("CSV文件为空")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvUploadError("CSV文件必须使用UTF-8编码") from exc

    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        parsed_rows = list(reader)
    except csv.Error as exc:
        raise CsvUploadError(f"CSV格式错误：{exc}") from exc

    parsed_rows = [row for row in parsed_rows if any(str(value).strip() for value in row)]
    if not parsed_rows:
        raise CsvUploadError("CSV文件为空")

    headers = [str(value).strip() for value in parsed_rows[0]]
    missing_headers = sorted(REQUIRED_FIELDS[normalized_type] - set(headers))
    if missing_headers:
        raise CsvUploadError(f"缺少必填字段：{'、'.join(missing_headers)}")

    total_rows = 0
    imported_rows = 0
    duplicate_rows = 0
    errors: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    for csv_row_number, values in enumerate(parsed_rows[1:], start=2):
        if not any(str(value).strip() for value in values):
            continue
        total_rows += 1
        raw = {
            header: str(values[index]).strip() if index < len(values) else ""
            for index, header in enumerate(headers)
            if header
        }
        validation_errors = validate_csv_row(normalized_type, raw)
        if validation_errors:
            errors.append({"row": csv_row_number, "reason": "；".join(validation_errors)})
            continue

        if is_duplicate(db, project_id, normalized_type, raw):
            duplicate_rows += 1
            duplicates.append({"row": csv_row_number, "reason": "重复数据，已跳过"})
            continue

        raw.setdefault("source", "manual")
        raw.setdefault("confidence", 0.8)
        raw.setdefault("status", "pending_review")
        try:
            import_project_data(db, project_id, normalized_type, raw)
            imported_rows += 1
        except (ValidationError, ValueError, TypeError) as exc:
            db.rollback()
            errors.append({"row": csv_row_number, "reason": readable_validation_error(exc)})
        except Exception:
            db.rollback()
            errors.append({"row": csv_row_number, "reason": "数据保存失败"})

    if total_rows == 0:
        raise CsvUploadError("CSV文件没有数据行")

    return {
        "success": imported_rows > 0 or duplicate_rows > 0,
        "total_rows": total_rows,
        "imported_rows": imported_rows,
        "failed_rows": len(errors),
        "duplicate_rows": duplicate_rows,
        "errors": errors,
        "duplicates": duplicates,
    }


def is_duplicate(db: Session, project_id: str, data_type: str, row: dict[str, str]) -> bool:
    if data_type == "competitor":
        name = str(row.get("名称") or row.get("name") or "").strip()
        address = str(row.get("地址") or row.get("address") or "").strip() or None
        stmt = select(UnifiedCompetitorRecord.id).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.name == name,
        )
        stmt = stmt.where(
            UnifiedCompetitorRecord.address == address
            if address is not None
            else UnifiedCompetitorRecord.address.is_(None)
        )
        return db.scalar(stmt.limit(1)) is not None

    if data_type == "rent":
        address = str(row.get("地址") or row.get("location_type") or "").strip() or None
        try:
            area_sqm = float(str(row.get("面积") or row.get("area_sqm") or "").strip())
        except ValueError:
            return False
        stmt = select(RentDataRecord.id).where(
            RentDataRecord.project_id == project_id,
            RentDataRecord.area_sqm == area_sqm,
        )
        stmt = stmt.where(
            RentDataRecord.location_type == address
            if address is not None
            else RentDataRecord.location_type.is_(None)
        )
        return db.scalar(stmt.limit(1)) is not None

    return False


def validate_csv_row(data_type: str, row: dict[str, str]) -> list[str]:
    errors: list[str] = []

    def require_text(field: str) -> None:
        if not str(row.get(field) or "").strip():
            errors.append(f"{field}为空")

    def require_number(field: str, *, required: bool = False) -> None:
        value = str(row.get(field) or "").strip()
        if not value:
            if required:
                errors.append(f"{field}为空")
            return
        try:
            float(value)
        except ValueError:
            errors.append(f"{field}格式错误")

    if data_type == "competitor":
        require_text("名称")
        require_number("距离", required=True)
        for field in ("面积", "机器数量", "价格", "会员价格", "月营业额", "年营业额"):
            require_number(field)
        occupancy = str(row.get("上座率") or "").strip()
        if occupancy:
            try:
                float(occupancy.rstrip("%"))
            except ValueError:
                errors.append("上座率格式错误")
    elif data_type == "food":
        require_text("名称")
        require_number("距离", required=True)
        require_text("营业时间")
        require_number("评分")
    elif data_type == "entertainment":
        require_text("名称")
        require_number("距离", required=True)
    elif data_type == "rent":
        require_number("面积", required=True)
        require_number("月租金", required=True)
        for field in ("物业费", "转让费", "单平租金"):
            require_number(field)

    return errors


def readable_validation_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        details = exc.errors()
        if details:
            location = ".".join(str(item) for item in details[0].get("loc", []))
            return f"{location or '字段'}校验失败"
    return str(exc) or "数据格式错误"
