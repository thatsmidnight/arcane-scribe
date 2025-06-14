# Use the official AWS Lambda Python base image for Python 3.12
FROM public.ecr.aws/lambda/python:3.12

# Set the root directory for the Lambda function, also the working directory
ENV LAMBDA_TASK_ROOT=/var/task
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt .
# Install dependencies into the LAMBDA_TASK_ROOT
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -t .

# Copy the main handler file
COPY handler.py .

# Copy the additional files needed for the Lambda function
COPY ./api_authorizer ./api_authorizer/

# Set the CMD to your handler function within handler.py
CMD [ "handler.lambda_handler" ]