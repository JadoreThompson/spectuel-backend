#!/bin/bash

set -e

echo "Creating alembic.ini"
cp alembic.ini.template alembic.ini
cd src 

cat <<EOF > tmp.py
from utils.db import write_db_url_alembic
write_db_url_alembic()
EOF

uv run tmp.py
rm tmp.py
cd ..
echo "Successfully wrote db url to alembic"

echo "Applying migrations"
uv run alembic upgrade head
