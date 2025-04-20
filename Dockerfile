# Use the official Python image as the base
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Copy the application code to the container
COPY . /app

# Install dependencies
RUN pip install --upgrade pip
RUN pip install flask flask-sqlalchemy flask-login

# Expose the port the app runs on
EXPOSE 5000

# Define the default command to run the app
CMD ["python", "app.py"]
