# Django Certificate System - Deployment Guide

## 🚀 Production Deployment Guide

This guide will help you deploy your Django Certificate System to production.

### 📋 Prerequisites

- Domain name (recommended)
- SSL certificate (for HTTPS)
- PostgreSQL database (for production)
- Email service (Gmail recommended)
- Server or hosting platform

### 🗂️ Project Structure

```
certificate_system/
├── certificate_project/          # Django project
├── certificates/                  # Django app
├── static/                        # Static files
├── media/                         # User uploads
├── templates/                     # HTML templates
├── requirements.txt               # Python dependencies
├── .env.production               # Production environment variables
├── settings_production.py        # Production settings
├── docker-compose.yml            # Docker configuration
├── Dockerfile                     # Docker image
├── nginx.conf                    # Nginx configuration
├── vercel.json                   # Vercel deployment
├── app.json                      # Heroku deployment
└── deploy.sh                     # Deployment script
```

### 🔧 Environment Configuration

1. **Copy and configure environment variables:**
```bash
cp .env.production .env
```

2. **Update the following variables in `.env`:**
```bash
# Generate new secret key
SECRET_KEY=your-new-secret-key-here

# Your domain
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
SITE_DOMAIN=yourdomain.com

# Database configuration
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# Email configuration
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

3. **Generate Django secret key:**
```bash
python manage.py generate_secret_key
```

### 🌐 Deployment Options

#### Option 1: Docker Deployment (Recommended)

1. **Install Docker and Docker Compose**

2. **Build and run:**
```bash
docker-compose up -d --build
```

3. **Run migrations:**
```bash
docker-compose exec web python manage.py migrate --settings=certificate_project.settings_production
```

4. **Create superuser:**
```bash
docker-compose exec web python manage.py createsuperuser --settings=certificate_project.settings_production
```

5. **Collect static files:**
```bash
docker-compose exec web python manage.py collectstatic --noinput --settings=certificate_project.settings_production
```

#### Option 2: Heroku Deployment

1. **Install Heroku CLI**

2. **Create Heroku app:**
```bash
heroku create your-app-name
```

3. **Set environment variables:**
```bash
heroku config:set DJANGO_SETTINGS_MODULE=certificate_project.settings_production
heroku config:set SECRET_KEY=your-secret-key
heroku config:set ALLOWED_HOSTS=your-app-name.herokuapp.com
heroku config:set SITE_DOMAIN=your-app-name.herokuapp.com
```

4. **Add PostgreSQL:**
```bash
heroku addons:create heroku-postgresql:hobby-dev
```

5. **Deploy:**
```bash
git push heroku main
```

6. **Run migrations:**
```bash
heroku run python manage.py migrate
```

7. **Create superuser:**
```bash
heroku run python manage.py createsuperuser
```

#### Option 3: PythonAnywhere

1. **Sign up at [pythonanywhere.com](https://www.pythonanywhere.com)**

2. **Create a new Web app**

3. **Choose Django framework and Python 3.11**

4. **Upload your project files**

5. **Configure virtual environment:**
```bash
pip install -r requirements.txt
```

6. **Set environment variables in the Web tab**

7. **Configure database (they provide PostgreSQL)**

8. **Run migrations:**
```bash
python manage.py migrate --settings=certificate_project.settings_production
```

9. **Collect static files:**
```bash
python manage.py collectstatic --noinput --settings=certificate_project.settings_production
```

#### Option 4: VPS Deployment

1. **Install dependencies:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv postgresql nginx
```

2. **Clone your project**

3. **Set up virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4. **Configure PostgreSQL database**

5. **Configure Nginx (use provided nginx.conf)**

6. **Set up systemd service**

7. **Configure SSL with Let's Encrypt:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

### 📧 Email Configuration

1. **Enable 2-factor authentication on your Gmail account**

2. **Generate an App Password:**
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password

3. **Use the app password in EMAIL_HOST_PASSWORD**

### 🔒 Security Settings

The production settings include:
- HTTPS enforcement
- Security headers
- CSRF protection
- XSS protection
- Content type protection

### 📁 File Uploads

- **Static files**: Collected to `staticfiles/`
- **Media files**: Stored in `media/`
- **Certificates**: Generated in `media/certificates/`
- **Templates**: Stored in `media/templates/`

### 🔄 Backup Strategy

1. **Database backup:**
```bash
pg_dump your_db_name > backup.sql
```

2. **Media files backup:**
```bash
tar -czf media_backup.tar.gz media/
```

3. **Automate backups with cron jobs**

### 📊 Monitoring

1. **Check application logs:**
```bash
docker-compose logs web
```

2. **Monitor database performance**

3. **Set up error tracking (Sentry recommended)**

### 🚀 Deployment Script

Use the provided `deploy.sh` script for automated deployment:
```bash
chmod +x deploy.sh
./deploy.sh
```

### 🐛 Troubleshooting

**Common Issues:**

1. **Static files not loading:**
   - Run `collectstatic` command
   - Check STATIC_URL and STATIC_ROOT settings

2. **Database connection errors:**
   - Verify database credentials
   - Check if database server is running

3. **Email not sending:**
   - Verify email credentials
   - Check if app password is correct

4. **Permission errors:**
   - Check file permissions for media directory
   - Ensure web server has write access

### 📞 Support

For deployment issues:
1. Check logs for error messages
2. Verify environment variables
3. Ensure all dependencies are installed
4. Check database connectivity

---

**Your Django Certificate System is now production-ready! 🎉**
