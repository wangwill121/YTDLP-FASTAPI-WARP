FROM python:3.12.5

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
COPY ./scripts/start.sh /code/start.sh

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

# 确保start.sh有执行权限
RUN chmod +x /code/start.sh

CMD ["/code/start.sh"]
