import boto3
from botocore.exceptions import ClientError
import json
import logging
from datetime import datetime
import os
import time

# Instructions:
#1. Before running script:
#  create eb app and env and then deploy
#  update the orchestration variables below
#2. After running script, npm run build and copy files to S3 bucket


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

def create_acm_certificate(frontend_domain, backend_domain):
    """
    Creates and validates an ACM certificate for the domain and alternative names
    
    Args:
        domain_name (str): Main domain name (e.g., 'ironcliff.ai')
        alternative_names (list): List of full domain names (e.g., ['ra.ironcliff.ai', 'ra-api.ironcliff.ai'])
        
    Returns:
        str: Certificate ARN if successful, None if failed
    """
    logger.info(f"Creating ACM certificate for {frontend_domain} and alternative names {backend_domain}")
    
    try:
        acm_client = boto3.client('acm', region_name=AWS_REGION)
        
        # Request certificate
        response = acm_client.request_certificate(
            DomainName=frontend_domain,
            ValidationMethod='DNS',
            SubjectAlternativeNames=[backend_domain]
        )
        
        certificate_arn = response['CertificateArn']
        logger.info(f"Certificate requested successfully. ARN: {certificate_arn}")
        
        return certificate_arn
        
    except ClientError as e:
        logger.error(f"Error requesting certificate: {str(e)}")
        return None

def create_cloudfront_distribution(
        domain_name,
        certificate_arn
    ):
    """
    Creates a CloudFront distribution for the S3 bucket
    
    Args:
        domain_name (str): Domain name for the distribution
        s3_bucket_website_endpoint (str): S3 bucket website endpoint (e.g., bucket-name.s3-website-region.amazonaws.com)
        certificate_arn (str): ACM certificate ARN
        
    Returns:
        dict: Distribution details if successful, None if failed
    """
    logger.info(f"Creating CloudFront distribution for {domain_name}")

    # Get S3 website endpoint for existing bucket
    s3_website_endpoint = get_s3_website_endpoint(frontend_domain)
    logger.info(f"Using S3 website endpoint: {s3_website_endpoint}")

    try:
        cloudfront_client = boto3.client('cloudfront')
        
        distribution_config = {
            'CallerReference': str(datetime.now().timestamp()),
            'Comment': f'Distribution for {domain_name}',
            'Aliases': {
                'Quantity': 1,
                'Items': [domain_name]
            },
            'DefaultRootObject': 'index.html',
            'Origins': {
                'Quantity': 1,
                'Items': [{
                    'Id': 'S3Origin',
                    'DomainName': s3_website_endpoint,
                    'CustomOriginConfig': {
                        'HTTPPort': 80,
                        'HTTPSPort': 443,
                        'OriginProtocolPolicy': 'http-only'
                    }
                }]
            },
            'DefaultCacheBehavior': {
                'TargetOriginId': 'S3Origin',
                'ViewerProtocolPolicy': 'redirect-to-https',
                'AllowedMethods': {
                    'Quantity': 7,
                    'Items': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE'],
                    'CachedMethods': {
                        'Quantity': 2,
                        'Items': ['GET', 'HEAD']
                    }
                },
                'CachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad',  # CachingDisabled policy
                'OriginRequestPolicyId': '88a5eaf4-2fd4-4709-b370-b4c650ea3fcf',  # CORS-S3Origin
                'ResponseHeadersPolicyId': '60669652-455b-4ae9-85a4-c4c02393f86c'  # SimpleCORS
            },
            'ViewerCertificate': {
                'ACMCertificateArn': certificate_arn,
                'SSLSupportMethod': 'sni-only',
                'MinimumProtocolVersion': 'TLSv1.2_2021'
            },
            'Enabled': True,
            'WebACLId': ''  # Explicitly not enabling WAF
        }
        
        response = cloudfront_client.create_distribution(
            DistributionConfig=distribution_config
        )
        
        logger.info(f"CloudFront distribution created successfully")
        return response['Distribution']
        
    except ClientError as e:
        logger.error(f"Error creating CloudFront distribution: {str(e)}")
        return None

def get_s3_website_endpoint(bucket_name, region=AWS_REGION):
    """
    Gets the S3 website endpoint for an existing bucket
    
    Args:
        bucket_name (str): Name of the S3 bucket (e.g., ra.ironcliff.ai)
        region (str): AWS region
        
    Returns:
        str: Website endpoint URL
    """
    try:
        s3_client = boto3.client('s3')
        
        # Try to get the website configuration to confirm bucket exists and has website enabled
        try:
            s3_client.get_bucket_website(Bucket=bucket_name)
            logger.info(f"Found website configuration for bucket {bucket_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchWebsiteConfiguration':
                logger.error(f"Bucket {bucket_name} does not have website hosting enabled")
            else:
                logger.error(f"Error checking bucket website config: {str(e)}")
            return None

        # Return the bucket website endpoint
        return f"{bucket_name}.s3-website-{region}.amazonaws.com"
        
    except ClientError as e:
        logger.error(f"Error getting S3 website endpoint: {str(e)}")
        return None

def create_frontend_route53_record(domain_name, cloudfront_domain_name):
    """
    Creates Route53 A record pointing to CloudFront distribution
    
    Args:
        domain_name (str): Domain name for the record (e.g., ra.ironcliff.ai)
        cloudfront_domain_name (str): CloudFront distribution domain name
    """
    try:
        route53_client = boto3.client('route53')
        
        # Get the hosted zone ID for the domain
        hosted_zones = route53_client.list_hosted_zones()
        zone_id = None
        base_domain = '.'.join(domain_name.split('.')[-2:])  # Get base domain (e.g., ironcliff.ai)
        
        for zone in hosted_zones['HostedZones']:
            if zone['Name'].rstrip('.') == base_domain:
                zone_id = zone['Id']
                break
        
        if not zone_id:
            logger.error(f"No hosted zone found for domain {base_domain}")
            return None
        
        # Create A record
        response = route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': domain_name,
                        'Type': 'A',
                        'AliasTarget': {
                            'HostedZoneId': 'Z2FDTNDATAQYW2',  # CloudFront's hosted zone ID (constant)
                            'DNSName': cloudfront_domain_name,
                            'EvaluateTargetHealth': False
                        }
                    }
                }]
            }
        )
        
        logger.info(f"Route53 record created/updated successfully")
        return response
        
    except ClientError as e:
        logger.error(f"Error creating Route53 record: {str(e)}")
        return None

def wait_for_eb_environment_ready(environment_name, timeout_seconds=300):
    """
    Waits for an Elastic Beanstalk environment to be ready
    
    Args:
        environment_name (str): Name of the Elastic Beanstalk environment
        timeout_seconds (int): Maximum time to wait in seconds
        
    Returns:
        bool: True if environment is ready, False if timeout occurred
    """
    logger.info(f"Waiting for environment {environment_name} to be ready...")
    eb_client = boto3.client('elasticbeanstalk', region_name=AWS_REGION)
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            response = eb_client.describe_environments(
                EnvironmentNames=[environment_name],
                IncludeDeleted=False
            )
            
            if not response['Environments']:
                logger.error(f"Environment {environment_name} not found")
                return False
                
            status = response['Environments'][0]['Status']
            health = response['Environments'][0]['Health']
            
            logger.info(f"Environment status: {status}, health: {health}")
            
            if status == 'Ready':
                logger.info(f"Environment {environment_name} is ready")
                return True
                
            time.sleep(10)  # Wait 10 seconds before checking again
            
        except ClientError as e:
            logger.error(f"Error checking environment status: {str(e)}")
            return False
            
    logger.error(f"Timeout waiting for environment {environment_name} to be ready")
    return False

def configure_eb_https(environment_name, certificate_arn):
    try:
        if not wait_for_eb_environment_ready(environment_name):
            logger.error("Environment not ready, aborting HTTPS configuration")
            return None
            
        eb_client = boto3.client('elasticbeanstalk', region_name=AWS_REGION)
        
        option_settings = [
            # HTTPS Listener
            {
                'Namespace': 'aws:elbv2:listener:443',
                'OptionName': 'Protocol',
                'Value': 'HTTPS'
            },
            {
                'Namespace': 'aws:elbv2:listener:443',
                'OptionName': 'SSLCertificateArns',
                'Value': certificate_arn
            },
            {
                'Namespace': 'aws:elbv2:listener:443',
                'OptionName': 'DefaultProcess',
                'Value': 'default'
            },
            # HTTP Listener
            {
                'Namespace': 'aws:elbv2:listener:80',
                'OptionName': 'Protocol',
                'Value': 'HTTP'
            },
            {
                'Namespace': 'aws:elbv2:listener:80',
                'OptionName': 'DefaultProcess',
                'Value': 'default'
            },
            # Define the redirect process
            {
                'Namespace': 'aws:elasticbeanstalk:environment:process:redirect',
                'OptionName': 'Port',
                'Value': '443'
            },
            {
                'Namespace': 'aws:elasticbeanstalk:environment:process:redirect',
                'OptionName': 'Protocol',
                'Value': 'HTTPS'
            },
            # Define the redirect rule
            {
                'Namespace': 'aws:elbv2:listenerrule:redirect',
                'OptionName': 'PathPatterns',
                'Value': '/*'
            },
            {
                'Namespace': 'aws:elbv2:listenerrule:redirect',
                'OptionName': 'Priority',
                'Value': '1'
            },
            {
                'Namespace': 'aws:elbv2:listenerrule:redirect',
                'OptionName': 'Process',
                'Value': 'redirect'
            }
        ]
        
        response = eb_client.update_environment(
            EnvironmentName=environment_name,
            OptionSettings=option_settings
        )
        
        logger.info("HTTPS configuration updated successfully")
        
        if wait_for_eb_environment_ready(environment_name):
            logger.info("HTTPS configuration changes applied successfully")
        else:
            logger.warning("Environment not ready after applying changes, but changes were submitted")
            
        return response
        
    except ClientError as e:
        logger.error(f"Error configuring HTTPS for Elastic Beanstalk: {str(e)}")
        return None

def create_backend_route53_record(domain_name):
    """
    Creates Route53 A record pointing to Elastic Beanstalk environment
    
    Args:
        domain_name (str): Domain name for the record (e.g., ra-api.ironcliff.ai)
    """
    try:
        route53_client = boto3.client('route53')
        eb_client = boto3.client('elasticbeanstalk', region_name=AWS_REGION)
        
        # Get the EB environment CNAME
        eb_env = eb_client.describe_environments(
            EnvironmentNames=[EB_ENV_NAME],
            IncludeDeleted=False
        )['Environments'][0]
        
        eb_cname = eb_env['CNAME']
        
        # Get the hosted zone ID for the domain
        hosted_zones = route53_client.list_hosted_zones()
        zone_id = None
        base_domain = '.'.join(domain_name.split('.')[-2:])  # Get base domain (e.g., ironcliff.ai)
        
        for zone in hosted_zones['HostedZones']:
            if zone['Name'].rstrip('.') == base_domain:
                zone_id = zone['Id']
                break
        
        if not zone_id:
            logger.error(f"No hosted zone found for domain {base_domain}")
            return None
        
        # Create A record
        response = route53_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': domain_name,
                        'Type': 'CNAME',
                        'TTL': 300,
                        'ResourceRecords': [{'Value': eb_cname}]
                    }
                }]
            }
        )
        
        logger.info(f"Route53 record created/updated successfully for backend")
        return response
        
    except ClientError as e:
        logger.error(f"Error creating Route53 record for backend: {str(e)}")
        return None

def deploy_app():
    logger.info("Starting deployment process")
    
    # Create S3 bucket
    s3_result = create_s3_bucket(frontend_domain)
    logger.info(f"S3 bucket creation result: {s3_result}")
    
    # Create certificate - pass the full domain names
    cert_arn = create_acm_certificate(
        frontend_domain,
        backend_domain
    )
    logger.info(f"Certificate creation result: {cert_arn}")

    # pause for certificate to be ready
    time.sleep(10)

    # Create CloudFront distribution
    cloudfront_distribution = create_cloudfront_distribution(
        frontend_domain,
        cert_arn
    )
    logger.info(f"CloudFront distribution creation result: {cloudfront_distribution}")
    
    # Create Route53 record for frontend
    create_frontend_route53_record(frontend_domain, cloudfront_distribution['DomainName'])

    # Configure HTTPS for Elastic Beanstalk
    configure_eb_https(EB_ENV_NAME, cert_arn)
    
    # Create Route53 record for backend
    create_backend_route53_record(backend_domain)


cert_arn = "arn:aws:acm:us-east-1:183944926635:certificate/7ac292e7-f387-4805-abbf-2c28d9e59129"
eb_result = configure_eb_https(EB_ENV_NAME, cert_arn)

# be_route53_result = create_backend_route53_record(backend_domain)
