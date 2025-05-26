# Use the official AWS Lambda Python base image for Python 3.12
FROM public.ecr.aws/lambda/python:3.12

ENV LAMBDA_TASK_ROOT=/var/task

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
# If you have other utility files/modules in this directory, copy them as well
# COPY ./my_utils ${LAMBDA_TASK_ROOT}/my_utils

# Install dependencies from requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r requirements.txt -t ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "handler.lambda_handler" ]