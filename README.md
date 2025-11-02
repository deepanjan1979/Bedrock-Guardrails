# AWS Bedrock Guardrails for Banking Voice Bot

This project provides guardrail configurations and utilities for AWS Bedrock, specifically designed for banking voice bot applications. It includes security policies, content filtering, and contextual grounding checks to ensure safe and compliant AI interactions in financial services.

## Features

- **Content Filtering**: Block inappropriate or sensitive content
- **Contextual Grounding**: Ensure responses are factually consistent with provided context
- **Sensitive Information Protection**: Detect and protect PII and financial information
- **Voice Interaction Settings**: Configure voice-specific parameters
- **KMS Integration**: Secure encryption for sensitive data

## Prerequisites

- Python 3.8+
- AWS Account with Bedrock access
- AWS CLI configured with appropriate permissions
- Required Python packages (see `requirements.txt`)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/bedrock-guardrails.git
   cd bedrock-guardrails
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # On Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on `.env.example` and fill in your AWS credentials and KMS key ARN.

## Usage

1. Configure your `.env` file with the required credentials:
   ```
   AWS_ACCESS_KEY_ID=your_access_key
   AWS_SECRET_ACCESS_KEY=your_secret_key
   AWS_DEFAULT_REGION=your_region
   KMS_KEY_ARN=your_kms_key_arn
   KMS_KEY_ALIAS=your_kms_key_alias
   ```

2. Run the guardrail creation script:
   ```bash
   python create_guardrail.py
   ```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Security

- Never commit your `.env` file or any sensitive credentials
- Use IAM roles and policies to restrict access to only necessary AWS resources
- Regularly rotate your AWS access keys
