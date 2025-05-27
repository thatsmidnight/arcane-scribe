# Standard Library
from typing import Optional, List

# Third-Party
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
        super().__init__(scope, id, **kwargs)

        # Create the IAM policy statement
        self.statement = iam.PolicyStatement(
            actions=actions,
            resources=resources,
            effect=effect,
            conditions=conditions or {},
        )
