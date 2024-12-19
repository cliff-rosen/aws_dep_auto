import boto3

# Constants
AWS_REGION = "us-east-1"
DB_INSTANCE_CLASS = "db.t3.medium"
DB_STORAGE_SIZE = 20
DB_PUBLIC_ACCESS = False
REACT_BUILD_PATH = "/path/to/build"

# Initialize AWS clients
s3 = boto3.client("s3", region_name=AWS_REGION)
cloudfront = boto3.client("cloudfront", region_name=AWS_REGION)
route53 = boto3.client("route53", region_name=AWS_REGION)
elasticbeanstalk = boto3.client("elasticbeanstalk", region_name=AWS_REGION)
rds = boto3.client("rds", region_name=AWS_REGION)
acm = boto3.client("acm", region_name=AWS_REGION)

# Step 1: Create S3 Bucket
def create_s3_bucket(domain_name):
    bucket_name = domain_name
    s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": AWS_REGION})
    s3.put_bucket_policy(
        Bucket=bucket_name,
        Policy=f"""
        {{
            "Version": "2012-10-17",
            "Statement": [
                {{
                    "Sid": "PublicReadGetObject",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": "arn:aws:s3:::{bucket_name}/*"
                }}
            ]
        }}
        """,
    )
    s3.put_bucket_website(
        Bucket=bucket_name,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "index.html"},
        },
    )
    print(f"S3 bucket '{bucket_name}' created and configured.")

# Step 2: Create CloudFront Distribution
def create_cloudfront_distribution(domain_name, certificate_arn):
    response = cloudfront.create_distribution(
        DistributionConfig={
            "CallerReference": domain_name,
            "Aliases": {"Quantity": 1, "Items": [domain_name]},
            "DefaultRootObject": "index.html",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "S3-" + domain_name,
                        "DomainName": f"{domain_name}.s3.amazonaws.com",
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                    }
                ],
            },
            "DefaultCacheBehavior": {
                "TargetOriginId": "S3-" + domain_name,
                "ViewerProtocolPolicy": "redirect-to-https",
                "AllowedMethods": {
                    "Quantity": 2,
                    "Items": ["GET", "HEAD"],
                    "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
                },
                "ForwardedValues": {"QueryString": False, "Cookies": {"Forward": "none"}},
                "MinTTL": 0,
            },
            "ViewerCertificate": {
                "ACMCertificateArn": certificate_arn,
                "SSLSupportMethod": "sni-only",
                "MinimumProtocolVersion": "TLSv1.2_2021",
            },
            "Enabled": True,
        }
    )
    print(f"CloudFront distribution created: {response['Distribution']['Id']}")

# Step 3: Create Route 53 DNS Records
def create_route53_record(hosted_zone_id, domain_name, cloudfront_distribution):
    route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": domain_name,
                        "Type": "A",
                        "AliasTarget": {
                            "HostedZoneId": "Z2FDTNDATAQYW2",  # CloudFront Hosted Zone ID
                            "DNSName": f"{cloudfront_distribution}.cloudfront.net",
                            "EvaluateTargetHealth": False,
                        },
                    },
                }
            ]
        },
    )
    print(f"Route 53 record created for {domain_name}.")

# Step 4: Create Elastic Beanstalk Environment
def create_eb_environment(app_name, env_name, domain_name):
    elasticbeanstalk.create_application(ApplicationName=app_name)
    elasticbeanstalk.create_environment(
        ApplicationName=app_name,
        EnvironmentName=env_name,
        SolutionStackName="64bit Amazon Linux 2 v3.3.5 running Python 3.8",
        OptionSettings=[
            {"Namespace": "aws:elasticbeanstalk:application:environment", "OptionName": "DJANGO_SETTINGS_MODULE", "Value": "mysite.settings"},
            {"Namespace": "aws:elasticbeanstalk:environment", "OptionName": "EnvironmentType", "Value": "LoadBalanced"},
            {"Namespace": "aws:autoscaling:launchconfiguration", "OptionName": "InstanceType", "Value": "t2.micro"},
        ],
    )
    print(f"Elastic Beanstalk environment '{env_name}' created.")

# Step 5: Create RDS Database
def create_rds_instance(db_name):
    rds.create_db_instance(
        DBName=db_name,
        DBInstanceIdentifier=db_name,
        AllocatedStorage=DB_STORAGE_SIZE,
        DBInstanceClass=DB_INSTANCE_CLASS,
        Engine="mariadb",
        MasterUsername="admin",
        MasterUserPassword="yourpassword",
        PubliclyAccessible=DB_PUBLIC_ACCESS,
    )
    print(f"RDS database '{db_name}' created.")

# export the functions and constants  
__all__ = ["create_s3_bucket", "create_cloudfront_distribution", "create_route53_record", "create_eb_environment", "create_rds_instance", "AWS_REGION", "DB_INSTANCE_CLASS", "DB_STORAGE_SIZE", "DB_PUBLIC_ACCESS", "REACT_BUILD_PATH"]


