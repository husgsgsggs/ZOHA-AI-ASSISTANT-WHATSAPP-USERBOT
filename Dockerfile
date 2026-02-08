# Use a Python base image that supports the latest Selenium
FROM python:3.10-slim

# Step 1: Install Chromium and the essential Linux drivers
# These specific libraries prevent the 'browser crashed' error in Docker
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 2: Set Environment Variables for Selenium
# This ensures your main.py knows exactly where to find the browser
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Step 3: Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: Copy all project files
COPY . .

# Step 5: Ensure your assets folder for the profile pic is ready
RUN mkdir -p assets

# Step 6: Expose Port 8000 for Sevalla
EXPOSE 8000

# Step 7: Start the bot
CMD ["python", "main.py"]
