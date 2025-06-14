# Standard Library
from typing import Optional, List, Literal

# Third Party
from aws_cdk import aws_iam as iam
from constructs import Construct


class CustomIamRole(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: Optional[str] = None,
        stack_suffix: Optional[str] = "",
        assumed_by: Optional[
            Literal["lambda.amazonaws.com"]
        ] = "lambda.amazonaws.com",
        managed_policies: Optional[List[iam.IManagedPolicy]] = None,
        inline_policies: Optional[List[iam.Policy]] = None,
        **kwargs,
    ) -> None:
        """Custom IAM Role Construct for AWS CDK.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        assumed_by : iam.IPrincipal
            The principal that can assume this role.
        managed_policies : Optional[List[iam.IManagedPolicy]], optional
            List of managed policies to attach to the role, by default None
        inline_policies : Optional[List[iam.Policy]], optional
            List of inline policies to attach to the role, by default None
        role_name : Optional[str], optional
            Name of the IAM role, by default None
        """
        super().__init__(scope, id, **kwargs)

        # Create the IAM Role
        self.role = iam.Role(
            scope=self,
            id=f"DefaultRole{stack_suffix}",
            role_name=f"{name}{stack_suffix}",
            assumed_by=iam.ServicePrincipal(assumed_by),
            managed_policies=managed_policies
            or [
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            inline_policies=inline_policies,
        )
