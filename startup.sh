#!/bin/bash
# App Service outbound internet is firewalled (confirmed: forced through
# udr-jeef01-np-euw-dv-subnet-to-fw with no PyPI/packages.microsoft.com
# access), so apt-get/curl at runtime silently fail here. The ODBC driver
# is pre-installed and bundled into the deployment zip by GitHub Actions
# instead (see .github/workflows/main_accio-dev.yml) — this script just
# copies those already-downloaded files into place. No network calls.
set -e

if [ -d "/home/site/wwwroot/driver_files" ]; then
  echo "Staging bundled ODBC driver files..."
  mkdir -p /home/msodbc/etc
  cp -r /home/site/wwwroot/driver_files/opt /home/msodbc/ 2>/dev/null || true
  cp -r /home/site/wwwroot/driver_files/usr /home/msodbc/ 2>/dev/null || true
  cp /home/site/wwwroot/driver_files/etc/odbcinst.ini /home/msodbc/etc/odbcinst.ini

  # Point unixODBC at our bundled odbcinst.ini instead of /etc (App Service
  # doesn't let us write to /etc as non-root, so we redirect via env var).
  export ODBCSYSINI=/home/msodbc/etc
  export LD_LIBRARY_PATH="/home/msodbc/opt/microsoft/msodbcsql18/lib64:/home/msodbc/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}"
  echo "ODBCSYSINI set to $ODBCSYSINI"
  echo "Driver registered: $(cat $ODBCSYSINI/odbcinst.ini | grep -A1 '\[ODBC Driver 18 for SQL Server\]' || echo 'NOT FOUND — check driver_files staging')"
else
  echo "WARNING: driver_files/ not found in deployment package — Azure SQL connections via pyodbc will fail."
  echo "Check the 'Install and stage msodbcsql18 driver' step in the GitHub Actions workflow."
fi

# Start gunicorn
gunicorn --config gunicorn.conf.py wsgi:app
