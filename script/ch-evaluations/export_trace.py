import argparse
import csv
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REQUIRED_COLUMNS = {
    "operation_Id", "id", "operation_ParentId", "stage", "contentId",
    "instructions", "inputMessages", "outputMessages",
}


def export_csv(result: dict, output: Path) -> int:
    if result.get("error"):
        raise ValueError("The monitoring query returned an error or partial result.")
    tables = result.get("tables", [])
    if len(tables) != 1:
        raise ValueError("Expected exactly one monitoring result table.")
    table = tables[0]
    columns = [column["name"] for column in table["columns"]]
    if not REQUIRED_COLUMNS.issubset(columns):
        raise ValueError("The query did not return all required stage-evaluation fields.")
    if not table["rows"]:
        raise ValueError("No stage spans found; check the AppId, Trace ID, time range, and telemetry ingestion.")
    for row in table["rows"]:
        if len(row) != len(columns):
            raise ValueError("A monitoring row has an unexpected number of fields.")
    with output.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(table["rows"])
    return len(table["rows"])


def main():
    parser = argparse.ArgumentParser(description="Export complete v3 stage payloads from Application Insights.")
    parser.add_argument("--app-id", required=True, help="Application Insights Application ID, not a resource ARM ID.")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--query", type=Path, default=Path(__file__).resolve().parents[2] / "kql/ch-evaluations/export-stage-inputs.kql")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", args.app_id) or not re.fullmatch(r"[0-9a-fA-F]{32}", args.trace_id):
        parser.error("Provide a valid Application ID and 32-character hexadecimal Trace ID.")
    if args.output.exists():
        parser.error("The output already exists; choose another path.")
    from azure.identity import AzureCliCredential

    try:
        query = args.query.read_text(encoding="utf-8")
        if query.count("<TRACE_ID>") != 1:
            raise ValueError("The query must have exactly one <TRACE_ID> placeholder.")
        query = query.replace("<TRACE_ID>", args.trace_id)
        with AzureCliCredential(process_timeout=90) as credential:
            token = credential.get_token("https://api.applicationinsights.io/.default")
            request = Request(
                f"https://api.applicationinsights.io/v1/apps/{args.app_id}/query",
                data=json.dumps({"query": query, "timespan": "P7D"}).encode(),
                headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=120) as response:
                result = json.load(response)
        count = export_csv(result, args.output)
    except HTTPError as error:
        parser.exit(1, f"Monitoring request failed with HTTP {error.code}; check permissions and query syntax.\n")
    except (OSError, ValueError, URLError) as error:
        parser.exit(1, f"Trace export failed: {error}\n")
    print(json.dumps({"output": str(args.output), "stage_spans": count, "agent_calls": 0}))


if __name__ == "__main__":
    main()
