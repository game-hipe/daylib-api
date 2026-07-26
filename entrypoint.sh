#!/bin/sh

echo "Running migrations..."
alembic upgrade head

echo "Starting application..."
exec python main.py
