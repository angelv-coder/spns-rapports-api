FROM python:3.12-slim

WORKDIR /app

COPY . /app

ENV SPNS_HOST=0.0.0.0
ENV SPNS_PORT=10000

EXPOSE 10000

CMD ["python", "server.py"]
