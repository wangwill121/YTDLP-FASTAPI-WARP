FROM python:3.12.5

WORKDIR /code

# 复制依赖文件
COPY ./requirements.txt /code/requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制应用代码
COPY ./app /code/app

# 复制脚本目录（确保在 chmod 之前复制）
COPY ./scripts /code/scripts

# 复制 WARP 配置文件目录（如果存在）
COPY ./warp-configs /code/warp-configs

# 确保脚本文件有执行权限（现在 scripts 目录已经存在）
RUN chmod +x /code/scripts/start.sh /code/scripts/verify-railway.sh

# Railway 兼容的启动方式 - 使用 sh -c 执行启动脚本
# 备选方案：如果脚本失败，可以直接用 CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT"]
ENTRYPOINT ["/bin/sh", "-c", "/code/scripts/start.sh"]
