# Dockerfile (production)

# This Dockerfile is for production (optional). This is designed for deployment, as it:
# - Copies all code into the image.
# - Freeze dependencies.
# - No --reload. Suitable for running in CI/CD, on servers, etc.
# - Rebuilds are expected for new releases.

# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# Copy all files (full source)
COPY api/ ./api/
COPY app/ ./app/

# Expose FastAPI port
EXPOSE 8000

# Run the API
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
