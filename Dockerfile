# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY src/ /app/src/

# The default command to run when the container starts.
# This will be overridden by docker-compose or kubernetes.
# We set a default entrypoint that can run any of our scripts.
ENTRYPOINT ["python3"]
