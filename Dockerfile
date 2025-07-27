FROM python:3.12.5

WORKDIR /code

# 复制依赖文件
COPY ./requirements.txt /code/requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制应用代码
COPY ./app /code/app

# 复制脚本目录
COPY ./scripts /code/scripts

# 复制 WARP 配置文件目录（如果存在）
COPY ./warp-configs /code/warp-configs

# 设置启动脚本执行权限
RUN chmod +x /code/scripts/start.sh

# Railway 启动
ENTRYPOINT ["/bin/sh", "-c", "/code/scripts/start.sh"]
