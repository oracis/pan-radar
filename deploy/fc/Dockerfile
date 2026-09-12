# PanRadar 函数计算（FC）自定义容器镜像
# 零依赖 Python 应用，基础镜像即含 Python 3.12
FROM python:3.12-slim

WORKDIR /code

# 只拷贝运行必需文件（测试脚本 / 部署脚本不进镜像）
COPY panradar.py ./
COPY config.json ./
COPY web/ ./web/

# FC 的 /code 只读，SQLite 缓存落到可写目录 /tmp（冷启动会清空，见 README）
ENV PANRADAR_DATA_DIR=/tmp/panradar
ENV PYTHONUNBUFFERED=1

EXPOSE 9000

# FC 自定义容器：前台监听 9000，FC 会把外部请求转发到该端口
CMD ["python", "panradar.py", "--host", "0.0.0.0", "--port", "9000", "--no-browser"]
