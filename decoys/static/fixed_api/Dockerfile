FROM python:3.11-slim
WORKDIR /opt/api
RUN pip install --no-cache-dir flask
COPY app.py /opt/api/app.py
EXPOSE 80
CMD ["python", "app.py"]
