"""S3 client wrapper for common S3 operations."""

# Standard Library
from typing import Dict, List, Optional, Union

# Third Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger(service="s3-client-wrapper")


class S3Client:
    """Wrapper class for AWS S3 operations using boto3.

    This class provides a simplified interface for common S3 operations
    such as uploading files, retrieving files, and listing objects.
    """

    def __init__(
        self, bucket_name: str, region_name: Optional[str] = None
    ) -> None:
        """Initialize the S3Client with a bucket name and optional region.

        Parameters
        ----------
        bucket_name : str
            The name of the S3 bucket to operate on.
        region_name : Optional[str]
            The AWS region where the S3 bucket is located. If not provided,
            the default region configured in boto3 will be used.
        """
        self.bucket_name = bucket_name
        try:
            self._client = boto3.client("s3", region_name=region_name)
        except Exception as e:
            logger.error("Failed to create S3 client: %s", e)
            raise

    def upload_file(
        self,
        file_path: str,
        object_key: str,
        bucket_name: Optional[str] = None,
        extra_args: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Upload a file to S3.

        Parameters
        ----------
        file_path : str
            The local path to the file to be uploaded.
        object_key : str
            The key (path) in the S3 bucket where the file will be stored.
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.
        extra_args : Optional[Dict[str, str]]
            Additional arguments to pass to the upload operation, such as
            ACL. Defaults to None.

        Returns
        -------
        bool
            True if the upload was successful, False otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        # Try to upload the file to S3
        try:
            self._client.upload_file(
                file_path, bucket_name, object_key, ExtraArgs=extra_args
            )
            return True
        except ClientError as e:
            logger.error(
                "Failed to upload file: %s to s3://%s/%s - Error: %s",
                file_path,
                bucket_name,
                object_key,
                e,
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error uploading file: %s to s3://%s/%s - Error: %s",
                file_path,
                bucket_name,
                object_key,
                e,
            )
            return False

    def get_file(
        self,
        object_key: str,
        download_path: str,
        bucket_name: Optional[str] = None,
    ) -> bool:
        """Download a file from S3.

        Parameters
        ----------
        object_key : str
            The key (path) in the S3 bucket of the file to be downloaded.
        download_path : str
            The local path where the file will be saved.
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        bool
            True if the download was successful, False otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        # Try to download the file from S3
        try:
            self._client.download_file(bucket_name, object_key, download_path)
            return True
        except ClientError as e:
            logger.error(
                "Failed to download file: s3://%s/%s to %s - Error: %s",
                bucket_name,
                object_key,
                download_path,
                e,
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error downloading file: s3://%s/%s to %s - Error: %s",
                bucket_name,
                object_key,
                download_path,
                e,
            )
            return False

    def get_object_content(
        self,
        object_key: str,
        bucket_name: Optional[str] = None,
    ) -> Optional[bytes]:
        """Retrieve the content of an S3 object.

        Parameters
        ----------
        object_key : str
            The key (path) in the S3 bucket of the object to retrieve.
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        Optional[bytes]
            The content of the object as bytes if it exists, None otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        # Try to get the object from S3
        try:
            response = self._client.get_object(
                Bucket=bucket_name, Key=object_key
            )
            content = response["Body"].read()
            return content
        except ClientError as e:
            logger.error(
                "Failed to get object content: s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error getting object content: s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return None

    def list_objects(
        self,
        prefix: Optional[str] = None,
        max_keys: int = 1000,
        bucket_name: Optional[str] = None,
    ) -> List[Dict[str, Union[str, int]]]:
        """List objects in an S3 bucket.

        Parameters
        ----------
        prefix : Optional[str], optional
            A prefix to filter the objects by their keys. Defaults to None.
        max_keys : int, optional
            The maximum number of objects to return. Defaults to 1000.
        bucket_name : Optional[str], optional
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        List[Dict[str, Union[str, int]]]
            A list of dictionaries containing the keys, sizes, and last
            modified timestamps of the objects in the bucket. If no objects are
            found, an empty list is returned.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        try:
            # Validate max_keys
            kwargs = {"Bucket": bucket_name, "MaxKeys": max_keys}
            if prefix:
                kwargs["Prefix"] = prefix

            # List objects in the bucket
            response = self._client.list_objects_v2(**kwargs)

            # Check if the response contains any objects
            if "Contents" not in response:
                logger.info(
                    "No objects found in bucket: %s with prefix: %s",
                    bucket_name,
                    prefix or "None",
                )
                return []

            # Return a list of dictionaries with object details
            result = [
                {
                    "Key": obj["Key"],
                    "Size": obj["Size"],
                    "LastModified": obj["LastModified"].isoformat(),
                }
                for obj in response["Contents"]
            ]
            return result
        except ClientError as e:
            logger.error(
                "Failed to list objects in bucket: %s with prefix: %s - Error: %s",
                bucket_name,
                prefix or "None",
                e,
            )
            return []
        except Exception as e:
            logger.error(
                "Unexpected error listing objects in bucket: %s with prefix: %s - Error: %s",
                bucket_name,
                prefix or "None",
                e,
            )
            return []

    def delete_object(
        self, object_key: str, bucket_name: Optional[str] = None
    ) -> bool:
        """Delete an object from S3.

        Parameters
        ----------
        object_key : str
            The key (path) in the S3 bucket of the object to delete.
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        bool
            True if the deletion was successful, False otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        # Try to delete the object from S3
        try:
            self._client.delete_object(Bucket=bucket_name, Key=object_key)
            return True
        except ClientError as e:
            logger.error(
                "Failed to delete object: s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error deleting object: s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return False

    def object_exists(
        self, object_key: str, bucket_name: Optional[str] = None
    ) -> bool:
        """Check if an object exists in S3.

        Parameters
        ----------
        object_key : str
            The key (path) in the S3 bucket of the object to check.
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        bool
            True if the object exists, False otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        # Try to head the object to check if it exists
        try:
            self._client.head_object(Bucket=bucket_name, Key=object_key)
            return True
        except ClientError as e:
            # Check if it's a 404 (not found) error
            if e.response.get("Error", {}).get("Code") == "404":
                logger.debug(
                    "Object does not exist: s3://%s/%s",
                    bucket_name,
                    object_key,
                )
            else:
                logger.error(
                    "Error checking if object exists: s3://%s/%s - Error: %s",
                    bucket_name,
                    object_key,
                    e,
                )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error checking if object exists: s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return False

    def generate_presigned_upload_url(
        self,
        object_key: str,
        expiration: int = 3600,
        bucket_name: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a presigned URL for uploading a file to S3.

        Parameters
        ----------
        object_key : str
            The key (path) in the S3 bucket where the file will be uploaded.
        expiration : int, optional
            The time in seconds for which the presigned URL is valid.
            Defaults to 3600 (15 minutes).
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        Optional[str]
            The presigned URL if generation was successful, None otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        try:
            # Prepare parameters for presigned URL generation
            params = {"Bucket": bucket_name, "Key": object_key}

            # Generate the presigned URL
            presigned_url = self._client.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expiration
            )
            return presigned_url
        except ClientError as e:
            logger.error(
                "Failed to generate presigned upload URL for s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error generating presigned upload URL for s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return None

    def generate_presigned_download_url(
        self,
        object_key: str,
        expiration: int = 3600,
        bucket_name: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a presigned URL for downloading a file from S3.

        Parameters
        ----------
        object_key : str
            The key (path) in the S3 bucket of the file to be downloaded.
        expiration : int, optional
            The time in seconds for which the presigned URL is valid.
            Defaults to 3600 (15 minutes).
        bucket_name : Optional[str]
            The name of the S3 bucket. If not provided, the bucket_name
            specified during initialization will be used.

        Returns
        -------
        Optional[str]
            The presigned URL if generation was successful, None otherwise.
        """
        # Use the provided bucket name or the one from initialization
        if bucket_name is None:
            bucket_name = self.bucket_name

        try:
            # Generate the presigned URL for downloading
            presigned_url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": object_key},
                ExpiresIn=expiration,
            )
            return presigned_url
        except ClientError as e:
            logger.error(
                "Failed to generate presigned download URL for s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error generating presigned download URL for s3://%s/%s - Error: %s",
                bucket_name,
                object_key,
                e,
            )
            return None
