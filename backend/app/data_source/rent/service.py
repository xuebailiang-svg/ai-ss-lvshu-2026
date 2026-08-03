from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.crawler.evidence import crawler_suggestion_from_raw

from app.data_source.base import DataSourceRequest
from app.data_source.registry import DataSourceRegistry, build_default_registry
from app.models import RentDataRecord
from app.projects.service import get_project


class RentProjectNotFoundError(RuntimeError):
    pass


class RentCsvImportError(ValueError):
    pass


class RentRecordNotFoundError(RuntimeError):
    pass


FIELD_ALIASES = {
    "address": ("地址", "address", "location_type"),
    "area_sqm": ("面积", "area_sqm"),
    "monthly_rent": ("月租金", "monthly_rent"),
    "property_fee": ("物业费", "property_fee"),
    "transfer_fee": ("转让费", "transfer_fee"),
    "rent_per_sqm": ("单平租金", "rent_unit_price", "rent_per_sqm"),
}
REQUIRED_FIELDS = {
    "address": "地址",
    "area_sqm": "面积",
    "monthly_rent": "月租金",
}


def _value(row: dict[str, str], field_name: str) -> str:
    for alias in FIELD_ALIASES[field_name]:
        value = str(row.get(alias) or "").strip()
        if value:
            return value
    return ""


def _number(value: str, label: str, *, required: bool = False) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        if required:
            raise ValueError(f"{label}不能为空")
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"{label}必须为数字") from exc
    if number < 0:
        raise ValueError(f"{label}不能为负数")
    return number


def _parse_csv(content: bytes) -> tuple[int, list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    if not content:
        raise RentCsvImportError("CSV文件为空")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RentCsvImportError("CSV文件必须使用UTF-8编码") from exc

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = [str(item or "").strip() for item in (reader.fieldnames or [])]
    except csv.Error as exc:
        raise RentCsvImportError(f"CSV格式错误：{exc}") from exc
    if not headers:
        raise RentCsvImportError("CSV文件缺少表头")

    missing_headers = [
        label
        for field_name, label in REQUIRED_FIELDS.items()
        if not any(alias in headers for alias in FIELD_ALIASES[field_name])
    ]
    if missing_headers:
        raise RentCsvImportError(f"缺少必填字段：{'、'.join(missing_headers)}")

    total_rows = 0
    records: list[tuple[int, dict[str, Any]]] = []
    errors: list[dict[str, Any]] = []
    for row_number, raw_row in enumerate(reader, start=2):
        row = {str(key or "").strip(): str(value or "").strip() for key, value in raw_row.items()}
        if not any(row.values()):
            continue
        total_rows += 1
        try:
            address = _value(row, "address")
            if not address:
                raise ValueError("地址不能为空")
            area_sqm = _number(_value(row, "area_sqm"), "面积", required=True)
            monthly_rent = _number(_value(row, "monthly_rent"), "月租金", required=True)
            property_fee = _number(_value(row, "property_fee"), "物业费")
            transfer_fee = _number(_value(row, "transfer_fee"), "转让费")
            rent_per_sqm = _number(_value(row, "rent_per_sqm"), "单平租金")
            if rent_per_sqm is None and area_sqm and monthly_rent is not None:
                rent_per_sqm = round(monthly_rent / area_sqm, 2)
            records.append(
                (
                    row_number,
                    {
                        "location_type": address,
                        "address": address,
                        "area_sqm": area_sqm,
                        "monthly_rent": monthly_rent,
                        "property_fee": property_fee,
                        "transfer_fee": transfer_fee,
                        "rent_per_sqm": rent_per_sqm,
                        "source": "manual",
                        "confidence": 0.8,
                        "status": "pending_review",
                    },
                )
            )
        except ValueError as exc:
            errors.append({"row": row_number, "reason": str(exc)})

    if total_rows == 0:
        raise RentCsvImportError("CSV文件没有数据行")
    return total_rows, records, errors


async def import_project_rent_csv(
    db: Session,
    project_id: str,
    content: bytes,
    *,
    registry: DataSourceRegistry | None = None,
) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise RentProjectNotFoundError("Project not found")

    total_rows, parsed_records, errors = _parse_csv(content)
    provider = (registry or build_default_registry()).get("manual_rent")
    request = DataSourceRequest(project_id=project_id, records=[record for _, record in parsed_records])
    result = await provider.get_rent(request)

    imported_rows = 0
    for (row_number, _), item in zip(parsed_records, result.items):
        raw_data = dict(item.raw_data or {})
        row = RentDataRecord(
            project_id=project_id,
            monthly_rent=item.monthly_rent,
            area_sqm=item.area_sqm,
            rent_per_sqm=item.rent_per_sqm,
            location_type=item.location_type,
            source="manual",
            confidence=float(item.confidence or 0.8),
            status="pending_review",
            raw_data=raw_data,
        )
        db.add(row)
        imported_rows += 1

    if len(result.items) < len(parsed_records):
        for row_number, _ in parsed_records[len(result.items):]:
            errors.append({"row": row_number, "reason": "租金数据转换失败"})

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise RentCsvImportError("租金数据保存失败") from exc

    return {
        "success": imported_rows > 0,
        "project_id": project_id,
        "total_rows": total_rows,
        "imported_rows": imported_rows,
        "failed_rows": len(errors),
        "errors": errors,
        "warnings": list(result.warnings),
    }


def _raw_number(raw_data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = raw_data.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _rent_item(row: RentDataRecord) -> dict[str, Any]:
    raw_data = row.raw_data if isinstance(row.raw_data, dict) else {}
    manual_detail = raw_data.get("manual_detail") if isinstance(raw_data.get("manual_detail"), dict) else {}
    address = row.location_type or raw_data.get("address") or raw_data.get("地址")
    missing_fields: list[str] = []
    if not address:
        missing_fields.append("地址")
    if row.area_sqm is None:
        missing_fields.append("面积")
    if row.monthly_rent is None:
        missing_fields.append("月租金")
    return {
        "id": row.id,
        "address": address,
        "area_sqm": row.area_sqm,
        "monthly_rent": row.monthly_rent,
        "rent_unit_price": row.rent_per_sqm,
        "property_fee": _raw_number(raw_data, "property_fee", "物业费"),
        "transfer_fee": _raw_number(raw_data, "transfer_fee", "转让费"),
        "source": row.source,
        "status": row.status,
        "timestamp": row.timestamp,
        "missing_fields": missing_fields,
        "detail_completed": bool(manual_detail.get("property_type") and manual_detail.get("source_url")),
        "crawler_suggestion": crawler_suggestion_from_raw(raw_data, row.status),
    }


def list_project_rent(db: Session, project_id: str) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise RentProjectNotFoundError("Project not found")
    rows = db.scalars(
        select(RentDataRecord)
        .where(RentDataRecord.project_id == project_id)
        .order_by(RentDataRecord.timestamp.desc(), RentDataRecord.id.desc())
    ).all()
    items = [_rent_item(row) for row in rows]
    return {
        "items": items,
        "total": len(items),
        "incomplete_count": sum(bool(item["missing_fields"]) for item in items),
        "confirmed_count": sum(item["status"] == "confirmed" for item in items),
        "detail_completed_count": sum(
            item["status"] == "confirmed" and item["detail_completed"] for item in items
        ),
    }


def _get_rent_record(db: Session, project_id: str, rent_id: int) -> RentDataRecord:
    project = get_project(db, project_id)
    if not project:
        raise RentProjectNotFoundError("Project not found")
    row = db.scalar(
        select(RentDataRecord).where(
            RentDataRecord.project_id == project_id,
            RentDataRecord.id == rent_id,
        )
    )
    if not row:
        raise RentRecordNotFoundError("Rent record not found")
    return row


def review_project_rent(db: Session, project_id: str, rent_id: int, status: str) -> dict[str, Any]:
    row = _get_rent_record(db, project_id, rent_id)
    row.status = status
    db.commit()
    db.refresh(row)
    return _rent_item(row)


def get_project_rent_detail(db: Session, project_id: str, rent_id: int) -> dict[str, Any]:
    row = _get_rent_record(db, project_id, rent_id)
    raw_data = row.raw_data if isinstance(row.raw_data, dict) else {}
    manual_detail = raw_data.get("manual_detail") if isinstance(raw_data.get("manual_detail"), dict) else {}
    return {**_rent_item(row), "manual_detail": manual_detail}


def update_project_rent_detail(
    db: Session,
    project_id: str,
    rent_id: int,
    updates: dict[str, Any],
) -> dict[str, Any]:
    row = _get_rent_record(db, project_id, rent_id)
    raw_data = dict(row.raw_data or {})
    manual_detail = dict(raw_data.get("manual_detail") or {})
    for field_name, value in updates.items():
        manual_detail[field_name] = value.strip() if isinstance(value, str) and value.strip() else value
    raw_data["manual_detail"] = manual_detail
    row.raw_data = raw_data
    db.commit()
    db.refresh(row)
    return {**_rent_item(row), "manual_detail": manual_detail}
