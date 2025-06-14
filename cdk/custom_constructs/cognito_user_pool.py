# Standard Library
from typing import Optional, Dict, Union, Any

# Third Party
from aws_cdk import aws_cognito as cognito, RemovalPolicy
from constructs import Construct


class CustomCognitoUserPool(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        stack_suffix: Optional[str] = "",
        self_sign_up_enabled: Optional[bool] = False,
        sign_in_aliases: Optional[
            Union[cognito.SignInAliases, Dict[str, Any]]
        ] = None,
        auto_verify: Optional[
            Union[cognito.AutoVerifiedAttrs, Dict[str, Any]]
        ] = None,
        standard_attributes: Optional[
            Union[cognito.StandardAttributes, Dict[str, Any]]
        ] = None,
        password_policy: Optional[
            Union[cognito.PasswordPolicy, Dict[str, Any]]
        ] = None,
        account_recovery: Optional[cognito.AccountRecovery] = None,
        removal_policy: Optional[RemovalPolicy] = None,
    ) -> None:
        super().__init__(scope, id)

        # Append stack suffix to name if provided
        self.stack_suffix = stack_suffix or ""
        name = f"{name}{self.stack_suffix}"

        # Create the Cognito User Pool
        self.user_pool = cognito.UserPool(
            self,
            "DefaultUserPool",
            user_pool_name=name,
            self_sign_up_enabled=self_sign_up_enabled,
            sign_in_aliases=sign_in_aliases,
            auto_verify=auto_verify,
            standard_attributes=standard_attributes,
            password_policy=password_policy,
            account_recovery=(
                account_recovery or cognito.AccountRecovery.EMAIL_ONLY
            ),
            removal_policy=removal_policy or RemovalPolicy.DESTROY,
        )

    def add_client(
        self,
        id: str,
        name: str,
        admin_user_password_auth: Optional[bool] = True,
        user_srp_auth: Optional[bool] = True,
        generate_secret: Optional[bool] = False,
    ) -> cognito.UserPoolClient:
        """
        Add a client to the Cognito User Pool.
        """
        return self.user_pool.add_client(
            id=f"{id}{self.stack_suffix}",
            user_pool_client_name=f"{name}{self.stack_suffix}",
            auth_flows=cognito.AuthFlow(
                admin_user_password=admin_user_password_auth,
                user_srp=user_srp_auth,
            ),
            generate_secret=generate_secret,
        )
