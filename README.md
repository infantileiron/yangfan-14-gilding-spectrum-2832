# 砚光修复·金箔补样反射分解

从比色仪的六波段测量拆出补样的参考谱比例，排定复测路线。

## 业务背景

砚光文保装饰修复小组，5 名修复员和 2 名检测员，负责非文物展示件的模拟打样。

检测员把六波段反射率留在测量表里。修复员逐份对照新制打样片和旧基底，按目视综合色差安排复测。

- 同样的平均反光可能来自完全不同的波段变化。
- 没有统一的参考谱比例，多个检测员的复测理由难复现。
- 明显偏离参考域的样片容易被当成普通配比差异。

- 上游输入为比色仪导出来自参照片、独立复核片和待验补样的六波段反射率。
- 下游交付为复核员签发的补样清单发给复测台或二次试贴台，参考谱交给检测员复核。

## 算法与数据口径

**三分量非负矩阵分解（NMF）**

用 6 个波段的反射率百分数拟合 3 个非负参考谱，固定初始化和随机种子。只用参照片拟合，独立复核片计算重构误差。将参考谱按谱质心从短波到长波编号。以参考谱的 L1 范数调整系数并归一，得到各补样的相对光谱贡献比例。按单波段绝对残差的最大值与复测门槛分流；比例不等同于材料质量比。

种子文件名为 `砚光_金箔补样六波段_2026-11-25.csv`。CSV 按下表顺序提供字段，最多 5,000 行。样本编号在同一数据版本内唯一。服务用规范化行内容的 SHA-256 对导入去重并保留实际计算所用的输入版本。

| 列 | 用途 | 类型 | 范围或选项 |
|---|---|---|---|
| `sample_id` | 样片编号 | text | 见业务口径 |
| `split` | 样片分组 | text | `参照`、`复核`、`待验` |
| `surface` | 试贴基底 | text | `封闭基底`、`仿旧基底`、`过渡基底` |
| `r440` | 440 nm 反射率 % | number | 0 至 100 |
| `r500` | 500 nm 反射率 % | number | 0 至 100 |
| `r560` | 560 nm 反射率 % | number | 0 至 100 |
| `r620` | 620 nm 反射率 % | number | 0 至 100 |
| `r680` | 680 nm 反射率 % | number | 0 至 100 |
| `r740` | 740 nm 反射率 % | number | 0 至 100 |

计算参数为 **单波段复测门槛（百分点）**，取值 2.0 至 25.0，默认 7.0。在 `POST /api/runs` 的 JSON 中使用 `parameter` 字段传入。

## 一次当班交接

1. 08:40 检测员交出砚光_金箔补样六波段_2026-11-25.csv。
2. 08:55 核对 72 片参照、24 片独立复核、8 片待验补样。
3. 09:10 复核三种参考谱的波段中心。
4. 09:20 以 7.0 个反射率百分点作为单波段复测门槛。
5. 09:30 样片 YG-P02 因 560 nm 残差偏高进入全波段复测。
6. 09:40 YG-P01 随参照谱清单提交二次试贴。
7. 10:00 复核员签发当天首批补样清单。

## 快速启动

在本项目根目录执行。复制示例环境前先检查是否已有 `.env`。示例中的连接口令供本机演示，部署时为每个项目设置独立的 JWT 密钥和数据库口令。

```sh
test -e .env || cp .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
curl -fsS http://127.0.0.1:19453/healthz
```

API 使用 `http://127.0.0.1:19453`，接口定义为 `/openapi.json`。数据库端口为 `127.0.0.1:17953`。Nginx 网关、FastAPI、Python worker、MySQL 8.0 和 Redis 组成完整服务。数据库、队列缓存和 CSV 文件使用各自的命名卷。

| 演示账号 | 权限 |
|---|---|
| `analyst@demo.local` | 读取，导入 CSV，提交计算 |
| `reviewer@demo.local` | 读取，签发或暂缓交接 |
| `viewer@demo.local` | 只读，下载结果和已签发的交接单 |

演示账号共用密码 `Yangfan-demo-2026`。关闭自动初始化可设 `SEED_DEMO=false`，也可以执行上述 seed 命令手动初始化。已有数据和账号保留原有内容。

## API 流程

| 操作 | 接口 | 要点 |
|---|---|---|
| 获取 JWT | `POST /api/auth/login` | JSON 包含 `email` 和 `password`。后续请求传 `Authorization: Bearer <token>` |
| 查看数据 | `GET /api/datasets` | 返回数据版本与校验和。附加 `/{dataset_id}/csv` 下载有效 CSV 样板 |
| 导入数据 | `POST /api/datasets` | JSON 包含 `name` 与完整 CSV 字符串 `csv` |
| 创建计算 | `POST /api/runs` | JSON 包含 `dataset_id`、`label`、`parameter`，返回计算 ID |
| 取结果 | `GET /api/runs/{run_id}` | 等待 `succeeded` 或 `failed`，完成后附加 `/csv` 下载结果 |
| 查业务交接建议 | `GET /api/domain/spectrum-review/{run_id}` | 返回项目专用的工位、样本或处置摘要 |
| 签审 | `POST /api/runs/{run_id}/review` | JSON 包含 `decision`、`samples`、`note` |
| 下载交接单 | `GET /api/runs/{run_id}/handoff.csv` | 签发后可下载，包含选中样本与交接记录 |
| 查审计 | `GET /api/audit` | 最近 100 条业务变更 |

可用 Python 标准库解析登录返回的 JWT：

```sh
API=http://127.0.0.1:19453
TOKEN=$(curl -fsS "$API/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"analyst@demo.local","password":"Yangfan-demo-2026"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
curl -fsS "$API/api/datasets" -H "Authorization: Bearer $TOKEN"
```

## 开发与运行

- `backend/src/business` 实现本项目的输入、算法和业务交接，主要模块为 `algorithm.py`, `demo.py`, `factorization.py`, `profile.py`, `review.py`, `routes.py`, `spectra.py`。
- `backend/src/routes`、`controllers`、`services` 处理 HTTP、数据版本、异步执行、签审、导出和审计。
- `backend/src/models`、`schemas` 定义持久化和接口数据。角色 `analyst/reviewer/viewer`、任务状态 `queued/running/succeeded/failed`、决定 `approve/hold` 定义在 `backend/src/constants/workflow.py`，被路由、worker、请求模型和数据模型使用。
- `backend/migrations/bootstrap.py` 初始化数据库表。修改代码后可执行 `docker compose up -d --build --wait` 重新装载。
- 本地开发可以先用 Compose 单独启动 `db` 和 `redis`，再在 `backend` 中按 `requirements.txt` 安装 Python 3.11 依赖。通过 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`、`JWT_ISSUER` 和可写的 `ARTIFACTS_DIR` 配置进程，运行 `uvicorn src.main:app --port 8000` 与 `python -m src.worker`。开发机的 Redis 可使用本地实例或为容器配置临时回环端口。
- `docker compose down` 停止本项目服务并保留数据卷。需要清空模拟数据时手动执行 `docker compose down -v --remove-orphans`。
- 业务示例均为模拟数据。模型输出供交接与现场复核。项目授权沿用工作区及交付方约定。

[验收记录](../../test-artifacts/yangfan-14-gilding-spectrum/TESTING.md)
