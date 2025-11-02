import boto3
import os
import time
import uuid
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Union
from botocore.config import Config
from dotenv import load_dotenv
from kms_manager import KMSKeyManager

# Load environment variables from .env file
load_dotenv()

class ContextualGroundingCheck:
    """Class to handle contextual grounding checks for banking guardrails."""
    
    @staticmethod
    def check_factual_consistency(response: str, context: str) -> Tuple[bool, str]:
        """
        Check if the response is factually consistent with the provided context.
        
        Args:
            response: The model's response to check
            context: The context against which to check the response
            
        Returns:
            Tuple of (is_consistent, reason)
        """
        # Check for numerical consistency (e.g., interest rates, dates, amounts)
        numbers_in_response = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', response))
        numbers_in_context = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', context))
        
        # If there are numbers in response but not in context, it might be hallucinated
        if numbers_in_response and not numbers_in_response.issubset(numbers_in_context):
            return False, "Response contains numbers not present in context"
            
        # Check for key financial terms that should be consistent
        financial_terms = ['interest rate', 'APR', 'APY', 'fee', 'penalty', 'balance', 'withdrawal', 'deposit']
        for term in financial_terms:
            if term in response.lower() and term not in context.lower():
                return False, f"Response introduces financial term '{term}' not in context"
                
        return True, ""
    
    @staticmethod
    def check_temporal_consistency(response: str, context: str) -> Tuple[bool, str]:
        """Check if the response maintains temporal consistency with the context."""
        # Extract dates from response and context
        date_pattern = r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
        response_dates = set(re.findall(date_pattern, response, re.IGNORECASE))
        context_dates = set(re.findall(date_pattern, context, re.IGNORECASE))
        
        # If response introduces new dates not in context, it might be hallucinated
        if response_dates and not response_dates.issubset(context_dates):
            return False, "Response introduces dates not present in context"
            
        return True, ""

class BankingGuardrailManager:
    def __init__(self, region='us-east-1'):
        """Initialize the BankingGuardrailManager with AWS credentials from environment variables."""
        load_dotenv()  # Load environment variables from .env file

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
        self.grounding_checker = ContextualGroundingCheck()
        self.base_guardrail_name = "BankingVoiceBotGuardrail"
        
        # Initialize KMS Key Manager
        self.kms_manager = KMSKeyManager(region=self.region)
        self.encryption_context = {
            'service': 'bedrock-guardrails',
            'environment': os.getenv('ENVIRONMENT', 'development')
        }
        
    def check_grounding(self, response: str, context: str) -> Dict[str, any]:
        """
        Perform contextual grounding checks on a model response.
        
        Args:
            response: The model's response to check
            context: The context against which to check the response
            
        Returns:
            Dictionary containing grounding check results
        """
        results = {
            'is_grounded': True,
            'checks': [],
            'warnings': []
        }
        
        # Perform factual consistency check
        fact_consistent, fact_reason = self.grounding_checker.check_factual_consistency(response, context)
        if not fact_consistent:
            results['is_grounded'] = False
            results['checks'].append({
                'check': 'factual_consistency',
                'passed': False,
                'reason': fact_reason
            })
            results['warnings'].append(f"Factual inconsistency detected: {fact_reason}")
        else:
            results['checks'].append({
                'check': 'factual_consistency',
                'passed': True
            })
        
        # Perform temporal consistency check
        temp_consistent, temp_reason = self.grounding_checker.check_temporal_consistency(response, context)
        if not temp_consistent:
            results['is_grounded'] = False
            results['checks'].append({
                'check': 'temporal_consistency',
                'passed': False,
                'reason': temp_reason
            })
            results['warnings'].append(f"Temporal inconsistency detected: {temp_reason}")
        else:
            results['checks'].append({
                'check': 'temporal_consistency',
                'passed': True
            })
        
        return results
        
    def generate_with_grounding_check(self, prompt: str, context: str, **kwargs) -> Dict[str, any]:
        """
        Generate a response with contextual grounding check.
        
        Args:
            prompt: The prompt to generate a response for
            context: The context to use for grounding checks
            **kwargs: Additional arguments to pass to the model
            
        Returns:
            Dictionary containing the response and grounding check results
        """
        # Call the model to generate a response
        model_id = kwargs.pop('model_id', 'anthropic.claude-v2')
        
        try:
            # This is a simplified example - you would replace this with your actual model invocation
            response = f"This is a sample response to: {prompt}"  # Replace with actual model call
            
            # Perform grounding check
            grounding_results = self.check_grounding(response, context)
            
            return {
                'response': response,
                'grounding_check': grounding_results,
                'is_grounded': grounding_results['is_grounded']
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'is_grounded': False
            }

    def _encrypt_sensitive_data(self, data: Union[str, Dict, List]) -> Dict[str, Any]:
        """
        Encrypt sensitive data using KMS.
        
        Args:
            data: Data to encrypt (can be string, dict, or list)
            
        Returns:
            Dictionary containing encrypted data and metadata
        """
        try:
            # Convert data to JSON string if it's a dict or list
            if isinstance(data, (dict, list)):
                data_str = json.dumps(data, ensure_ascii=False)
            else:
                data_str = str(data)
                
            # Encrypt the data
            encrypted = self.kms_manager.encrypt_data(
                key_id=os.getenv('KMS_KEY_ALIAS', 'alias/bedrock-guardrail-key'),
                plaintext=data_str,
                context=self.encryption_context
            )
            
            return {
                'encrypted': True,
                'data': encrypted['CiphertextBlob'],
                'key_id': encrypted['KeyId'],
                'algorithm': encrypted['EncryptionAlgorithm']
            }
            
        except Exception as e:
            logger.error(f"Error encrypting data: {e}")
            raise
    
    def _decrypt_data(self, encrypted_data: Dict[str, Any]) -> Union[str, Dict, List]:
        """
        Decrypt data that was encrypted with KMS.
        
        Args:
            encrypted_data: Dictionary containing encrypted data and metadata
            
        Returns:
            Decrypted data (string, dict, or list)
        """
        try:
            # Decrypt the data
            decrypted = self.kms_manager.decrypt_data(
                ciphertext_blob=encrypted_data['data'],
                context=self.encryption_context
            )
            
            # Try to parse as JSON if it looks like JSON
            try:
                return json.loads(decrypted['Plaintext'])
            except json.JSONDecodeError:
                return decrypted['Plaintext']
        except Exception as e:
            logger.error(f"Error decrypting data: {e}")
            raise

    def _get_topic_policy_config(self):
        """Define topic-based policies for banking context."""
        return {
            'topicsConfig': [
                # Security and Fraud Prevention
                {
                    'name': 'Financial Fraud',
                    'definition': 'Discussions about fraudulent activities or scams',
                    'type': 'DENY',
                    'examples': ['how to commit fraud', 'bypass security measures', 'scam techniques'],
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                # Sensitive Personal Information
                {
                    'name': 'Personal Information',
                    'definition': 'Requests for personal or sensitive information',
                    'type': 'DENY',
                    'examples': ['what is my SSN', 'tell me my account balance', 'change my password'],
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                # Unauthorized Financial Advice
                {
                    'name': 'Financial Advice',
                    'definition': 'Providing financial or investment advice',
                    'type': 'DENY',
                    'examples': ['should I invest in', 'is this a good stock', 'financial planning advice'],
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                # Harmful Content
                {
                    'name': 'Harmful Content',
                    'definition': 'Content that promotes harm or illegal activities',
                    'type': 'DENY',
                    'examples': ['how to launder money', 'illegal transactions', 'bypass KYC'],
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                # Sensitive Banking Operations
                {
                    'name': 'Sensitive Operations',
                    'definition': 'High-risk banking operations that require additional verification',
                    'type': 'DENY',
                    'examples': ['wire transfer', 'change account details', 'update contact information'],
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                }
            ]
        }
        
    def _get_sensitive_info_policy_config(self):
        """
        Configure sensitive information policy for the guardrail.
        This defines what types of sensitive information should be protected.
        """
        return {
            'piiEntitiesConfig': [
                {
                    'type': 'US_SOCIAL_SECURITY_NUMBER',
                    'action': 'BLOCK',
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                {
                    'type': 'CREDIT_DEBIT_CARD_NUMBER',
                    'action': 'BLOCK',
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                {
                    'type': 'US_BANK_ACCOUNT_NUMBER',
                    'action': 'BLOCK',
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                {
                    'type': 'US_BANK_ROUTING_NUMBER',
                    'action': 'BLOCK',
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                },
                {
                    'type': 'US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER',
                    'action': 'BLOCK',
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                }
            ],
            'regexesConfig': [
                {
                    'name': 'Credit Card Number',
                    'pattern': r'\b(?:\d[ -]*?){13,16}\b',
                    'action': 'BLOCK',
                    'description': 'Detects credit card numbers'
                },
                {
                    'name': 'SSN',
                    'pattern': r'\b\d{3}[-\.]?\d{2}[-\.]?\d{4}\b',
                    'action': 'BLOCK',
                    'description': 'Detects Social Security Numbers'
                },
                {
                    'name': 'Bank Account Number',
                    'pattern': r'\b\d{8,17}\b',
                    'action': 'BLOCK',
                    'description': 'Detects potential bank account numbers'
                }
            ]
        }

    def _get_sensitive_actions_config(self):
        """Define sensitive actions that should trigger additional verification."""
        # Note: This is a placeholder for future implementation
        # Currently not supported in the Bedrock Guardrails API
        return None
        
    def _get_contextual_grounding_policy_config(self):
        """
        Configure contextual grounding policy for the guardrail.
        This ensures the model's responses are grounded in the provided context.
        """
        return {
            'filtersConfig': [
                {
                    'type': 'GROUNDING',
                    'enabled': True,
                    'action': 'BLOCK',
                    'threshold': 0.8
                },
                {
                    'type': 'RELEVANCE',
                    'enabled': True,
                    'action': 'BLOCK',  # Changed from 'WARN' to 'BLOCK' as per allowed values
                    'threshold': 0.7
                }
            ]
        }
        
    def _get_automated_reasoning_policy_config(self):
        """
        Configure automated reasoning policies for the guardrail.
        This includes settings for detecting and handling potentially harmful or inappropriate content.
        
        Returns:
            None: Automated reasoning requires a valid ARN which is not available.
        """
        # Automated reasoning requires a valid ARN which we don't have in this context
        # Returning None will skip this configuration
        return None
        
    def _get_voice_interaction_config(self):
        """
        Configure voice interaction settings for the guardrail.
        This includes voice selection, language, and other voice-related settings.
        """
        return {
            'voiceId': 'Joanna',  # Default voice
            'engine': 'neural',   # Neural engine for more natural sounding speech
            'languageCode': 'en-US',  # Default language
            'voiceSettings': {
                'speakingRate': 'medium',  # slow, medium, fast
                'pitch': 'medium',        # low, medium, high
                'volume': 'medium',       # low, medium, high
                'enableVoiceStyling': True  # Allow for expressive speech
            },
            'bargeInConfig': {
                'enabled': True,  # Allow users to interrupt the bot
                'sensitivity': 'HIGH'  # Sensitivity for detecting user speech
            },
            'speechRecognition': {
                'enableAutomaticPunctuation': True,
                'enableSpeakerDiarization': False,
                'enableWordTimeOffsets': True,
                'languageCode': 'en-US',
                'maxAlternatives': 1,
                'profanityFilter': True,
                'speechModel': 'CONVERSATION'  # CONVERSATION, PHONE_CALL, DICTATION
            },
            'emotionDetection': {
                'enabled': True,
                'sensitivity': 'MEDIUM'  # LOW, MEDIUM, HIGH
            },
            'interruptionHandling': {
                'enabled': True,
                'maxInterruptions': 3,  # Maximum number of allowed interruptions
                'timeoutSeconds': 5     # Timeout before considering the user done speaking
            },
            'fallbackToText': True,  # Fall back to text if voice recognition fails
            'enableBackgroundNoiseReduction': True,
            'enableEchoCancellation': True,
            'enableNoiseSuppression': True,
            'enableVoiceActivityDetection': True
        }

    def _get_content_policy_config(self):
        """
        Define content filtering policies for the guardrail.
        Includes profanity filtering and other content safety measures.
        """
        return {
            'filtersConfig': [
                # Hate speech filter - must be first as per enum order
                {
                    'type': 'HATE',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH',
                    'inputEnabled': True,
                    'outputEnabled': True,
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK'
                },
                # Insults filter
                {
                    'type': 'INSULTS',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH',
                    'inputEnabled': True,
                    'outputEnabled': True,
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK'
                },
                # Prompt attack filter
                {
                    'type': 'PROMPT_ATTACK',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'NONE',  # Must be NONE for PROMPT_ATTACK
                    'inputEnabled': True,
                    'outputEnabled': False,
                    'inputAction': 'BLOCK',
                    'outputAction': 'NONE'
                },
                # Sexual content filter
                {
                    'type': 'SEXUAL',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH',
                    'inputEnabled': True,
                    'outputEnabled': True,
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK'
                },
                # Violence filter
                {
                    'type': 'VIOLENCE',
                    'inputStrength': 'HIGH',
                    'outputStrength': 'HIGH',
                    'inputEnabled': True,
                    'outputEnabled': True,
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK'
                }
            ]
        }

    def _get_word_policy_config(self):
        """
        Define word-based filtering policies for the guardrail.
        This includes sensitive banking terms and PII that should be blocked.
        """
        sensitive_terms = [
            # Sensitive banking terms
            'password', 'passcode', 'security code', 'one-time password', 'MFA code',
            'wire transfer', 'SWIFT code', 'IBAN', 'account balance', 'overdraft',
            'account holder', 'signature', 'government ID', 'driver\'s license', 'passport number',
            'credit card number', 'CVV', 'expiration date', 'social security number', 'SSN',
            'routing number', 'account number', 'PIN', 'personal identification number'
        ]
        
        return {
            'wordsConfig': [
                {
                    'text': term,
                    'inputAction': 'BLOCK',
                    'outputAction': 'BLOCK',
                    'inputEnabled': True,
                    'outputEnabled': True
                } for term in sensitive_terms
            ]
        }
        
    def _get_voice_interaction_config(self):
        """Configure voice-specific interaction policies."""
        return {
            'voiceId': 'Joanna',
            'engine': 'neural',
            'languageCode': 'en-US'
        }

    def _validate_guardrail_config(self, config):
        """
        Validate the guardrail configuration before sending to AWS.
        
        Args:
            config (dict): The guardrail configuration to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        required_fields = [
            'name', 'description', 'blockedInputMessaging', 
            'blockedOutputsMessaging', 'contentPolicyConfig',
            'wordPolicyConfig', 'topicPolicyConfig'
        ]
        
        # Check for required fields
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            return False, f"Missing required fields: {', '.join(missing_fields)}"
            
        # Validate content policy config
        content_policy = config.get('contentPolicyConfig', {})
        if not isinstance(content_policy, dict):
            return False, "contentPolicyConfig must be a dictionary"
            
        # Validate word policy config
        word_policy = config.get('wordPolicyConfig', {})
        if not isinstance(word_policy, dict):
            return False, "wordPolicyConfig must be a dictionary"
            
        # Validate topic policy config
        topic_policy = config.get('topicPolicyConfig', {})
        if not isinstance(topic_policy, dict):
            return False, "topicPolicyConfig must be a dictionary"
            
        # Voice interaction config is not a valid parameter in the current API version
        # It has been removed from the configuration
        return True, ""

    def _handle_error(self, error):
        """
        Handle and display errors in a user-friendly way.
        
        Args:
            error: The exception that was raised
        """
        print("\n❌ Error creating banking guardrail:")
        print(f"   Error Type: {error.__class__.__name__}")
        
        # Handle boto3 client errors
        if hasattr(error, 'response'):
            error_response = error.response
            print(f"\n🔍 Error Details:")
            
            # Print error message if available
            if 'Error' in error_response and 'Message' in error_response['Error']:
                print(f"   • {error_response['Error']['Message']}")
                
            # Print error code if available
            if 'Error' in error_response and 'Code' in error_response['Error']:
                print(f"   • Error Code: {error_response['Error']['Code']}")
                
            # Print request ID if available
            if 'ResponseMetadata' in error_response and 'RequestId' in error_response['ResponseMetadata']:
                print(f"   • Request ID: {error_response['ResponseMetadata']['RequestId']}")
                
            # Handle specific error types
            if error.__class__.__name__ == 'ParamValidationError':
                print("\n🔧 Parameter Validation Error Details:")
                if hasattr(error, 'kwargs') and 'report' in error.kwargs:
                    for issue in error.kwargs['report']:
                        print(f"   • {issue}")
        else:
            # For non-boto3 errors
            print(f"\n🔍 Error Details:")
            print(f"   • {str(error)}")
            
        print("\n🔧 Please check the following:")
        print("   • AWS Bedrock service is enabled in your account")
        print("   • Your region supports Bedrock Guardrails")
        print("   • You're not hitting service limits")
        print("   • Your IAM user has the necessary permissions")

    def create_banking_guardrail(self, guardrail_name=None):
        """
        Create a comprehensive guardrail for a banking voice bot.
        Includes content filtering, topic controls, and sensitive information protection.
        
        Args:
            guardrail_name (str, optional): Name for the guardrail. If not provided, a timestamp will be appended.
            
        Returns:
            str: The ID of the created guardrail, or None if creation failed.
        """
        if not guardrail_name:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            guardrail_name = f"{self.base_guardrail_name}-{timestamp}"

        print(f"\n🚀 Creating new guardrail: {guardrail_name}")

        try:
            # Get all policy configurations
            content_policy = self._get_content_policy_config()
            topic_policy = self._get_topic_policy_config()
            word_policy = self._get_word_policy_config()
            sensitive_info_policy = self._get_sensitive_info_policy_config()
            contextual_grounding_policy = self._get_contextual_grounding_policy_config()
            automated_reasoning_policy = self._get_automated_reasoning_policy_config()

            # Prepare guardrail configuration with only supported parameters
            guardrail_config = {
                'name': guardrail_name,
                'description': 'Comprehensive guardrail for banking voice bot with enhanced security and compliance',
                'blockedInputMessaging': "I'm sorry, but I can't process that request. For security reasons, certain actions require additional verification.",
                'blockedOutputsMessaging': "I'm sorry, but I can't provide that information through this channel. Please contact customer service for assistance.",
                'contentPolicyConfig': content_policy,
                'topicPolicyConfig': topic_policy,
                'wordPolicyConfig': word_policy,
                'sensitiveInformationPolicyConfig': sensitive_info_policy,
                'contextualGroundingPolicyConfig': contextual_grounding_policy,
                'tags': [
                    {'key': 'environment', 'value': 'production'},
                    {'key': 'department', 'value': 'customer_service'},
                    {'key': 'compliance', 'value': 'pci-dss'},
                    {'key': 'managed_by', 'value': 'security_team'}
                ]
            }
            
            # Only add automatedReasoningPolicyConfig if it's not None
            if automated_reasoning_policy is not None:
                guardrail_config['automatedReasoningPolicyConfig'] = automated_reasoning_policy

            # Load environment variables from .env file
            from dotenv import load_dotenv
            load_dotenv()
            
            # Get KMS key from .env file
            kms_key_id = os.getenv('KMS_KEY_ID')
            # KMS key is required for guardrail creation
            if not kms_key_id:
                raise ValueError(
                    "❌ KMS key is required for guardrail creation.\n"
                    "Please provide a valid KMS key ARN in your .env file.\n"
                    "Example: KMS_KEY_ARN=arn:aws:kms:region:account-id:key/key-id\n\n"
                    "You can create a KMS key in the AWS Console or using the AWS CLI:\n"
                    "1. Create a KMS key: aws kms create-key --description 'Bedrock Guardrail Key'\n"
                    "2. Get the key ARN and add it to your .env file"
                )
            
            # Verify the KMS key exists and is accessible
            try:
                kms = boto3.client('kms',
                                 aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                                 aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                                 region_name=self.region)
                
                # Try to describe the key to verify it exists and is accessible
                key_info = kms.describe_key(KeyId=kms_key_id)
                key_arn = key_info['KeyMetadata']['Arn']
                
                # Verify the key is enabled
                if key_info['KeyMetadata']['KeyState'] != 'Enabled':
                    raise ValueError(f"KMS key {kms_key_id} is not in 'Enabled' state")
                
                # Add the key to the guardrail config
                guardrail_config['kmsKeyId'] = kms_key_id
                print(f"🔑 Using KMS Key: {key_arn}")
                
            except Exception as e:
                raise ValueError(
                    f"❌ Error accessing KMS key {kms_key_id}: {str(e)}\n"
                    "Please verify that:\n"
                    f"1. The KMS key ARN is correct: {kms_key_id}\n"
                    "2. The key exists in the same region as your Bedrock guardrail\n"
                    "3. Your IAM user has the following permissions on the key:\n"
                    "   - kms:DescribeKey\n"
                    "   - kms:CreateGrant\n"
                    "   - kms:Encrypt\n"
                    "   - kms:Decrypt"
                )
            
            # Validate the configuration before sending to AWS
            is_valid, error_msg = self._validate_guardrail_config(guardrail_config)
            if not is_valid:
                raise ValueError(f"Invalid guardrail configuration: {error_msg}")
            
            # Debug: Print the configuration being sent
            print("\n📝 Guardrail Configuration:")
            print(json.dumps(guardrail_config, indent=2, default=str))
            
            # Create the guardrail
            print("\n🔄 Creating guardrail...")
            try:
                response = self.client.create_guardrail(**guardrail_config)
                
                if 'guardrailId' in response:
                    guardrail_id = response['guardrailId']
                    print(f"\n✅ Guardrail created successfully!")
                    print(f"   • Guardrail ID: {guardrail_id}")
                    print(f"   • Name: {guardrail_name}")
                    print(f"   • Region: {self.region}")
                    
                    # Save guardrail details to a file for reference
                    with open('guardrail_details.json', 'w') as f:
                        json.dump({
                            'guardrail_id': guardrail_id,
                            'name': guardrail_name,
                            'region': self.region,
                            'created_at': datetime.now().isoformat(),
                            'arn': response.get('guardrailArn')
                        }, f, indent=2)
                    
                    return guardrail_id
                else:
                    print("\n❌ Failed to create guardrail. No guardrail ID in response.")
                    print("Response from API:", json.dumps(response, indent=2, default=str))
                    return None
                    
            except Exception as e:
                print(f"\n❌ Error creating guardrail: {str(e)}")
                if hasattr(e, 'response') and 'Error' in e.response:
                    print("\n🔍 Error details:")
                    print(f"   • Error Code: {e.response['Error'].get('Code', 'Unknown')}")
                    print(f"   • Message: {e.response['Error'].get('Message', 'No error message')}")
                    print(f"   • Request ID: {e.response.get('ResponseMetadata', {}).get('RequestId', 'N/A')}")
                    
                    # Print additional error details if available
                    if 'Error' in e.response and 'Message' in e.response['Error']:
                        print("\nAdditional error context:")
                        print(e.response['Error']['Message'])
                return None

        except Exception as e:
            self._handle_error(e)
            return None


def main():
    print("🚀 Setting up Banking Voice Bot Guardrail...")
    print("🔒 Configuring security policies for financial services...\n")
    
    guardrail_manager = BankingGuardrailManager()
    guardrail_id = guardrail_manager.create_banking_guardrail()
    
    if guardrail_id:
        print("\n🎉 Guardrail deployment completed successfully!")
        print("Next steps:")
        print("1. Test the guardrail with sample banking conversations")
        print("2. Review the guardrail settings in the AWS Management Console")
        print("3. Integrate the guardrail ID with your voice bot application")


if __name__ == "__main__":
    main()