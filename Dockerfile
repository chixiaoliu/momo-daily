# 给 Hugging Face Spaces 用的镜像（免费、不需要信用卡）
FROM python:3.12-slim

WORKDIR /app
COPY . /app

ENV MOMO_PUBLIC=1 \
    MOMO_CORS=* \
    PYTHONUNBUFFERED=1 \
    PORT=7860

EXPOSE 7860

CMD ["python", "prototype/server.py", "--port", "7860", "--no-browser", "--host", "0.0.0.0"]
