import boto3
from botocore.exceptions import ClientError
import json
import logging
from datetime import datetime
import os

# Constants
AWS_REGION = "us-east-1"

# Orchestrate the deployment
DOMAIN_NAME = "ironcliff.ai"
FRONTEND_SUBDOMAIN = "ra"
BACKEND_SUBDOMAIN = "ra-api"
EB_APP_NAME = "ra-app"
EB_ENV_NAME = "ra-env"

frontend_domain = f"{FRONTEND_SUBDOMAIN}.{DOMAIN_NAME}"
backend_domain = f"{BACKEND_SUBDOMAIN}.{DOMAIN_NAME}"
s3 = boto3.client("s3", region_name=AWS_REGION)

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Generate log filename with timestamp
log_filename = f"logs/deployment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log the start of the script with some basic info
logger.info("=" * 80)
logger.info("Starting AWS Deployment Script")
logger.info(f"Log file: {log_filename}")
logger.info(f"AWS Region: {AWS_REGION}")
logger.info(f"Domain: {DOMAIN_NAME}")
logger.info(f"Frontend Domain: {frontend_domain}")
logger.info(f"Backend Domain: {backend_domain}")
logger.info("=" * 80)


def create_s3_bucket(domain_name):
    """
    Creates and configures an S3 bucket for static website hosting.
    
    Args:
        domain_name (str): The domain name to use as the bucket name
        
    Returns:
        dict: Contains status and website_url if successful, or error message if failed
    """
    logger.info(f"Starting S3 bucket creation for domain: {domain_name}")
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3')
        logger.info(f"Creating bucket '{domain_name}' in region {s3_client.meta.region_name}")
        
        # Step 1: Create the bucket with public access
        # Special handling for us-east-1 region
        if s3_client.meta.region_name == 'us-east-1':
            logger.info("Using special configuration for us-east-1 region")
            s3_client.create_bucket(
                Bucket=domain_name,
                ObjectOwnership='ObjectWriter'  # Required for public access
            )
        else:
            s3_client.create_bucket(
                Bucket=domain_name,
                CreateBucketConfiguration={
                    'LocationConstraint': s3_client.meta.region_name
                },
                ObjectOwnership='ObjectWriter'  # Required for public access
            )
        logger.info(f"Successfully created bucket: {domain_name}")
        
        # Disable block public access
        logger.info("Configuring public access settings")
        s3_client.put_public_access_block(
            Bucket=domain_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': False,
                'IgnorePublicAcls': False,
                'BlockPublicPolicy': False,
                'RestrictPublicBuckets': False
            }
        )
        logger.info("Public access block settings updated")
        
        # Step 2: Set bucket policy for public read access
        logger.info("Setting bucket policy for public read access")
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadGetObject",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{domain_name}/*"]
                }
            ]
        }
        
        # Convert policy to JSON string and apply it
        s3_client.put_bucket_policy(
            Bucket=domain_name,
            Policy=json.dumps(bucket_policy)
        )
        logger.info("Bucket policy applied successfully")
        
        # Step 3: Enable static website hosting
        logger.info("Configuring static website hosting")
        website_configuration = {
            'ErrorDocument': {'Key': 'index.html'},
            'IndexDocument': {'Suffix': 'index.html'}
        }
        
        s3_client.put_bucket_website(
            Bucket=domain_name,
            WebsiteConfiguration=website_configuration
        )
        logger.info("Static website hosting configured")
        
        # Get the website URL
        website_url = f"http://{domain_name}.s3-website-{s3_client.meta.region_name}.amazonaws.com"
        logger.info(f"Website URL: {website_url}")
        
        return {
            'status': 'success',
            'message': 'Bucket created and configured successfully',
            'website_url': website_url
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        # Handle specific error cases
        if error_code == 'BucketAlreadyOwnedByYou':
            logger.warning(f"Bucket {domain_name} already exists and is owned by you")
            return {
                'status': 'error',
                'message': f'Bucket {domain_name} already exists and is owned by you'
            }
        elif error_code == 'BucketAlreadyExists':
            logger.error(f"Bucket {domain_name} already exists and is owned by another AWS account")
            return {
                'status': 'error',
                'message': f'Bucket {domain_name} already exists and is owned by another AWS account'
            }
        else:
            logger.error(f"Error creating bucket: {error_message}")
            return {
                'status': 'error',
                'message': f'Error creating bucket: {error_message}'
            }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': f'Unexpected error: {str(e)}'
        }

if __name__ == "__main__":
    logger.info("Starting deployment process")
    result = create_s3_bucket(frontend_domain)
    logger.info(f"Deployment result: {result}")
