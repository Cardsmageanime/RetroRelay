FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY catalog.py server.py ./
ENV RETRORELAY_HOST=0.0.0.0 RETRORELAY_PORT=8751 RETRORELAY_DB=/appdata/lobbies.sqlite3
EXPOSE 8751
CMD ["python", "server.py"]
