FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ATALAYA_ENV=production PORT=8100
WORKDIR /app
COPY Web/requirements.txt Web/requirements.txt
RUN pip install --no-cache-dir -r Web/requirements.txt
COPY src src
COPY Web Web
COPY artifacts artifacts
COPY data data
RUN useradd -m atalaya && chown -R atalaya /app
USER atalaya
EXPOSE 8100
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/healthz')"
CMD ["sh", "-c", "gunicorn --chdir Web --bind 0.0.0.0:${PORT} --workers 2 --timeout 60 wsgi:app"]
