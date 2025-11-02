import boto3
import os
import time
import json
import argparse
from botocore.config import Config
from dotenv import load_dotenv

class GuardrailDeployer:
    def __init__(self, region='us-east-1'):
        """Initialize the GuardrailDeployer with AWS credentials from environment variables."""
        load_dotenv()
        
        # Configure AWS client with retry mechanism
        config = Config(
            region_name=os.getenv('AWS_DEFAULT_REGION', region),
            retries={
                'max_attempts': 5,
                'mode': 'standard'
            }
        )

        # Initialize the Bedrock client
        self.client = boto3.client(
            'bedrock',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            config=config
        )
        self.region = os.getenv('AWS_DEFAULT_REGION', region)

    def get_guardrail_status(self, guardrail_id, detailed=False):
        """Get the current status of a guardrail.
        
        Args:
            guardrail_id: The ID of the guardrail
            detailed: If True, returns full status information including failure reasons
            
        Returns:
            If detailed=False: Status string (e.g., 'ACTIVE', 'CREATING', 'FAILED')
            If detailed=True: Dictionary with status and additional information
        """
        try:
            response = self.client.get_guardrail(guardrailIdentifier=guardrail_id)
            if not detailed:
                return response.get('status', 'UNKNOWN')
            return response
        except Exception as e:
            print(f"❌ Error getting guardrail status: {str(e)}")
            if hasattr(e, 'response') and 'Error' in e.response:
                print(f"   Code: {e.response['Error'].get('Code', 'N/A')}")
                print(f"   Message: {e.response['Error'].get('Message', 'N/A')}")
            return None

    def create_guardrail_version(self, guardrail_id):
        """Create a new version of the guardrail."""
        try:
            print("🔄 Creating a new version of the guardrail...")
            response = self.client.create_guardrail_version(
                guardrailIdentifier=guardrail_id,
                description=f'Version created via script on {time.strftime("%Y-%m-%d %H:%M:%S")}'
            )
            version_id = response.get('version')
            if version_id:
                print(f"✅ Created new version: {version_id}")
                return version_id
            return None
        except Exception as e:
            print(f"❌ Error creating guardrail version: {str(e)}")
            if hasattr(e, 'response') and 'Error' in e.response:
                print(f"   Code: {e.response['Error'].get('Code', 'N/A')}")
                print(f"   Message: {e.response['Error'].get('Message', 'N/A')}")
            return None

    def deploy_guardrail(self, guardrail_id, version_id=None):
        """Deploy a guardrail version."""
        try:
            # Get guardrail details first
            guardrail_info = self.client.get_guardrail(guardrailIdentifier=guardrail_id)
            
            # If no version_id is provided, get the latest version or create one
            if not version_id:
                versions = guardrail_info.get('versions', [])
                
                if not versions:
                    print("ℹ️  No versions found. Creating a new version...")
                    version_id = self.create_guardrail_version(guardrail_id)
                    if not version_id:
                        return False
                else:
                    # Sort versions by creation time (newest first)
                    versions_sorted = sorted(versions, key=lambda v: v.get('createdAt', ''), reverse=True)
                    version_id = versions_sorted[0].get('version')
                    print(f"Using latest version: {version_id}")

            print(f"🚀 Activating guardrail {guardrail_id} (version {version_id})...")
            
            # Get the guardrail's current configuration
            guardrail_config = {
                'guardrailIdentifier': guardrail_id,
                'name': guardrail_info['name'],
                'description': f'Activated via script on {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'blockedInputMessaging': guardrail_info.get('blockedInputMessaging', 'Request blocked by guardrail'),
                'blockedOutputsMessaging': guardrail_info.get('blockedOutputsMessaging', 'Response blocked by guardrail'),
                'topicPolicyConfig': {
                    'topicsConfig': [{
                        'name': 'DefaultTopic',
                        'definition': 'General purpose topic for testing',
                        'type': 'DENY',
                        'inputAction': 'BLOCK',
                        'outputAction': 'BLOCK',
                        'inputEnabled': True,
                        'outputEnabled': True
                    }]
                },
                'contentPolicyConfig': {
                    'filtersConfig': [{
                        'type': 'HATE',
                        'inputStrength': 'LOW',
                        'outputStrength': 'LOW',
                        'inputAction': 'BLOCK',
                        'outputAction': 'BLOCK',
                        'inputEnabled': True,
                        'outputEnabled': True
                    }]
                },
                'contextualGroundingPolicyConfig': {
                    'filtersConfig': [{
                        'type': 'RELEVANCE',
                        'threshold': 0.7,
                        'action': 'BLOCK',
                        'enabled': True
                    }]
                }
            }


            # Remove None values
            guardrail_config = {k: v for k, v in guardrail_config.items() if v is not None}

            # Update the guardrail with the current configuration
            response = self.client.update_guardrail(**guardrail_config)
            
            # Wait for activation to complete
            max_attempts = 10
            for attempt in range(max_attempts):
                status_info = self.get_guardrail_status(guardrail_id, detailed=True)
                status = status_info.get('status')
                
                if status == 'ACTIVE':
                    print("✅ Guardrail activated successfully!")
                    return True
                elif status in ['FAILED', 'ERROR']:
                    print(f"❌ Guardrail activation failed with status: {status}")
                    if 'failureReasons' in status_info:
                        print("Failure reasons:", status_info['failureReasons'])
                    return False
                elif status == 'READY':
                    # If guardrail is READY, we can consider it successfully activated
                    print("✅ Guardrail is ready for use!")
                    return True
                
                print(f"   Activation in progress... (Status: {status})")
                time.sleep(5)
            
            print("⚠️  Activation is taking longer than expected. Please check the AWS Console for status.")
            return False
                
        except Exception as e:
            print(f"❌ Error deploying guardrail: {str(e)}")
            if hasattr(e, 'response') and 'Error' in e.response:
                print(f"   Code: {e.response['Error'].get('Code', 'N/A')}")
                print(f"   Message: {e.response['Error'].get('Message', 'N/A')}")
            return False

def main():
    """Main function to handle command-line arguments."""
    parser = argparse.ArgumentParser(description='Deploy and activate an AWS Bedrock Guardrail')
    parser.add_argument('--guardrail-id', type=str, required=True, help='ID of the guardrail to deploy')
    parser.add_argument('--version', type=str, help='Version ID to deploy (default: latest version)')
    parser.add_argument('--region', type=str, default='us-east-1', help='AWS region (default: us-east-1)')
    
    args = parser.parse_args()
    
    print("🚀 AWS Bedrock Guardrail Deployer")
    print("=" * 80)
    
    try:
        deployer = GuardrailDeployer(region=args.region)
        
        # Check guardrail status first
        status = deployer.get_guardrail_status(args.guardrail_id)
        if not status:
            print(f"❌ Could not find guardrail with ID: {args.guardrail_id}")
            return
            
        print(f"ℹ️  Current status of guardrail {args.guardrail_id}: {status}")
        
        if status == 'ACTIVE':
            print("✅ Guardrail is already active. No action needed.")
            return
            
        # Deploy the guardrail
        success = deployer.deploy_guardrail(args.guardrail_id, args.version)
        
        if success:
            print("\n🎉 Deployment completed successfully!")
            print("\nNext steps:")
            print(f"1. Test the guardrail in the AWS Console")
            print(f"2. Monitor guardrail metrics in CloudWatch")
            print(f"3. Update your application to use guardrail ID: {args.guardrail_id}")
        else:
            print("\n❌ Deployment failed. Check the error messages above for details.")
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
