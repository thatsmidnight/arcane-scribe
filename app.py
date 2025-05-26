#!/usr/bin/env python3
# Standard Library
import os

# Third-Party
import aws_cdk as cdk

# Local Folder
from cdk.stacks import ArcaneScribeStack

app = cdk.App()

# Standard AWS environment variables for CDK
aws_env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

# Determine stack suffix from context variable (passed by CI/CD or default to 'Dev')
# This allows for unique stack names per feature branch
stack_suffix = app.node.try_get_context("stack-suffix") or ""
stack_name_prefix = "ArcaneScribeStack"

if stack_suffix != "main":
    final_stack_name = f"{stack_name_prefix}-{stack_suffix}"
else:
    # Fallback for local development or main branch if no suffix is provided
    # Consider a more explicit way to differentiate main vs. feature if needed
    stack_suffix = ""
    final_stack_name = f"{stack_name_prefix}-Main"


ArcaneScribeStack(
    app, final_stack_name, stack_suffix=stack_suffix, env=aws_env
)

app.synth()
