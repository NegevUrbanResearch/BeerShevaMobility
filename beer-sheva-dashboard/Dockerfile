# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgdal-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/data/raw \
    /app/data/processed \
    /app/output/dashboard_data \
    /app/output/poi_charts

# Copy the application code
COPY . /app/

# Run preprocessing scripts
RUN python pre_preprocess_data.py && \
    python preprocess_data.py

# Make port 8050 available
EXPOSE 8050

# Run app.py when the container launches
CMD ["python", "app.py"]