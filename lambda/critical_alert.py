import os
import boto3

sns = boto3.client("sns")
TOPIC_ARN = os.environ["TOPIC_ARN"]


def lambda_handler(event, context):
    sent = 0
    for record in event["Records"]:
        if record["eventName"] != "INSERT":
            continue
        t = record["dynamodb"]["NewImage"]
        if t["priority"]["S"] != "Critical":
            continue
        sns.publish(
            TopicArn=TOPIC_ARN,
            Subject=f"[CRITICAL] {t['ticketId']['S']} - {t['module']['S']}",
            Message=(
                f"Ticket: {t['ticketId']['S']}\n"
                f"Customer: {t['customerName']['S']}\n"
                f"Module: {t['module']['S']}\n"
                f"Type: {t['requestType']['S']}\n"
                f"Due: {t['dueAt']['S']}\n\n"
                f"{t['description']['S']}"
            ),
        )
        sent += 1
        print(f"alert sent for {t['ticketId']['S']}")
    return {"processed": len(event["Records"]), "alertsSent": sent}
