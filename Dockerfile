FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Python dependencies — every compiled package ships manylinux wheels
# for this Python version (psycopg[binary] bundles libpq), so no
# compiler toolchain is installed in the image.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Dev-in-Docker (docker-compose.yml) opts into the dev/test tier via
# this build arg; production images never install it.
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

# Application code
COPY . .

# Volume mountpoints must exist before the chown, or Docker creates them
# root-owned at mount time and appuser can't write uploads/static
RUN mkdir -p /app/media /app/staticfiles

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
