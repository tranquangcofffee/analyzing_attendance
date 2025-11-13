# 1. Chọn base image có sẵn Python
FROM python:3.11-slim

# 2. Set working directory trong container
WORKDIR /app

# 3. Copy file requirements.txt (danh sách thư viện)
COPY requirements.txt .

# 4. Cài các thư viện Python
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy toàn bộ project vào container
COPY . .

# 6. Expose port mà Flask sẽ chạy
EXPOSE 5000

# 7. Command để chạy Flask app
CMD ["python", "app.py"]
