# Standard Library
from typing import Optional

# Third-Party
from aws_cdk import aws_dynamodb as dynamodb, RemovalPolicy
from constructs import Construct


class CustomDynamoDBTable(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        partition_key: dynamodb.Attribute,
        stack_suffix: Optional[str] = "",
        sort_key: Optional[dynamodb.Attribute] = None,
        removal_policy: Optional[RemovalPolicy] = RemovalPolicy.DESTROY,
        time_to_live_attribute: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Append stack suffix to name if provided
        if stack_suffix:
            name = f"{name}-{stack_suffix}"

        # Create the DynamoDB table
        self.table = dynamodb.Table(
            self,
            "DefaultTable",
            table_name=name,
            partition_key=partition_key,
            sort_key=sort_key,
            removal_policy=removal_policy,
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute=time_to_live_attribute,
        )
