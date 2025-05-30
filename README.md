# Arcane Scribe

The **Arcane Scribe** is a serverless application enabling users to pose natural language questions concerning TTRPG rules. The core of this system will involve ingesting and processing TTRPG SRDs (System Reference Documents) to create a knowledge base that can be queried using natural language.

## System Flow

1. Client requests an upload URL via the `as-presigned-url-generator`
2. Client uploads a PDF document using the presigned URL
3. S3 upload event triggers the `as-pdf-ingestor`
4. Client submits a query to the `as-rag-query` endpoint
5. The query Lambda processes the question and returns an answer
6. All API endpoints are protected by the `as-authorizer` Lambda

## Lambda Functions

### 1. API Authorization (`as-authorizer`)

- **Purpose**: Secures API endpoints by validating request headers.
- **Functionality**:
  - Validates incoming reqeusts against configured authentication headers
  - Returns IAM policy documents that allow or deny access to API resources
  - Configured via environment variables for header name and expected value
    - Environment variables set using GitHub Secrets
- **Trigger**: API Gateway authorization requests

```text
📁 as-authorizer/
  ├─ handler.py        # Main Lambda handler with authorization logic
  ├─ requirements.txt  # Dependencies (AWS Lambda Powertools)
  └─ Dockerfile        # Container definition for Lambda deployment
```

### 2. PDF Ingestion (`as-pdf-ingestor`)

- **Purpose**: Processes uploaded PDF documents and transforms them into vector embeddings.
- **Functionality**:
  - Listens for S3 bucket events when new PDFs are uploaded
  - Extracts text content from PDF documents
  - Processes and chunks the text for better semantic understanding
  - Creates vector embeddings from text chunks
  - Stores the embeddings in a FAISS index for semantic search
  - Saves the index to S3 for retrieval by the query Lambda
- **Trigger**: S3 bucket events (object creation)

```text
📁 as-pdf-ingestor/
  ├─ handler.py        # Main Lambda handler processing S3 events
  ├─ requirements.txt  # Dependencies (PDF processing, vector embeddings)
  ├─ Dockerfile        # Container definition for Lambda deployment
  └─ pdf_ingestor/     # Module with processing logic
      ├─ __init__.py
      └─ processor.py  # Core PDF processing functionality
```

### 3. Presigned URL Generation (`as-presigned-url-generator`)

- **Purpose**: Generates secure URLs for uploading SRD documents to the system.
- **Functionality**:
  - Provides an API endpoint (`/src/upload-url`) for requesting upload URLs
  - Validates request payload with required `file_name` and optional `content_type`
  - Generates time-limited (15 minutes) presigned URLs for S3 uploads
  - Returns the URL, bucket name, and key information to the client
  - Handles errors and validates input parameters
- **Trigger**: API Gateway HTTP events (POST requests)

```text
📁 as-presigned-url-generator/
  ├─ handler.py                   # Main Lambda handler with API endpoint
  ├─ requirements.txt             # Dependencies (AWS Lambda Powertools, boto3)
  ├─ Dockerfile                   # Container definition for Lambda deployment
  └─ presigned_url_generator/     # Module with URL generation logic
      ├─ __init__.py
      ├─ data_classes.py          # Request validation model
      └─ processor.py             # URL generation functionality
```

### 4. RAG Query Processing (`as-rag-query`)

- **Purpose**: Handles natural language queries and retrieves relevant information.
- **Functionality**:
  - Provides an API endpoint (`/query`) for submitting questions
  - Takes query text, SRD ID, and option to use generative AI
  - Performs semantic search on vector embeddings using FAISS
  - Retrieves relevant context from the knowledge base
  - Optional passes context to an LLM (AWS Bedrock) for enhanced answers
  - Implements response caching to improve performance
  - Returns comprehensive answers based on SRD content
- **Trigger**: API Gateway HTTP events (POST requests)

```text
📁 as-rag-query/
  ├─ handler.py                # Main Lambda handler with API endpoint
  ├─ requirements.txt          # Dependencies (LangChain, FAISS, boto3)
  ├─ Dockerfile                # Container definition for Lambda deployment
  └─ rag_query_processor/      # Module with RAG functionality
      ├─ __init__.py
      └─ processor.py          # Core query processing and RAG chain logic
```
