FROM python:3.12.5

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
COPY ./scripts/start.sh /code/start.sh

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

# 复制 WARP 配置文件目录（如果存在）
COPY ./warp-configs /code/warp-configs

# 确保start.sh有执行权限
RUN chmod +x /code/start.sh

# 使用 sh -c 方式执行，Railway 100% 兼容
ENTRYPOINT ["/bin/sh", "-c", "/code/start.sh"]
