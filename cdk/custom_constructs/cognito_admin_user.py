# Standard Library
import os

# Third Party
from aws_cdk import (
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    custom_resources as cr,
    CustomResource,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class CognitoAdminUser(Construct):
    """
    A custom construct that creates a Cognito admin user with a password
    from AWS Secrets Manager.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        user_pool: cognito.IUserPool,
        admin_username: str,
        admin_email: str,
        admin_password_secret_name: str,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # This is the inline Python code for the Lambda function handler.
        # It's placed here for encapsulation, making the construct self-contained.
        lambda_handler_code = """
import boto3
import json
import cfnresponse
import os

cognito_client = boto3.client('cognito-idp')
secrets_client = boto3.client('secretsmanager')

def get_password_from_secret(secret_name):
    print(f"Fetching password from Secrets Manager secret: {secret_name}")
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

def lambda_handler(event, context):
    props = event.get('ResourceProperties', {})
    user_pool_id = props.get('UserPoolId')
    user_name = props.get('UserName')
    user_email = props.get('UserEmail')
    secret_name = props.get('PasswordSecretName')
    physical_resource_id = f'{user_pool_id}-{user_name}'

    try:
        if event['RequestType'] == 'Create' or event['RequestType'] == 'Update':
            print(
                f"Creating or updating user: {user_name} in pool: {user_pool_id}"
            )
            password = get_password_from_secret(secret_name)

            # Create the user without a temporary password
            cognito_client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=user_name,
                UserAttributes=[
                    {'Name': 'email', 'Value': user_email},
                    {'Name': 'email_verified', 'Value': 'true'}
                ],
                MessageAction='SUPPRESS' # Do not send an invitation email
            )

            # Set the password permanently
            cognito_client.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username=user_name,
                Password=password,
                Permanent=True
            )
            print(
                f"Successfully created and set password for user: {user_name}"
            )

        elif event['RequestType'] == 'Delete':
            print(f"Deleting user: {user_name} from pool: {user_pool_id}")
            try:
                cognito_client.admin_delete_user(
                    UserPoolId=user_pool_id,
                    Username=user_name
                )
                print(f"Successfully deleted user: {user_name}")
            except cognito_client.exceptions.UserNotFoundException:
                # If user doesn't exist, it's a success for deletion.
                print(f"User {user_name} not found. Assuming already deleted.")
                pass

        cfnresponse.send(
            event, context, cfnresponse.SUCCESS, {}, physical_resource_id
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        # Truncate the error message to fit within the 4KB limit
        error_message = f"Error: {str(e)}"
        truncated_message = error_message[:1024] # Truncate to a safe length
        cfnresponse.send(
            event,
            context,
            cfnresponse.FAILED,
            {"Error": truncated_message},
            physical_resource_id,
        )

"""

        # IAM Role for the Lambda function
        lambda_role = iam.Role(
            self,
            "AdminUserLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Grant necessary permissions to the Lambda function
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminSetUserPassword",
                    "cognito-idp:AdminDeleteUser",
                ],
                resources=[user_pool.user_pool_arn],
            )
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                # Be specific about which secret can be read
                resources=[
                    f"arn:aws:secretsmanager:{os.environ['CDK_DEFAULT_REGION']}:{os.environ['CDK_DEFAULT_ACCOUNT']}:secret:{admin_password_secret_name}-*"
                ],
            )
        )

        # We need the cfnresponse library for our Lambda.
        # The Custom Resource Provider framework can bundle it for us.
        provider = cr.Provider(
            self,
            "AdminUserProvider",
            on_event_handler=_lambda.Function(
                self,
                "AdminUserEventHandler",
                runtime=_lambda.Runtime.PYTHON_3_12,
                handler="index.lambda_handler",
                code=_lambda.Code.from_inline(lambda_handler_code),
                role=lambda_role,
                timeout=Duration.minutes(5),
            ),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # The actual Custom Resource
        CustomResource(
            self,
            "AdminUserResource",
            service_token=provider.service_token,
            properties={
                "UserPoolId": user_pool.user_pool_id,
                "UserName": admin_username,
                "UserEmail": admin_email,
                "PasswordSecretName": admin_password_secret_name,
            },
            removal_policy=RemovalPolicy.DESTROY,
        )
