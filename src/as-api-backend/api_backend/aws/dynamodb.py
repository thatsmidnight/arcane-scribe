"""DynamoDB wrapper class for common table operations."""

# Standard Library
from typing import Any, Dict, Optional

# Third Party
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger(service="dynamodb-client-wrapper")


class DynamoDb:
    """A wrapper class for DynamoDB table operations using boto3.

    This class provides a simplified interface for common DynamoDB operations
    such as putting, getting, updating, and deleting items with comprehensive
    logging for developer and QA diagnostics.
    """

    def __init__(self, table_name: str) -> None:
        """Initialize the DynamoDb instance with a table name.

        Parameters
        ----------
        table_name : str
            The name of the DynamoDB table to operate on.
        """
        # Store table name for use in all operations and logging
        self.table_name = table_name

        try:
            # Create DynamoDB resource using boto3 with default region/credentials
            self._dynamodb = boto3.resource("dynamodb")
            # Get reference to the specific table for all operations
            self._table = self._dynamodb.Table(table_name)
        except Exception as e:
            # Log initialization failure and propagate exception
            logger.error(
                "Failed to create DynamoDB client for table %s: %s",
                table_name,
                e,
            )
            raise

    def put_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Put an item into the DynamoDB table.

        Parameters
        ----------
        item : Dict[str, Any]
            The item to put into the table. Must be a dictionary where keys are
            attribute names and values are attribute values.

        Returns
        -------
        Dict[str, Any]
            The response from the DynamoDB service after putting the item.

        Raises
        ------
        ClientError
            If there is an error while putting the item into the table.
        """
        try:
            # Execute put_item operation on DynamoDB table
            response = self._table.put_item(Item=item)
            # Return the full response from DynamoDB for caller processing
            return response
        except ClientError as e:
            # Log AWS service error with detailed message
            logger.error(
                "Failed to put item in table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            # Re-raise original ClientError for proper error handling
            raise
        except Exception as e:
            # Log unexpected errors that aren't AWS-specific
            logger.error(
                "Unexpected error putting item in table %s: %s",
                self.table_name,
                str(e),
            )
            raise

    def get_item(self, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get an item from the DynamoDB table by its key.

        Parameters
        ----------
        key : Dict[str, Any]
            The key of the item to retrieve. Must be a dictionary where keys
            are attribute names and values are attribute values that match the
            table's key schema.

        Returns
        -------
        Optional[Dict[str, Any]]
            The item retrieved from the table, or None if the item does not
            exist.

        Raises
        ------
        ClientError
            If there is an error while getting the item from the table.
        """
        try:
            # Execute get_item operation using the provided key
            response = self._table.get_item(Key=key)
            # Extract item from response (None if not found)
            item = response.get("Item")
            return item
        except ClientError as e:
            # Log AWS service error with context about the operation
            logger.error(
                "Failed to get item from table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            raise
        except Exception as e:
            # Handle any unexpected errors during retrieval
            logger.error(
                "Unexpected error getting item from table %s: %s",
                self.table_name,
                str(e),
            )
            raise

    def update_item(
        self,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_values: Optional[Dict[str, Any]] = None,
        expression_attribute_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Update an item in the DynamoDB table.

        Parameters
        ----------
        key : Dict[str, Any]
            The key of the item to update. Must be a dictionary where keys are
            attribute names and values are attribute values that match the
            table's key schema.
        update_expression : str
            The update expression that specifies the attributes to be updated.
            This should be a valid DynamoDB update expression.
        expression_attribute_values : Optional[Dict[str, Any]], optional
            A dictionary of values to be used in the update expression, by
            default None.
        expression_attribute_names : Optional[Dict[str, str]], optional
            A dictionary of attribute names to be used in the update
            expression, by default None.

        Returns
        -------
        Dict[str, Any]
            The response from the DynamoDB service after updating the item.

        Raises
        ------
        ClientError
            If there is an error while updating the item in the table.
        """
        try:
            # Build base update parameters with required fields
            update_params = {
                "Key": key,
                "UpdateExpression": update_expression,
                "ReturnValues": "ALL_NEW",
            }

            # Add optional expression attribute values if provided
            if expression_attribute_values:
                update_params["ExpressionAttributeValues"] = (
                    expression_attribute_values
                )

            # Add optional expression attribute names if provided
            if expression_attribute_names:
                update_params["ExpressionAttributeNames"] = (
                    expression_attribute_names
                )

            # Execute update operation with constructed parameters
            response = self._table.update_item(**update_params)
            return response
        except ClientError as e:
            # Log AWS service error with update context
            logger.error(
                "Failed to update item in table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            raise
        except Exception as e:
            # Handle unexpected errors during update operation
            logger.error(
                "Unexpected error updating item in table %s: %s",
                self.table_name,
                str(e),
            )
            raise

    def delete_item(self, key: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an item from the DynamoDB table.

        Parameters
        ----------
        key : Dict[str, Any]
            The key of the item to delete. Must be a dictionary where keys are
            attribute names and values are attribute values that match the
            table's key schema.

        Returns
        -------
        Dict[str, Any]
            The response from the DynamoDB service after deleting the item.

        Raises
        ------
        ClientError
            If there is an error while deleting the item from the table.
        """
        try:
            # Execute delete operation using the provided key
            response = self._table.delete_item(Key=key)
            return response
        except ClientError as e:
            # Log AWS service error with deletion context
            logger.error(
                "Failed to delete item from table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            raise
        except Exception as e:
            # Handle unexpected errors during deletion
            logger.error(
                "Unexpected error deleting item from table %s: %s",
                self.table_name,
                str(e),
            )
            raise

    def scan(
        self,
        filter_expression: Optional[Any] = None,
        projection_expression: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Scan the DynamoDB table to retrieve all items.

        Parameters
        ----------
        filter_expression : Optional[Any], optional
            An optional filter expression to apply to the scan results.
        projection_expression : Optional[str], optional
            An optional projection expression to specify which attributes to return.

        Returns
        -------
        Dict[str, Any]
            The response from the DynamoDB service after scanning the table.

        Raises
        ------
        ClientError
            If there is an error while scanning the table.
        """
        try:
            # Build scan parameters starting with empty dictionary
            scan_params = {}

            # Add optional filter expression to limit returned items
            if filter_expression is not None:
                scan_params["FilterExpression"] = filter_expression

            # Add optional projection expression to limit returned attributes
            if projection_expression:
                scan_params["ProjectionExpression"] = projection_expression

            # Execute scan operation with constructed parameters
            response = self._table.scan(**scan_params)
            return response
        except ClientError as e:
            # Log AWS service error with scan context
            logger.error(
                "Failed to scan table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            raise
        except Exception as e:
            # Handle unexpected errors during scan operation
            logger.error(
                "Unexpected error scanning table %s: %s",
                self.table_name,
                str(e),
            )
            raise

    def query(
        self,
        key_condition_expression: Any,
        filter_expression: Optional[Any] = None,
        projection_expression: Optional[str] = None,
        limit: Optional[int] = None,
        exclusive_start_key: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Query the DynamoDB table using a key condition expression.

        Parameters
        ----------
        key_condition_expression : Any
            The key condition expression to use for the query. This should be a
            valid DynamoDB key condition expression, typically using the Key
            class from `boto3.dynamodb.conditions`.
        filter_expression : Optional[Any], optional
            An optional filter expression to apply after the query, by default
            None. This can be used to further filter the results based on
            non-key attributes.
        projection_expression : Optional[str], optional
            An optional projection expression to specify which attributes to
            return in the query results, by default None. This can be used to
            limit the attributes returned for each item.
        limit : Optional[int], optional
            An optional limit on the number of items to return in the query
            results, by default None. This can be used to paginate results.
        exclusive_start_key : Optional[Dict[str, Any]], optional
            An optional key to start the query from, for pagination purposes,
            by default None. This allows continuation of a previous query
            operation.

        Returns
        -------
        Dict[str, Any]
            The response from the DynamoDB service after querying the table.
            This will include the items that match the key condition expression
            and any applied filter expression.

        Raises
        ------
        ClientError
            If there is an error while querying the table.
        """
        try:
            # Build query parameters with required key condition
            query_params = {"KeyConditionExpression": key_condition_expression}

            # Add optional exclusive start key for pagination
            if exclusive_start_key:
                query_params["ExclusiveStartKey"] = exclusive_start_key

            # Add optional filter expression for additional filtering
            if filter_expression is not None:
                query_params["FilterExpression"] = filter_expression

            # Add optional projection expression to limit returned attributes
            if projection_expression:
                query_params["ProjectionExpression"] = projection_expression

            # Add optional limit to control number of items returned
            if limit is not None:
                query_params["Limit"] = limit

            # Execute query operation with constructed parameters
            response = self._table.query(**query_params)
            return response
        except ClientError as e:
            # Log AWS service error with query context
            logger.error(
                "Failed to query table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            raise
        except Exception as e:
            # Handle unexpected errors during query operation
            logger.error(
                "Unexpected error querying table %s: %s",
                self.table_name,
                str(e),
            )
            raise

    def batch_write(self, items: list[Dict[str, Any]]) -> Dict[str, Any]:
        """Batch write items to the DynamoDB table.

        Parameters
        ----------
        items : list[Dict[str, Any]]
            A list of items to write to the table. Each item must be a
            dictionary where keys are attribute names and values are attribute
            values.

        Returns
        -------
        Dict[str, Any]
            The response from the DynamoDB service after the batch write
            operation. This will include any unprocessed items if the batch
            write was not fully successful.

        Raises
        ------
        ClientError
            If there is an error while performing the batch write operation.
        """
        try:
            # Use batch writer context manager for efficient batch operations
            with self._table.batch_writer() as batch:
                # Iterate through items and add each to the batch
                for item in items:
                    batch.put_item(Item=item)
            # Return success response indicating no unprocessed items
            return {"UnprocessedItems": {}}
        except ClientError as e:
            # Log AWS service error with batch write context
            logger.error(
                "Failed to batch write to table %s: %s",
                self.table_name,
                e.response.get("Error", {}).get("Message", str(e)),
            )
            raise
        except Exception as e:
            # Handle unexpected errors during batch write operation
            logger.error(
                "Unexpected error during batch write to table %s: %s",
                self.table_name,
                str(e),
            )
            raise
