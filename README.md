# cf-zt-cn-split

自动同步中国大陆 IP 段与直连域名到 Cloudflare Zero Trust 分流隧道（Split Tunnels），实现 CN 流量直连、其余流量走 WARP 的网络分流策略。

-----

## 功能简介

- 自动拉取最新中国大陆 IP 数据（来源：[gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) 全运营商聚合版）
- 自动拉取精选 CN 直连域名（来源：[Loyalsoldier/surge-rules](https://github.com/Loyalsoldier/surge-rules) `direct.txt`）
- 域名规则优先（DNS 层命中），IP 规则兜底（网络层），在 4000 条限额内最大化分流准确性
- 通过 Cloudflare Zero Trust API 更新设备策略的 Split Tunnels 规则
- 支持 `exclude`（CN 直连）和 `include`（仅 CN 走 WARP）两种模式
- 通过 GitHub Actions 定时自动运行，无需手动维护

-----

## 工作原理

```
Loyalsoldier/surge-rules (direct.txt)     gaoyifan/china-operator-ip (china.txt)
        ↓ 精选 CN 直连域名（取前 1000 条）          ↓ 全运营商聚合 CIDR（取前 3000 条）
                        ↓ 合并，域名规则在前 ↓
                      cf-zt-cn-split.py
                        ↓ Cloudflare Zero Trust API（PUT）
              设备策略 Split Tunnels 规则（exclude / include）
                        ↓
         CN 域名 DNS 层直连 + CN IP 网络层兜底，其余走 WARP
```

### 分流优先级逻辑

```
用户访问 baidu.com
  → 命中域名规则 *.baidu.com → DNS + 流量均走直连通道 ✅

用户访问未收录域名，但解析到国内 IP
  → 域名规则未命中 → IP 规则兜底命中 → 直连 ✅

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
|`CF_API_TOKEN` |Cloudflare API Token，需具备 Zero Trust 写权限                   |必填  |
|`CF_ACCOUNT_ID`|Cloudflare 账户 ID，可在控制台右侧边栏找到                              |必填  |
|`CF_PROFILE_ID`|设备策略 ID，留空则使用默认策略                                         |可选  |
|`MODE`         |分流模式：`exclude`（CN 直连）或 `include`（仅 CN 走 WARP），默认 `exclude`|可选  |

#### 如何获取 API Token

1. 前往 [Cloudflare Dashboard → API Tokens](https://dash.cloudflare.com/profile/api-tokens)
1. 点击 **Create Token**
1. 选择 **Edit Cloudflare Zero Trust** 模板，或手动添加 `Zero Trust: Edit` 权限
1. 复制生成的 Token

### 3. 启用 GitHub Actions

进入仓库 **Actions** 标签页，启用 Workflow。默认每天自动运行一次，也可手动触发。

-----

## 配置说明

### 分流模式（MODE）

|模式           |行为                                   |
|-------------|-------------------------------------|
|`exclude`（默认）|CN IP 和域名加入排除列表，CN 流量**不走** WARP，直连出口|
|`include`    |CN IP 和域名加入包含列表，**只有** CN 流量走 WARP   |

大多数用户选择 `exclude` 模式：境外流量走 WARP，国内流量直连，兼顾速度与访问需求。

### 设备策略（PROFILE_ID）

- **留空**：更新默认设备策略的 Split Tunnels 规则
- **填写策略 ID**：更新指定的自定义设备策略

-----

## 规则配额分配

Cloudflare Zero Trust Split Tunnels 单策略最多支持 **4000 条**规则，本项目按如下方式分配：

|规则类型            |条数        |数据来源                                  |优先级     |
|----------------|----------|--------------------------------------|--------|
|域名规则（`host`）    |最多 1000 条 |Loyalsoldier/surge-rules `direct.txt` |高（DNS 层）|
|IP 规则（`address`）|最多 3000 条 |gaoyifan/china-operator-ip `china.txt`|低（网络层兜底）|
|**合计**          |**4000 条**|                                      |        |


> 域名规则排列在前，确保 DNS 层优先命中；IP 规则在后作为网络层兜底。

-----

## 数据源说明

### IP 数据源

|数据源                                                                                    |实测条目数       |状态  |备注              |
|---------------------------------------------------------------------------------------|------------|----|----------------|
|[gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) `china.txt`|~4397 条     |当前使用|全运营商聚合，取前 3000 条|
|[IPdeny aggregated](https://www.ipdeny.com/ipblocks/data/aggregated/cn-aggregated.zone)|~2200 条     |备用  |条目更少，可完整载入      |
|[metowolf/iplist](https://github.com/metowolf/iplist) `china.txt`                      |~1700 条     |备用  |条目最少            |
|gaoyifan 三大运营商分列                                                                       |~8521 条（去重后）|已弃用 |未聚合，严重超出限额      |
|[17mon/china_ip_list](https://github.com/17mon/china_ip_list)                          |~7456 条     |已弃用 |超出 4000 条限额     |

### 域名数据源

|数据源                                                                                 |条目数                 |状态  |备注                         |
|------------------------------------------------------------------------------------|--------------------|----|---------------------------|
|[Loyalsoldier/surge-rules](https://github.com/Loyalsoldier/surge-rules) `direct.txt`|~118000 条（过滤后取 1000）|当前使用|人工维护，质量高，脚本过滤非法格式后取前 1000 条|

-----

## 本地运行

```bash
# 安装依赖
pip install requests

# 设置环境变量
export CF_API_TOKEN="your_api_token"
export CF_ACCOUNT_ID="your_account_id"
export CF_PROFILE_ID=""   # 留空使用默认策略
export MODE="exclude"

# 运行脚本
python cf-zt-cn-split.py
```

正常输出示例：

```
🔄 拉取最新 CN geo 数据...
   IP 数据源获取到 4397 条 CIDR
   域名数据源获取到 1183 条域名（已过滤非法格式）
   域名规则：1000 条 | IP 规则：3000 条 | 合计：4000 条
✅ 同步成功！4000 条路由 | Mode: exclude
```

-----

## GitHub Actions 定时任务

默认配置为每天 UTC 02:00（北京时间 10:00）自动运行，也可在 Actions 页面点击 **Run workflow** 手动触发。

如需修改定时频率，编辑 `.github/workflows/` 下 workflow 文件中的 `cron` 表达式。

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

**Q：为什么只取 1000 条域名而不是更多？**  
A：受限于 4000 条总配额，域名 1000 条 + IP 3000 条是在准确性与覆盖率之间的平衡点。域名规则覆盖高频访问场景，IP 规则兜底处理未收录域名，两者互补。

-----

## 许可证

MIT License