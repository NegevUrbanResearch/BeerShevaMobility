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

# Copy the current directory contents into the container at /app
COPY . /app

# Create data directory and copy data files
RUN mkdir -p /app/data
COPY data/* /app/data/

# Create necessary directories
RUN mkdir -p /app/output/dashboard_data

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Run preprocessing script
RUN python preprocess_data.py

# Make port 8050 available to the world outside this container
EXPOSE 8050

# Define environment variable
ENV NAME World

# Run app.py when the container launches
CMD ["python", "app.py"]
