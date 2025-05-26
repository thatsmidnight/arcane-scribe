FROM public.ecr.aws/lambda/python:3.12
COPY pyproject.toml ./
COPY poetry.lock ./
RUN pip install poetry
RUN poetry install --directory=/asset-output
COPY src/./ # Assuming Lambda code is in src/
# If specific files need to be in the root of the zip
# COPY src/lambda_function.py /asset-output/ 
# For other files, ensure they are copied to /asset-output which CDK will zip

# This is not strictly used by CDK, but good practice
CMD ["lambda_function.handler"]