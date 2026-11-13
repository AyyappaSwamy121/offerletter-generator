#!/bin/bash

# Production Deployment Script for Django Certificate System

echo "🚀 Starting production deployment..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please copy .env.production to .env and configure it."
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "🗄️ Running database migrations..."
python manage.py migrate --settings=certificate_project.settings_production

echo "📁 Collecting static files..."
python manage.py collectstatic --noinput --settings=certificate_project.settings_production

echo "👤 Creating superuser (optional)..."
read -p "Do you want to create a superuser? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python manage.py createsuperuser --settings=certificate_project.settings_production
fi

echo "🔍 Checking deployment health..."
python manage.py check --deploy --settings=certificate_project.settings_production

echo "✅ Deployment completed successfully!"
echo "🌐 Your application is ready at: $SITE_PROTOCOL://$SITE_DOMAIN"
echo "🔧 Admin panel: $SITE_PROTOCOL://$SITE_DOMAIN/admin/"
