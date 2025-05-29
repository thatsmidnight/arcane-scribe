# Standard Library
from typing import Optional

# Third Party
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_certificatemanager as acm,
)
from constructs import Construct


class ApiCustomDomain(Construct):
    """Custom construct for setting up API Gateway custom domains with DNS.

    This construct handles:
    1. Looking up an existing Route53 hosted zone
    2. Creating an ACM certificate with DNS validation
    3. Creating an API Gateway custom domain
    4. Mapping the API to the custom domain
    5. Creating a Route53 A record pointing to the domain
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        base_domain_name: str,
        subdomain_part: str,
        http_api: apigwv2.IHttpApi,
        stack_suffix: Optional[str] = "",
        **kwargs,
    ) -> None:
        """Initialize the API Gateway custom domain setup.

        Parameters
        ----------
        scope : Construct
            The scope in which this construct is defined.
        id : str
            The ID of the construct.
        base_domain_name : str
            The base domain name (e.g., example.com) for the custom domain.
        subdomain_part : str
            The subdomain part to be used (e.g., api for api.example.com).
        http_api : apigwv2.IHttpApi
            The HTTP API to be mapped to the custom domain.
        stack_suffix : Optional[str], optional
            Suffix to append to the construct ID, by default ""
        """
        super().__init__(scope, id, **kwargs)

        # Store the input parameters
        self.base_domain_name = base_domain_name
        self.subdomain_part = f"{subdomain_part}{stack_suffix}"
        self.full_subdomain_name = f"{self.subdomain_part}.{base_domain_name}"
        self.http_api = http_api

        # 1. Look up existing hosted zone
        self.hosted_zone = route53.HostedZone.from_lookup(
            self,
            "HostedZone",
            domain_name=self.base_domain_name,
        )

        # 2. Create an ACM certificate for subdomain with DNS validation
        self.certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=self.full_subdomain_name,
            validation=acm.CertificateValidation.from_dns(self.hosted_zone),
        )

        # 3. Create the API Gateway Custom Domain Name resource
        self.custom_domain = apigwv2.DomainName(
            self,
            "CustomDomain",
            domain_name=self.full_subdomain_name,
            certificate=self.certificate,
        )

        # 4. Map HTTP API to this custom domain
        self._validate_and_map_api()

        # 5. Create the Route 53 Alias Record
        self.alias_record = route53.ARecord(
            self,
            "AliasRecord",
            zone=self.hosted_zone,
            record_name=self.subdomain_part,
            target=route53.RecordTarget.from_alias(
                targets.ApiGatewayv2DomainProperties(
                    regional_domain_name=self.custom_domain.regional_domain_name,
                    regional_hosted_zone_id=self.custom_domain.regional_hosted_zone_id,
                )
            ),
        )

    def _validate_and_map_api(self) -> None:
        """Validate the API has a default stage and create API mapping."""
        default_stage = self.http_api.default_stage
        if not default_stage:
            raise ValueError(
                "Default stage could not be found for API mapping. "
                "Ensure API has a default stage or specify one."
            )

        self.api_mapping = apigwv2.ApiMapping(
            self,
            "ApiMapping",
            api=self.http_api,
            domain_name=self.custom_domain,
            stage=default_stage,
        )

    @property
    def url(self) -> str:
        """Get the custom domain URL.

        Returns:
            The full URL of the custom domain with https protocol.
        """
        return f"https://{self.full_subdomain_name}"
