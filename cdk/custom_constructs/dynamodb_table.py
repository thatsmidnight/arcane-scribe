# Standard Library
from typing import Optional

# Third Party
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
        """Custom DynamoDB Table Construct for AWS CDK.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        name : str
            The name of the DynamoDB table.
        partition_key : dynamodb.Attribute
            The partition key for the DynamoDB table.
        stack_suffix : Optional[str], optional
            Suffix to append to the DynamoDB table name, by default ""
        sort_key : Optional[dynamodb.Attribute], optional
            The sort key for the DynamoDB table, by default None
        removal_policy : Optional[RemovalPolicy], optional
            The removal policy for the DynamoDB table, by default
            RemovalPolicy.DESTROY
        time_to_live_attribute : Optional[str], optional
            The attribute name for time to live (TTL) in the DynamoDB table,
            by default None (no TTL configured)
        """
        super().__init__(scope, id, **kwargs)

        # Append stack suffix to name if provided
        if stack_suffix:
            name = f"{name}{stack_suffix}"

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
