import requests
import os
import re

CF_API_TOKEN = os.getenv("CF_API_TOKEN")
ACCOUNT_ID   = os.getenv("CF_ACCOUNT_ID")
PROFILE_ID   = os.getenv("CF_PROFILE_ID", "")
MODE         = os.getenv("MODE", "exclude")  # exclude=CN直连 | include=只有CN走WARP
ALLOWED_MODES = {"exclude", "include"}

if not all([CF_API_TOKEN, ACCOUNT_ID]):
    raise ValueError("缺少环境变量！请在 GitHub Secrets 设置 CF_API_TOKEN、CF_ACCOUNT_ID")

if MODE not in ALLOWED_MODES:
    raise ValueError(f"非法 MODE: {MODE}，只允许 {'/'.join(sorted(ALLOWED_MODES))}")

HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json"
}

# ==================== 可自定义参数 ====================
MAX_RULES               = 4000
TARGET_COMMON_DOMAIN_NUM = 200  # 自行设置通用surge直连域名最多取多少条
# ======================================================

VALID_DOMAIN_RE = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')

# 数据源地址
DOMAIN_URL = "https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/direct.txt"
IP_URL = "https://raw.githubusercontent.com/soffchen/GeoIP2-CN/release/CN-ip-cidr.txt"
MYDOMAIN_FILE = "mydomain.txt"


def get_myhost_domains():
    """读取本地 mydomain.txt 自定义域名，兼容 *.xxx.com 格式，第一优先级"""
    mydomain_list = []
    if os.path.exists(MYDOMAIN_FILE):
        with open(MYDOMAIN_FILE, "r", encoding="utf-8") as f:
            for line in f.readlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 去除行首 *. 兼容用户填写泛域名格式
                if line.startswith("*."):
                    line = line[2:]
                # 去除前导点
                line = line.lstrip(".")
                if VALID_DOMAIN_RE.match(line):
                    mydomain_list.append(f"*.{line}")
        mydomain_list = list(set(mydomain_list))
        print(f"   自定义域名(mydomain.txt)获取到 {len(mydomain_list)} 条")
    else:
        print(f"   未找到 {MYDOMAIN_FILE}，跳过自定义域名")
    return mydomain_list


def get_cn_cidrs():
    """从GeoIP2-CN 拉取聚合的 CN CIDR 列表"""
    r = requests.get(IP_URL, timeout=30)
    r.raise_for_status()
    cidrs = [line.strip() for line in r.text.splitlines() if line.strip() and not line.startswith('#')]
    print(f"   IP 数据源获取到 {len(cidrs)} 条 CIDR")
    return cidrs


def get_cn_domains():
    """从 Loyalsoldier/surge-rules 拉取精选 CN 直连域名列表，过滤非法格式"""
    r = requests.get(DOMAIN_URL, timeout=30)
    r.raise_for_status()
    domains = []
    for line in r.text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # 兼容 DOMAIN-SUFFIX,xxx 格式
        if line.startswith('DOMAIN-SUFFIX,'):
            line = line.replace('DOMAIN-SUFFIX,', '').strip()
        # 去掉前导点（如 .baidu.com → baidu.com）
        line = line.lstrip('.')
        # 只保留合法域名格式，过滤脏数据
        if line and VALID_DOMAIN_RE.match(line):
            domains.append(f"*.{line}")
    unique = list(set(domains))
    print(f"   通用直连域名数据源总条数: {len(unique)} 条，限制最多取 {TARGET_COMMON_DOMAIN_NUM} 条")
    return unique


def update_split_tunnels(cidrs, common_domains, custom_domains):
    routes = []
    remain_quota = MAX_RULES

    # 1. 第一优先级：自定义 mydomain 域名
    custom_entries = [{"host": d, "description": "Custom Host(mydomain.txt)"} for d in custom_domains[:remain_quota]]
    routes.extend(custom_entries)
    remain_quota -= len(custom_entries)
    final_custom = len(custom_entries)

    final_common = 0
    final_ip = 0

    if remain_quota > 0:
        # 2. 第二优先级：通用直连域名，最多取 TARGET_COMMON_DOMAIN_NUM 条
        take_common = min(TARGET_COMMON_DOMAIN_NUM, remain_quota, len(common_domains))
        common_entries = [{"host": d, "description": "CN Domain(Common)"} for d in common_domains[:take_common]]
        routes.extend(common_entries)
        remain_quota -= len(common_entries)
        final_common = len(common_entries)

        if remain_quota > 0:
            # 3. 第三优先级：CN IP CIDR，剩余配额全部填充IP
            ip_entries = [{"address": cidr, "description": "CN IP"} for cidr in cidrs[:remain_quota]]
            routes.extend(ip_entries)
            final_ip = len(ip_entries)

    print(f"   自定义域名规则：{final_custom} 条 | 通用域名规则：{final_common} 条 | IP 规则：{final_ip} 条 | 合计：{len(routes)} 条")

    if len(routes) > MAX_RULES:
        print(f"⚠️  规则总数超出限制，已截断至 {MAX_RULES} 条")
        routes = routes[:MAX_RULES]

    if PROFILE_ID:
        url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/devices/policy/{PROFILE_ID}/{MODE}"
    else:
        url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/devices/policy/{MODE}"

    resp = requests.put(url, json=routes, headers=HEADERS)
    if resp.status_code in (200, 204):
        print(f"✅ 同步成功！{len(routes)} 条路由 | Mode: {MODE}")
    else:
        print(f"❌ 失败 {resp.status_code}: Cloudflare API 请求未成功")
        print("API 返回详情:", resp.text)
        resp.raise_for_status()


if __name__ == "__main__":
    print("🔄 拉取最新 CN geo 数据...")
    # 按优先级顺序加载三类数据
    custom_hosts = get_myhost_domains()
    common_domains = get_cn_domains()
    cidr_list = get_cn_cidrs()
    update_split_tunnels(cidr_list, common_domains, custom_hosts)
