# Docker 部署文件

这个目录包含了 AI Studio Proxy API 项目的所有 Docker 相关文件。

## 📁 文件说明

- **`Dockerfile`** - Docker 镜像构建文件
- **`docker-compose.yml`** - Docker Compose 配置文件
- **`.env.docker`** - Docker 环境配置模板
- **`README-Docker.md`** - 详细的 Docker 部署指南

## 🚀 快速开始

### 0. 准备认证文件 (重要)

Docker 模式仅支持运行已认证的会话。请确保项目根目录下存在 `auth_profiles` 目录，并且其中包含有效的认证文件（通常由主机直接运行程序生成）。

**目录结构示例：**

```text
项目根目录/
  ├── auth_profiles/
  │   └── active/
  │       └── account_xxx.json  <-- 必需的认证文件
  └── docker/
```

### 1. 准备配置文件

```bash
cd docker
cp .env.docker .env
nano .env  # 编辑配置文件
```

### 2. 启动服务

```bash
# 构建并启动服务
docker compose up -d

# 查看日志
docker compose logs -f
```

### 3. 版本更新

```bash
# 在 docker 目录下
bash update.sh
```

## 📖 详细文档

完整的 Docker 部署指南请参见：[README-Docker.md](README-Docker.md)

## 🔧 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 进入容器
docker compose exec ai-studio-proxy /bin/bash
```

## 🌟 主要优势

- ✅ **统一配置**: 使用 `.env` 文件管理所有配置
- ✅ **版本更新无忧**: `bash update.sh` 即可完成更新
- ✅ **环境隔离**: 容器化部署，避免环境冲突
- ✅ **配置持久化**: 认证文件和日志持久化存储

## ⚠️ 注意事项

1. **认证文件**: 必须在主机上预先获取认证文件并放入 `auth_profiles/active/` 目录。
2. **端口配置**: 默认占用主机端口 `2048` (API) 和 `3120` (Stream)。如需修改，请编辑 `.env` 文件中的 `HOST_FASTAPI_PORT` 和 `HOST_STREAM_PORT`。
3. **配置文件**: `.env` 文件必须位于 `docker/` 目录下，以便 Docker Compose 正确加载。
4. **脚本注入**: 如需使用脚本注入功能，请参考 [README-Docker.md](README-Docker.md) 中的详细配置说明。
