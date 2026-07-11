# cf-zt-cn-split

自动同步中国大陆 IP 段与直连域名到 Cloudflare Zero Trust 分流隧道（Split Tunnels），实现 CN 流量直连、其余流量走 WARP 的网络分流策略。

-----

## 功能简介

- 自动拉取最新中国大陆 IP 数据（来源：[soffchen/GeoIP2-CN](https://github.com/soffchen/GeoIP2-CN) 全运营商聚合版）
- 通过 `mydomain.txt` 统一管理自定义直连域名与 IP/CIDR（含内网保留网段）
- 自定义规则优先加载，CN 公网 IP 段兜底填满剩余配额，在 4000 条限额内最大化分流准确性
- 通过 Cloudflare Zero Trust API 更新设备策略的 Split Tunnels 规则
- 支持一次更新多个设备策略（`CF_PROFILE_ID` 逗号分隔，写几个更新几个）
- 支持 `exclude`（CN 直连）和 `include`（仅 CN 走 WARP）两种模式
- 通过 GitHub Actions 定时自动运行，无需手动维护

-----

## 工作原理

```text
   mydomain.txt (自定义域名 + IP/CIDR)      soffchen/GeoIP2-CN (CN-ip-cidr.txt)
        ↓ 自定义 CIDR + 自定义直连域名               ↓ 全运营商聚合 CIDR（兜底填满剩余配额）
                        ↓ 自定义规则在前 ↓
                      cf-zt-cn-split.py
                        ↓ Cloudflare Zero Trust API（PUT）
              设备策略 Split Tunnels 规则（exclude / include）
                        ↓
      自定义域名 DNS 层直连 + 自定义/CN IP 网络层兜底，其余走 WARP
```

### 分流优先级逻辑

```text
用户访问 mydomain.txt 收录的域名（如 *.baidu.com）
  → 命中自定义域名规则 → DNS + 流量均走直连通道 ✅

用户访问未收录域名，但解析到 mydomain.txt 或 CN 数据源中的 IP
  → 域名规则未命中 → IP/CIDR 规则兜底命中 → 直连 ✅

用户访问未收录域名，IP 也未收录
  → 两层均未命中 → 走 WARP ⚠️（概率极低，可接受）
```

-----

## 前置要求

- Cloudflare Zero Trust 账户（免费版即可）
- 已在设备上部署 Cloudflare WARP 客户端
- Cloudflare API Token（需具备 Zero Trust 写权限）

-----

## 快速开始

### 1. Fork 本仓库

点击右上角 **Fork** 按钮，将仓库复制到你的 GitHub 账户。

### 2. 配置 GitHub Secrets

进入仓库 **Settings → Secrets and variables → Actions**，添加以下 Secrets：

|Secret 名称      |说明                                                        |是否必填|
|---------------|----------------------------------------------------------|----|
|`CF_API_TOKEN` |Cloudflare API Token，需具备 Zero Trust 写权限                   |✅必填  |
|`CF_ACCOUNT_ID`|Cloudflare 账户 ID，可在控制台右侧边栏找到                              |✅必填  |
|`CF_PROFILE_ID`|设备策略 ID，支持逗号分隔多个（如 `id1,id2,id3`），留空则使用默认策略        |❌可选  |
|`MODE`         |分流模式：`exclude`（CN 直连）或 `include`（仅 CN 走 WARP），默认 `exclude`|❌可选  |

#### 如何获取 API Token

1. 前往 [Cloudflare Dashboard → API Tokens](https://dash.cloudflare.com/profile/api-tokens)
1. 点击 **Create Token**
1. 选择 **Edit Cloudflare Zero Trust** 模板，或手动添加 `Zero Trust: Edit` 权限
1. 复制生成的 Token

### 3. 启用 GitHub Actions

进入仓库 **Actions** 标签页，启用 Workflow。默认每周日自动运行一次，也可手动触发。

-----

## 配置说明

### 分流模式（MODE）

|模式           |行为                                   |
|-------------|-------------------------------------|
|`exclude`（默认）|自定义规则与 CN IP 加入排除列表，对应流量**不走** WARP，直连出口|
|`include`    |自定义规则与 CN IP 加入包含列表，**只有**这些流量走 WARP   |

大多数用户选择 `exclude` 模式：境外流量走 WARP，国内流量直连，兼顾速度与访问需求。

### 设备策略（CF_PROFILE_ID）

`CF_PROFILE_ID` 支持逗号分隔多个策略 ID，脚本会依次更新列表中的每一个：

- **留空**：更新账户的默认设备策略
- **单个 ID**（如 `profile1`）：只更新该策略
- **多个 ID**（如 `profile1,profile2,profile3`）：按顺序逐个更新，写几个就更新几个

> 需要更新哪些策略就在列表里写哪些，顺序、数量均可自定义。运行时会打印 `本次将更新 N 个策略：[...]`，并对每个策略输出 `✅ 同步完成！策略[i/n] ...`。

-----

## 规则配额分配

Cloudflare Zero Trust Split Tunnels 单策略最多支持 **4000 条**规则，本项目按如下优先级依次填充配额：

|规则类型              |来源                                  |优先级          |
|------------------|------------------------------------|-------------|
|自定义 CIDR（`address`）|`mydomain.txt`（含内网保留网段）             |最高           |
|自定义域名（`host`）      |`mydomain.txt`                       |高（DNS 层）     |
|CN 公网 IP（`address`）|soffchen/GeoIP2-CN `CN-ip-cidr.txt`  |兜底（填满剩余配额）  |
|**合计**            |                                     |**≤ 4000 条** |

> 自定义规则优先加载，CN 公网 IP 段填满剩余配额；当规则总数超过 4000 条时脚本会自动截断。
> 通用 CN 域名数量由脚本中的 `TARGET_COMMON_DOMAIN_NUM` 控制，当前默认为 `0`（不加载），全部配额留给自定义规则与 CN IP 段。

-----

## 数据源说明

### IP 数据源

|数据源                                                                                    |实测条目数       |状态  |备注              |
|---------------------------------------------------------------------------------------|------------|----|----------------|
|[soffchen/GeoIP2-CN](https://github.com/soffchen/GeoIP2-CN) `CN-ip-cidr.txt`          |~3900 条     |当前使用|全运营商聚合，由于配额充足可完整载入|
|[gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) `china.txt`|~4397 条     |备用  |全运营商聚合，取前 3900 条      |
|[IPdeny aggregated](https://www.ipdeny.com/ipblocks/data/aggregated/cn-aggregated.zone)|~2200 条     |备用  |条目更少，可完整载入            |
|[metowolf/iplist](https://github.com/metowolf/iplist) `china.txt`                      |~1700 条     |备用  |条目最少                      |

### 域名与自定义规则

|来源                                                                                 |用途                 |状态  |备注                         |
|------------------------------------------------------------------------------------|--------------------|----|---------------------------|
|`mydomain.txt`                                                                       |自定义直连域名 + IP/CIDR |当前使用|统一在本文件中管理，含内网保留网段，脚本自动区分域名与 CIDR|
|[Loyalsoldier/surge-rules](https://github.com/Loyalsoldier/surge-rules) `direct.txt`|通用 CN 直连域名         |备用  |由 `TARGET_COMMON_DOMAIN_NUM` 控制加载条数，当前默认为 `0`（不加载）|

> `mydomain.txt` 中每行一条：以 `*.` 或域名格式书写的视为域名规则（自动补全 `*.` 前缀），符合 CIDR 格式的视为 IP 规则，`#` 开头为注释。

-----

## 本地运行

```bash
# 安装依赖
pip install requests

# 方式一：在项目根目录创建 .env 文件
CF_API_TOKEN=your_api_token
CF_ACCOUNT_ID=your_account_id
CF_PROFILE_ID=          # 留空=默认策略；多个用逗号分隔，如 id1,id2,id3
MODE=exclude

# 方式二：设置系统环境变量（.env 不存在时兜底读取）
export CF_API_TOKEN="your_api_token"
export CF_ACCOUNT_ID="your_account_id"
export CF_PROFILE_ID=""   # 留空=默认策略；多个用逗号分隔，如 id1,id2,id3
export MODE="exclude"

# 运行脚本
python cf-zt-cn-split.py
```

正常输出示例（以更新 2 个策略为例）：

```
ℹ️ 本次将更新 2 个策略：['profile1', 'profile2']
🔄 开始拉取CN域名与IP数据...
   自定义域名(mydomain.txt)：xxx 条
   自定义CIDR(mydomain.txt)：xx 条
   通用CN域名总数：xxxx，限制取 0 条
   CN IP CIDR 数据源：xxxx 条
   自定义CIDR:xx | 自定义域名:xxx | 通用域名:0 | CN公网IP:xxxx | 总规则:4000
✅ 同步完成！策略[1/2] profile1 | 共 4000 条路由，模式：exclude
✅ 同步完成！策略[2/2] profile2 | 共 4000 条路由，模式：exclude
```

-----

## GitHub Actions 定时任务

默认配置为每周日 UTC 03:00（北京时间 11:00）自动运行，也可在 Actions 页面点击 **Run workflow** 手动触发。

如需修改定时频率，编辑 `.github/workflows/sync-cn-split.yml` 中的 `cron` 表达式。

-----

## 常见问题

**Q：同步成功后 WARP 客户端需要重启吗？**  
A：不需要，Cloudflare Zero Trust 策略更新后会自动下发到已连接的 WARP 客户端。

**Q：报错 `invalid number of rules, number of rules cannot be greater than 4000`？**  
A：IP 或域名数据源条目超出上限，脚本已内置截断逻辑，正常情况下不会触发。若触发请检查数据源是否变更。

**Q：报错 `invalid exclude value` 或 `invalid domain name`？**  
A：API payload 格式错误或域名包含非法字符，请确保使用最新版本脚本（已内置正则过滤）。

**Q：报错 `404 Not Found`？**  
A：数据源 URL 失效，请检查脚本中 `IP_URL` / `DOMAIN_URL` 是否仍然可访问，并切换至备用数据源。

**Q：如何确认规则已生效？**  
A：前往 Cloudflare Zero Trust Dashboard → **Settings → WARP Client → Device settings → 对应策略 → Split Tunnels**，查看规则列表是否已更新。

**Q：如何添加自己的直连域名或 IP 段？**  
A：直接编辑根目录的 `mydomain.txt`，每行一条。域名可写为 `*.example.com` 或 `example.com`（脚本自动补全 `*.` 前缀），IP 段写为标准 CIDR 格式（如 `1.2.3.0/24`），`#` 开头为注释行。

**Q：为什么默认不加载通用 CN 域名？**  
A：脚本中的 `TARGET_COMMON_DOMAIN_NUM` 默认为 `0`，即不从 surge-rules 拉取通用域名，把全部 4000 条配额留给 `mydomain.txt` 自定义规则与 CN 公网 IP 段兜底。如需启用，可调大该值。

-----

## 许可证

MIT License
