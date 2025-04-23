import os

# PostgreSQL
POSTGRES_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:Jungkook1!@localhost:5432/cloudwatch")

# MongoDB
API_KEY = "fb23af25eda4f16a60eb16a48f7ca7e8"
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "cloudwatch")