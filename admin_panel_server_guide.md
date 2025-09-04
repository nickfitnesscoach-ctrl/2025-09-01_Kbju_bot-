# 🚀 Server Admin Panel Setup Guide

## 📋 Prerequisites

Make sure these are installed on your server:
```bash
# Required packages
pip install flask flask-limiter aiohttp

# Or install from requirements if updated
pip install -r requirements.txt
```

## 🔧 Server Configuration

### 1. **Set Secure Password**
Create or update `.env` file on server:
```bash
# Navigate to bot directory
cd /root/bots/kbju_bot

# Edit environment file
nano .env
```

Add these lines:
```bash
# Admin Panel Security
ADMIN_PASSWORD=Your_Secure_Password_2024!
SECRET_KEY=very-long-random-secret-key-for-flask-sessions-32-chars-min

# Bot settings (if not already set)
BOT_TOKEN=your_telegram_bot_token
N8N_WEBHOOK_URL=your_webhook_url
```

### 2. **Start Admin Panel Service**

#### Option A: Direct Launch
```bash
# Start admin panel (runs on port 5000)
python admin_panel.py

# Or run in background
nohup python admin_panel.py > admin_panel.log 2>&1 &
```

#### Option B: Using PM2 (Recommended)
```bash
# Install PM2 if not installed
npm install -g pm2

# Start admin panel with PM2
pm2 start admin_panel.py --name "bot-admin" --interpreter python3

# Save PM2 configuration
pm2 save
pm2 startup
```

### 3. **Configure Firewall (if needed)**
```bash
# Allow port 5000 for admin panel
ufw allow 5000

# Or use specific IP restriction
ufw allow from YOUR_IP_ADDRESS to any port 5000
```

## 🌐 Access from Browser

### Local Access (on server)
```
http://localhost:5000
```

### Remote Access
```
http://your-server-ip:5000
```

### With Domain (if configured)
```
http://yourdomain.com:5000
```

## 🔒 Production Security Setup

### 1. **Nginx Reverse Proxy** (Recommended)
Create nginx config: `/etc/nginx/sites-available/bot-admin`
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    
    location /admin/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:
```bash
ln -s /etc/nginx/sites-available/bot-admin /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 2. **SSL Certificate** (Production)
```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Get SSL certificate
certbot --nginx -d yourdomain.com

# Access will be: https://yourdomain.com/admin/
```

### 3. **IP Restrictions** (Optional)
Add to nginx config:
```nginx
location /admin/ {
    allow YOUR_IP_ADDRESS;
    allow YOUR_OFFICE_IP_RANGE;
    deny all;
    
    proxy_pass http://127.0.0.1:5000/;
    # ... other proxy settings
}
```

## 📊 Usage Workflow

### Daily Operations:
```bash
# 1. SSH to server
ssh root@your-server

# 2. Check bot status
cd /root/bots/kbju_bot
docker-compose ps

# 3. Check admin panel status
pm2 status

# 4. If admin panel not running:
pm2 start admin_panel.py --name "bot-admin" --interpreter python3

# 5. Access admin panel in browser
# Open: http://your-server-ip:5000
```

### Text Editing Process:
1. **Open browser** → `http://your-server-ip:5000`
2. **Login** with ADMIN_PASSWORD
3. **Find text** to edit in the organized list
4. **Click "Редактировать"** 
5. **Edit text** with HTML formatting
6. **Enter password** and save
7. **Changes apply immediately** to bot!

## 🔧 Maintenance Commands

### Check Admin Panel Logs:
```bash
# PM2 logs
pm2 logs bot-admin

# Direct log file (if using nohup)
tail -f admin_panel.log
```

### Restart Admin Panel:
```bash
# PM2 restart
pm2 restart bot-admin

# Or kill and start again
pm2 delete bot-admin
pm2 start admin_panel.py --name "bot-admin" --interpreter python3
```

### Update Admin Panel:
```bash
# Pull latest code
git pull origin main

# Restart admin panel
pm2 restart bot-admin
```

## 🚨 Troubleshooting

### Port 5000 Already in Use:
```bash
# Check what's using port 5000
lsof -i :5000

# Kill process if needed
kill -9 PID_NUMBER

# Or change port in admin_panel.py:
# app.run(debug=False, host='0.0.0.0', port=5001)
```

### Admin Panel Won't Start:
```bash
# Check Python path
which python3

# Install missing packages
pip3 install flask flask-limiter

# Check file permissions
chmod +x admin_panel.py
```

### Can't Access Remotely:
```bash
# Check firewall
ufw status

# Check if service is listening
netstat -tulpn | grep :5000

# Test locally first
curl http://localhost:5000
```

## 📈 Monitoring

### Setup Monitoring (Optional):
```bash
# Add to crontab for health check
crontab -e

# Add this line (check every 5 minutes):
*/5 * * * * curl -f http://localhost:5000 > /dev/null 2>&1 || pm2 restart bot-admin
```

### Backup Texts:
```bash
# Backup current texts
cp app/texts_data.json app/texts_backup_$(date +%Y%m%d).json

# Restore from backup if needed
cp app/texts_backup_20241201.json app/texts_data.json
```

## ✅ Quick Checklist

Before using admin panel:
- [ ] `.env` file configured with secure ADMIN_PASSWORD
- [ ] Flask and dependencies installed  
- [ ] Admin panel started (PM2 or direct)
- [ ] Port 5000 accessible
- [ ] Bot still running normally
- [ ] Test login with password

## 🎯 Success!

Now you can edit all bot texts through the web interface!

**Access: `http://your-server:5000`**
**Password: Check your `.env` ADMIN_PASSWORD**

No programming needed - just convenient browser interface! 🎉