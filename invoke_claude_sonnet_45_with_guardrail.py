import boto3
import json
import os

REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"  # Update if Claude 4.5 has a different modelId
GUARDRAIL_ID = "ze75inb2clma"
GUARDRAIL_VERSION = "DRAFT"  # Or your published version if available

PROMPT = "Give me a summary of the latest advancements in AI."

client = boto3.client("bedrock-runtime", region_name=REGION)

response = client.invoke_model(
    modelId=MODEL_ID,
    guardrailIdentifier=GUARDRAIL_ID,
    guardrailVersion=GUARDRAIL_VERSION,
    body=json.dumps({
        "prompt": PROMPT,
        "max_tokens_to_sample": 300
    })
)

print("--- Claude Sonnet 4.5 Response ---")
print(response["body"].read().decode())
