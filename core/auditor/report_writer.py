import json
from pathlib import Path
from datetime import datetime


def save_audit_report(report: dict) -> Path:
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    database_name = report.get("database_name", "database")
    db_type = report.get("database_type", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_path = reports_dir / f"{db_type}_{database_name}_audit_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, default=str)

    return output_path