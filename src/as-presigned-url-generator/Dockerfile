# Use the official AWS Lambda Python base image for Python 3.12
FROM public.ecr.aws/lambda/python:3.12

# Set the LAMBDA_TASK_ROOT environment variable (AWS base images use this)
ENV LAMBDA_TASK_ROOT=/var/task

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# Install dependencies from requirements.txt directly into LAMBDA_TASK_ROOT
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r requirements.txt -t ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler (function_name.handler_name)
CMD [ "handler.lambda_handler" ]