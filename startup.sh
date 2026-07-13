#!/bin/bash
# Install system dependencies in background, start gunicorn immediately
(
  apt-get update -qq
  apt-get install -y -qq libmagic1

  if ! dpkg -l msodbcsql18 &> /dev/null; then
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
    curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list
    apt-get update -qq
    ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 unixodbc-dev
  fi
) &

# Start gunicorn immediately
gunicorn --config gunicorn.conf.py wsgi:app
