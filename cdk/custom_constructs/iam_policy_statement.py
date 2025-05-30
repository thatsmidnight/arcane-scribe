# Standard Library
from typing import Optional, List

# Third Party
from aws_cdk import aws_iam as iam
from constructs import Construct


class CustomIAMPolicyStatement(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        actions: List[str],
        resources: List[str],
        effect: Optional[iam.Effect] = iam.Effect.ALLOW,
        conditions: Optional[dict] = None,
        **kwargs,
    ) -> None:
        """Custom IAM Policy Statement Construct for AWS CDK.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        actions : List[str]
            List of IAM actions to allow or deny.
        resources : List[str]
            List of resources the actions apply to.
        effect : Optional[iam.Effect], optional
            The effect of the policy statement, either ALLOW or DENY,
            by default iam.Effect.ALLOW
        conditions : Optional[dict], optional
            Conditions for the policy statement, by default None
        """
        super().__init__(scope, id, **kwargs)

        # Create the IAM policy statement
        self.statement = iam.PolicyStatement(
            actions=actions,
            resources=resources,
            effect=effect,
            conditions=conditions or {},
        )
