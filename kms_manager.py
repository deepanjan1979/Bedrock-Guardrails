import boto3
import json
import logging
from botocore.exceptions import ClientError
from typing import Dict, List, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KMSKeyManager:
    """
    A class to manage AWS KMS keys for Bedrock Guardrails.
    Handles creation, listing, and management of KMS keys with appropriate policies.
    """
    
    def __init__(self, region: str = 'us-east-1'):
        """Initialize the KMS key manager with AWS credentials."""
        self.region = region
        self.kms_client = boto3.client('kms', region_name=region)
        self.sts_client = boto3.client('sts', region_name=region)
    
    def create_kms_key(self, description: str = 'Key for Bedrock Guardrails encryption') -> Dict:
        """
        Create a new KMS key with a basic policy.
        
        Args:
            description: Description for the KMS key
            
        Returns:
            Dictionary containing key metadata
        """
        try:
            # First, create the key with a minimal policy
            response = self.kms_client.create_key(
                Description=description,
                KeyUsage='ENCRYPT_DECRYPT',
                CustomerMasterKeySpec='SYMMETRIC_DEFAULT',
                Tags=[
                    {
                        'TagKey': 'Purpose',
                        'TagValue': 'BedrockGuardrailsEncryption'
                    }
                ]
            )
            
            key_id = response['KeyMetadata']['KeyId']
            key_arn = response['KeyMetadata']['Arn']
            
            # Create an alias
            alias_name = f'alias/bedrock-guardrail-key-{key_id[:8]}'
            self.kms_client.create_alias(
                AliasName=alias_name,
                TargetKeyId=key_id
            )
            
            print(f"✅ Created KMS key: {key_id}")
            print(f"   ARN: {key_arn}")
            print(f"   Alias: {alias_name}")
            
            # Now update the key policy
            self._update_key_policy(key_id)
            
            return {
                'KeyId': key_id,
                'KeyArn': key_arn,
                'Alias': alias_name
            }
            
        except ClientError as e:
            logger.error(f"❌ Error creating KMS key: {e}")
            raise

    def _update_key_policy(self, key_id: str):
        """Update the key policy to allow Bedrock to use the key."""
        try:
            account_id = self.sts_client.get_caller_identity()['Account']
            
            policy = {
                "Version": "2012-10-17",
                "Id": "bedrock-guardrail-key-policy",
                "Statement": [
                    {
                        "Sid": "Enable IAM User Permissions",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": f"arn:aws:iam::{account_id}:root"
                        },
                        "Action": "kms:*",
                        "Resource": "*"
                    },
                    {
                        "Sid": "Allow Bedrock to use the key",
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "bedrock.amazonaws.com"
                        },
                        "Action": [
                            "kms:Encrypt",
                            "kms:Decrypt",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:DescribeKey"
                        ],
                        "Resource": "*"
                    }
                ]
            }
            
            self.kms_client.put_key_policy(
                KeyId=key_id,
                PolicyName='default',
                Policy=json.dumps(policy)
            )
            print("✅ Updated key policy to allow Bedrock access")
            
        except ClientError as e:
            logger.error(f"❌ Error updating key policy: {e}")
            raise

    def encrypt_data(self, key_id: str, plaintext: str, context: Optional[Dict] = None) -> Dict:
        """
        Encrypt data using the specified KMS key.
        
        Args:
            key_id: The ID or ARN of the KMS key to use for encryption
            plaintext: The data to encrypt (as string)
            context: Optional encryption context
            
        Returns:
            Dictionary containing the encrypted data and key ID
        """
        try:
            response = self.kms_client.encrypt(
                KeyId=key_id,
                Plaintext=plaintext.encode('utf-8'),
                EncryptionContext=context or {}
            )
            
            return {
                'CiphertextBlob': response['CiphertextBlob'].hex(),
                'KeyId': response['KeyId'],
                'EncryptionAlgorithm': response.get('EncryptionAlgorithm', 'SYMMETRIC_DEFAULT')
            }
            
        except ClientError as e:
            logger.error(f"Error encrypting data: {e}")
            raise

    def decrypt_data(self, ciphertext_blob: str, context: Optional[Dict] = None) -> Dict:
        """
        Decrypt data using KMS.
        
        Args:
            ciphertext_blob: The encrypted data (as hex string)
            context: Optional encryption context (must match the one used for encryption)
            
        Returns:
            Dictionary containing the decrypted data and key ID
        """
        try:
            response = self.kms_client.decrypt(
                CiphertextBlob=bytes.fromhex(ciphertext_blob),
                EncryptionContext=context or {}
            )
            
            return {
                'Plaintext': response['Plaintext'].decode('utf-8'),
                'KeyId': response['KeyId'],
                'EncryptionAlgorithm': response.get('EncryptionAlgorithm', 'SYMMETRIC_DEFAULT')
            }
            
        except ClientError as e:
            logger.error(f"Error decrypting data: {e}")
            raise

def main():
    """Example usage of the KMSKeyManager class."""
    try:
        print("🔑 Initializing KMS Key Manager...")
        kms_manager = KMSKeyManager()
        
        print("\n🔄 Creating a new KMS key...")
        key_info = kms_manager.create_kms_key(
            description='KMS key for Bedrock Guardrails encryption'
        )
        
        print("\n✅ KMS key setup complete!")
        print("   Add this to your .env file:")
        print(f"   KMS_KEY_ALIAS={key_info['Alias']}")
        
    except Exception as e:
        print(f"\n❌ An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
