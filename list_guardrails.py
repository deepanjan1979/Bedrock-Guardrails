import boto3
from botocore.config import Config
import os
from datetime import datetime
from dotenv import load_dotenv
import argparse

def setup_aws_client():
    """Initialize and return the AWS Bedrock client."""
    load_dotenv()
    
    config = Config(
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
        retries={
            'max_attempts': 5,
            'mode': 'standard'
        }
    )
    
    return boto3.client(
        'bedrock',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        config=config
    )

def list_guardrails(client, max_items=50):
    """List all guardrails with basic information."""
    try:
        # List all guardrails
        response = client.list_guardrails(maxResults=min(max_items, 100))
        
        # Get guardrails from response
        guardrails = response.get('guardrails', [])
        
        print("\n🔍 AWS Bedrock Guardrail Manager")
        print("=" * 80)
        print(f"{'ID':<30} {'Name':<30} {'Status':<15} {'Version'}")
        print('-' * 80)
        
        valid_guardrails = []
        
        # Collect valid guardrail information
        for guardrail in guardrails:
            guardrail_id = guardrail.get('id') or guardrail.get('guardrailId', '')
            name = guardrail.get('name', 'N/A')
            status = guardrail.get('status', 'N/A')
            arn = guardrail.get('arn', '')
            
            if not guardrail_id:
                continue
                
            valid_guardrails.append({
                'id': guardrail_id,
                'name': name,
                'status': status,
                'arn': arn
            })
        
        # Second pass: Get details for valid guardrails
        for guardrail in valid_guardrails:
            guardrail_id = guardrail['id']
            name = guardrail['name']
            status = guardrail['status']
            version = "v1 (DRAFT)"
            
            # Try to get version information if guardrail ID is valid
            if guardrail_id and guardrail_id != 'N/A':
                try:
                    details = client.get_guardrail(guardrailIdentifier=guardrail_id)
                    versions = details.get('versions', [])
                    if versions:
                        # Sort versions by creation time descending
                        sorted_versions = sorted(versions, key=lambda v: v.get('createdAt', ''), reverse=True)
                        latest = sorted_versions[0]
                        version_num = latest.get('version', 'N/A')
                        version_status = latest.get('status', 'N/A')
                        version = f"v{version_num} ({version_status})"
                except Exception as e:
                    version = "Error fetching version"


            
            # Use the guardrail ID directly
            print(f"{guardrail_id:<30} {name:<30} {status:<15} {version}")
        
        print("-" * 80)
        print(f"\nTotal guardrails found: {len(valid_guardrails)}")
        return valid_guardrails
        
    except Exception as e:
        print(f"\n❌ Error listing guardrails:")
        print(f"   {str(e)}")
        if hasattr(e, 'response') and 'Error' in e.response:
            print(f"   Code: {e.response['Error'].get('Code', 'N/A')}")
            print(f"   Message: {e.response['Error'].get('Message', 'N/A')}")
        return []

def get_guardrail_details(client, guardrail_id):
    """Get detailed information about a specific guardrail."""
    try:
        response = client.get_guardrail(guardrailIdentifier=guardrail_id)
        
        print(f"\n{'='*80}")
        print(f"Guardrail Details")
        print(f"{'='*80}")
        print(f"{'Name:':<20} {response.get('name')}")
        print(f"{'ID:':<20} {response.get('guardrailId')}")
        print(f"{'Status:':<20} {response.get('status')}")
        print(f"{'Created At:':<20} {response.get('createdAt')}")
        print(f"{'Last Updated:':<20} {response.get('updatedAt')}")
        
        # List versions if available
        versions = response.get('versions', [])
        if versions:
            print(f"\n{'Versions:':<20} {len(versions)}")
            for i, version in enumerate(versions, 1):
                print(f"  {i}. {version.get('version')} - {version.get('status')}")
        
        # List tags if available
        tags = response.get('tags', [])
        if tags:
            print("\nTags:")
            for tag in tags:
                print(f"  {tag.get('key')}: {tag.get('value')}")
                
        return response
        
    except Exception as e:
        print(f"❌ Error getting guardrail details: {str(e)}")
        if hasattr(e, 'response') and 'Error' in e.response:
            print(f"   Code: {e.response['Error'].get('Code', 'N/A')}")
            print(f"   Message: {e.response['Error'].get('Message', 'N/A')}")
        return None

def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(description='List and manage AWS Bedrock Guardrails')
    parser.add_argument('--id', type=str, help='Get details for a specific guardrail ID')
    parser.add_argument('--max-items', type=int, default=50, 
                       help='Maximum number of guardrails to list (default: 50)')
    
    args = parser.parse_args()
    
    print("🔍 AWS Bedrock Guardrail Manager")
    print("=" * 80)
    
    try:
        client = setup_aws_client()
        
        if args.id:
            get_guardrail_details(client, args.id)
        else:
            guardrails = list_guardrails(client, args.max_items)
            
    except Exception as e:
        print(f"\n❌ An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
