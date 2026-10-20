import json
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

MODULES = {"Core HR", "Payroll", "Time & Attendance", "Recruitment",
           "Performance", "Learning", "Reports", "Other"}
REQUEST_TYPES = {"Access/Permission", "Issue/Bug", "How-To",
                 "Data Correction", "Enhancement"}
SLA_HOURS = {"Low": 72, "Medium": 24, "High": 8, "Critical": 4}
STATUSES = {"Open", "In Progress", "Waiting on Customer", "Resolved", "Closed"}


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def now():
    return datetime.now(timezone.utc)


def lambda_handler(event, context):
    route = event["routeKey"]
    ticket_id = (event.get("pathParameters") or {}).get("id")
    qs = event.get("queryStringParameters") or {}

    print(json.dumps({"message": "request received", "route": route,
                      "requestId": context.aws_request_id}))

    try:
        # ---------- CREATE ----------
        if route == "POST /tickets":
            data = json.loads(event.get("body") or "{}")
            priority = data.get("priority", "Medium")
            errors = []
            if not data.get("customerName"):
                errors.append("customerName is required")
            if data.get("module") not in MODULES:
                errors.append(f"module must be one of {sorted(MODULES)}")
            if data.get("requestType") not in REQUEST_TYPES:
                errors.append(f"requestType must be one of {sorted(REQUEST_TYPES)}")
            if priority not in SLA_HOURS:
                errors.append(f"priority must be one of {list(SLA_HOURS)}")
            if not data.get("description"):
                errors.append("description is required")
            if errors:
                return respond(400, {"errors": errors})

            created = now()
            item = {
                "ticketId": f"HRIS-{uuid.uuid4().hex[:8].upper()}",
                "customerName": data["customerName"],
                "module": data["module"],
                "requestType": data["requestType"],
                "priority": priority,
                "status": "Open",
                "assignee": data.get("assignee", "Unassigned"),
                "description": data["description"],
                "resolutionNotes": "",
                "createdAt": created.isoformat(),
                "updatedAt": created.isoformat(),
                "dueAt": (created + timedelta(hours=SLA_HOURS[priority])).isoformat(),
            }
            table.put_item(Item=item)
            return respond(201, item)

        # ---------- LIST (optional ?status= and ?module=) ----------
        if route == "GET /tickets":
            status = qs.get("status")
            if status:
                if status not in STATUSES:
                    return respond(400, {"error": f"status must be one of {sorted(STATUSES)}"})
                result = table.query(
                    IndexName="status-index",
                    KeyConditionExpression=Key("status").eq(status),
                    ScanIndexForward=False,
                    Limit=50,
                )
            else:
                result = table.scan(Limit=50)
            items = result.get("Items", [])
            if qs.get("module"):
                items = [i for i in items if i["module"] == qs["module"]]
            return respond(200, items)

        # ---------- SUMMARY (counts by status and module) ----------
        if route == "GET /summary":
            by_status, by_module = Counter(), Counter()
            kwargs = {
                "ProjectionExpression": "#s, #m",
                "ExpressionAttributeNames": {"#s": "status", "#m": "module"},
            }
            while True:
                page = table.scan(**kwargs)
                for i in page["Items"]:
                    by_status[i["status"]] += 1
                    by_module[i["module"]] += 1
                if "LastEvaluatedKey" not in page:
                    break
                kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
            return respond(200, {"byStatus": dict(by_status),
                                 "byModule": dict(by_module),
                                 "total": sum(by_status.values())})

        # ---------- GET ONE ----------
        if route == "GET /tickets/{id}":
            item = table.get_item(Key={"ticketId": ticket_id}).get("Item")
            if not item:
                return respond(404, {"error": "ticket not found"})
            return respond(200, item)

        # ---------- UPDATE (status, assignee, priority, resolutionNotes) ----------
        if route == "PUT /tickets/{id}":
            data = json.loads(event.get("body") or "{}")
            allowed = {"status", "assignee", "priority", "resolutionNotes"}
            updates = {k: v for k, v in data.items() if k in allowed}
            if not updates:
                return respond(400, {"error": f"provide at least one of {sorted(allowed)}"})
            if "status" in updates and updates["status"] not in STATUSES:
                return respond(400, {"error": f"status must be one of {sorted(STATUSES)}"})
            if "priority" in updates and updates["priority"] not in SLA_HOURS:
                return respond(400, {"error": f"priority must be one of {list(SLA_HOURS)}"})
            if updates.get("status") == "Resolved":
                updates["resolvedAt"] = now().isoformat()
            updates["updatedAt"] = now().isoformat()

            result = table.update_item(
                Key={"ticketId": ticket_id},
                UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in updates),
                ConditionExpression="attribute_exists(ticketId)",
                ExpressionAttributeNames={f"#{k}": k for k in updates},
                ExpressionAttributeValues={f":{k}": v for k, v in updates.items()},
                ReturnValues="ALL_NEW",
            )
            return respond(200, result["Attributes"])

        # ---------- DELETE ----------
        if route == "DELETE /tickets/{id}":
            table.delete_item(
                Key={"ticketId": ticket_id},
                ConditionExpression="attribute_exists(ticketId)",
            )
            return respond(200, {"message": "deleted", "ticketId": ticket_id})

        return respond(404, {"error": "route not found"})

    except json.JSONDecodeError:
        return respond(400, {"error": "invalid JSON body"})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"error": "ticket not found"})
        print(json.dumps({"message": "dynamodb error", "error": str(e)}))
        return respond(500, {"error": "internal server error"})
    except Exception as e:
        print(json.dumps({"message": "unhandled error", "error": str(e)}))
        return respond(500, {"error": "internal server error"})
