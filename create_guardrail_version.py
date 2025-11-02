import boto3
import os
import argparse
import uuid
import json
from botocore.config import Config
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_bedrock_client():
    """Create and return a configured Bedrock client."""
    config = Config(
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
        retries={'max_attempts': 5, 'mode': 'standard'}
    )
    return boto3.client(
        'bedrock',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        config=config
    )

def create_new_guardrail(client, name="DefaultGuardrail", description=None):
    """Create a new guardrail with default settings."""
    print(f"🆕 Creating new guardrail: {name}")
    
    # Default guardrail configuration
    guardrail_config = {
        'name': name,
        'blockedInputMessaging': 'I can\'t help with that request.',
        'blockedOutputsMessaging': 'I can\'t provide that information.',
        'contentPolicyConfig': {
            'filtersConfig': [
                {
                    'type': 'HATE',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH'
                },
                {
                    'type': 'INSULTS',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH'
                },
                {
                    'type': 'MISCONDUCT',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH'
                },
                {
                    'type': 'PROMPT_ATTACK',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'NONE'  # Must be NONE for PROMPT_ATTACK
                },
                {
                    'type': 'SEXUAL',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH'
                },
                {
                    'type': 'VIOLENCE',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH'
                }
            ]
        },
        'sensitiveInformationPolicyConfig': {
            'piiEntitiesConfig': [
                {
                    'type': 'NAME',
                    'action': 'BLOCK'
                },
                {
                    'type': 'ADDRESS',
                    'action': 'BLOCK'
                },
                {
                    'type': 'EMAIL',
                    'action': 'BLOCK'
                },
                {
                    'type': 'PHONE',
                    'action': 'BLOCK'
                },
                {
                    'type': 'US_SOCIAL_SECURITY_NUMBER',
                    'action': 'BLOCK'
                },
                {
                    'type': 'CREDIT_DEBIT_CARD_NUMBER',
                    'action': 'BLOCK'
                }
            ]
        },
        'clientRequestToken': str(uuid.uuid4())
    }
    
    if description:
        guardrail_config['description'] = description
    
    response = client.create_guardrail(**guardrail_config)
    guardrail_id = response['guardrailId']
    print(f"✅ Created new guardrail with ID: {guardrail_id}")
    return guardrail_id

def create_guardrail_version_from_config(guardrail_id, version_description=None):
    """
    Create a new version of an existing guardrail using its current configuration.
    
    Args:
        guardrail_id (str): ID of the guardrail to version
        version_description (str, optional): Description for the new version
        
    Returns:
        dict: Dictionary with guardrail_id, version_id, and status
    """
    client = get_bedrock_client()
    
    try:
        # Get the current guardrail configuration
        guardrail = client.get_guardrail(guardrailIdentifier=guardrail_id)
        guardrail_name = guardrail.get('name', guardrail_id)
        print(f"🚀 Creating new version for guardrail: {guardrail_name}")
        
        # Create new version
        params = {
            'guardrailIdentifier': guardrail_id,
            'clientRequestToken': str(uuid.uuid4())
        }
        if version_description:
            params['description'] = version_description
            
        version_response = client.create_guardrail_version(**params)
        version_id = version_response['version']
        print(f"✅ Version {version_id} created successfully.")
        
        # The new version is automatically set as DRAFT
        # We'll try to update it to ACTIVE
        try:
            # First, get the current guardrail configuration
            current_config = client.get_guardrail(guardrailIdentifier=guardrail_id)
            
            # To activate the version, we need to use the update_guardrail API
            # with the new version number in the version parameter
            try:
                # First, update the guardrail to use the new version
                update_params = {
                    'guardrailIdentifier': guardrail_id,
                    'name': guardrail_name,
                    'version': version_id,  # This is the key to activating the new version
                    'blockedInputMessaging': current_config.get('blockedInputMessaging', 'I can\'t help with that request.'),
                    'blockedOutputsMessaging': current_config.get('blockedOutputsMessaging', 'I can\'t provide that information.')
                }
                
                # Add optional fields if they exist in the current config
                optional_fields = [
                    'description', 'kmsKeyId', 'contentPolicyConfig',
                    'sensitiveInformationPolicyConfig', 'wordPolicyConfig'
                ]
                
                for field in optional_fields:
                    if field in current_config:
                        update_params[field] = current_config[field]
                
                # Update the guardrail to use the new version
                update_response = client.update_guardrail(**update_params)
                
                # Now, get the guardrail to check its status
                guardrail = client.get_guardrail(guardrailIdentifier=guardrail_id)
                if guardrail.get('status') == 'ACTIVE' and guardrail.get('version') == version_id:
                    print(f"✅ Version {version_id} activated successfully.")
                    status = 'ACTIVE'
                else:
                    print(f"⚠️  Version {version_id} created but activation status is {guardrail.get('status')}")
                    status = guardrail.get('status', 'UNKNOWN')
                    
            except Exception as e:
                print(f"⚠️  Could not activate version: {str(e)}")
                print("The guardrail version was created but not activated. You can activate it manually in the AWS Console.")
                status = 'DRAFT'
            
        except Exception as e:
            print(f"⚠️  Could not activate version: {str(e)}")
            print("The guardrail version was created but not activated. You can activate it manually in the AWS Console.")
            status = 'DRAFT'
            
        return {
            'guardrail_id': guardrail_id,
            'version_id': version_id,
            'status': status
        }

    except client.exceptions.ResourceNotFoundException:
        print(f"❌ Error: Guardrail with ID '{guardrail_id}' not found.")
    except client.exceptions.ConflictException as e:
        print(f"❌ Conflict error: {str(e)}")
    except client.exceptions.ValidationException as e:
        print(f"❌ Validation error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        if hasattr(e, 'response') and 'Error' in e.response:
            print(f"   Code: {e.response['Error'].get('Code', 'N/A')}")
            print(f"   Message: {e.response['Error'].get('Message', 'N/A')}")

    return None

def main():
    parser = argparse.ArgumentParser(
        description='Create a new version of an existing AWS Bedrock guardrail'
    )
    parser.add_argument(
        '--guardrail-id',
        required=True,
        help='ID of the guardrail to create a new version for (required)'
    )
    parser.add_argument(
        '--description',
        help='Optional description for the new version'
    )
    args = parser.parse_args()

    print(f"🔍 Creating new version for guardrail: {args.guardrail_id}")
    
    result = create_guardrail_version_from_config(
        guardrail_id=args.guardrail_id,
        version_description=args.description
    )
    
    if result:
        print("\n🎉 Success!")
        print(f"   Guardrail ID: {result['guardrail_id']}")
        print(f"   Version ID: {result['version_id']}")
        print(f"   Status: {result['status']}")
        
        if result['status'] == 'DRAFT':
            print("\n⚠️  The new version was created but not activated.")
            print("   You can activate it in the AWS Console or update it with additional parameters.")

if __name__ == "__main__":
    main()
