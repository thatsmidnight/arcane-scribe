#!/usr/bin/env python3
# Standard Library
import os

# Third Party
import aws_cdk as cdk

# Local Modules
from cdk.stacks import ArcaneScribeStack

# Initialize the CDK application
app = cdk.App()

# Standard AWS environment variables for CDK
aws_env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

# Determine stack suffix from context variable (passed by CI/CD or default to 'Dev')
# This allows for unique stack names per feature branch
stack_suffix = app.node.try_get_context("stack-suffix")
formatted_stack_suffix = f"-{stack_suffix}" if stack_suffix else ""
stack_name_prefix = "arcane-scribe-stack"

if stack_suffix:
    final_stack_name = f"{stack_name_prefix}{formatted_stack_suffix}"
else:
    # Fallback for local development or main branch if no suffix is provided
    # Consider a more explicit way to differentiate main vs. feature if needed
    formatted_stack_suffix = ""
    final_stack_name = stack_name_prefix

# Create the stack with the final name and environment
ArcaneScribeStack(
    app, final_stack_name, stack_suffix=formatted_stack_suffix, env=aws_env
)

# Synthesize the app
app.synth()
