class Config:
    DEBUG = False
    TESTING = False
    SECRET_KEY = 'your-production-secret-key'  # Use a strong secret key in production
    # Other config variables for both environments
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = 'your-development-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///development.db'

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'postgresql://user:password@localhost/production_db'
    # For example, use PostgreSQL for production
