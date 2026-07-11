import requests
import os
import re

def load_local_env():
    env_dict = {}
    env_path = ".env"
    if os.path.exists(env_path):
        print("✅ 检测到本地.env文件，加载配置...")
        with open(env_path, "r", encoding="utf-8-sig") as f:
            raw_lines = f.readlines()
        for line_num, raw in enumerate(raw_lines, start=1):
            s = raw.replace("\r", "").replace("\t", "").replace("　", "").strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                print(f"⚠️ 第{line_num}行无=，跳过")
                continue
            key_raw, val_raw = s.split("=", 1)
            key = key_raw.strip()
            val = val_raw.strip()
            if not key:
                print(f"⚠️ 第{line_num}行key为空，跳过该行")
                continue
            env_dict[key] = val
            show_val = val[:20] + "..." if len(val) > 20 else val
            print(f"ℹ️ 加载 {key} = {show_val}")
    # 本地.env不存在时，读取系统环境变量兜底
    def get_env(key, default=None):
        if key in env_dict:
            return env_dict[key]
        return os.getenv(key, default)
    return get_env

# 获取读取函数（优先.env，其次系统环境）
get_env = load_local_env()

# 读取配置
CF_API_TOKEN = get_env("CF_API_TOKEN")
CF_ACCOUNT_ID = get_env("CF_ACCOUNT_ID")
CF_PROFILE_ID = get_env("CF_PROFILE_ID", "")
MODE         = get_env("MODE", "exclude")
ALLOWED_MODES = {"exclude", "include"}

# 调试打印
print("\n===== 调试变量 =====")
print(f"CF_API_TOKEN: {CF_API_TOKEN if CF_API_TOKEN else 'None'}")
print(f"CF_ACCOUNT_ID: {CF_ACCOUNT_ID if CF_ACCOUNT_ID else 'None'}")
print(f"CF_PROFILE_ID: {CF_PROFILE_ID}")
print(f"MODE: {MODE}")
print("====================\n")

# 参数校验
if not all([CF_API_TOKEN, CF_ACCOUNT_ID]):
    raise ValueError("缺少环境变量！请配置 .env 文件或在 GitHub Secrets 设置 CF_API_TOKEN、CF_ACCOUNT_ID")
if MODE not in ALLOWED_MODES:
    raise ValueError(f"非法 MODE: {MODE}，允许值：{'/'.join(sorted(ALLOWED_MODES))}")

# 解析 profile 列表
# CF_PROFILE_ID 支持逗号分隔的多个策略 ID，如 profile1,profile2,profile3
# 列表中写几个就更新几个（一个/多个/全部），留空则使用默认设备策略
TARGET_PROFILES = [p.strip() for p in CF_PROFILE_ID.split(",") if p.strip()]
if TARGET_PROFILES:
    print(f"ℹ️ 本次将更新 {len(TARGET_PROFILES)} 个策略：{TARGET_PROFILES}\n")
else:
    print("ℹ️ 未配置 CF_PROFILE_ID，使用默认设备策略\n")

HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json"
}

# ==================== 自定义参数 ====================
MAX_RULES               = 4000
TARGET_COMMON_DOMAIN_NUM = 0
# ====================================================

VALID_DOMAIN_RE = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')
CIDR_RE = re.compile(r'^[0-9a-fA-F:.]+/\d+$')
MYDOMAIN_FILE = "mydomain.txt"
DOMAIN_URL = "https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/direct.txt"
IP_URL = "https://raw.githubusercontent.com/soffchen/GeoIP2-CN/release/CN-ip-cidr.txt"

def get_myhost_content():
    mydomain_list = []
    mycidr_list = []
    if os.path.exists(MYDOMAIN_FILE):
        with open(MYDOMAIN_FILE, "r", encoding="utf-8") as f:
            for line in f.readlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if CIDR_RE.match(line):
                    mycidr_list.append(line)
                    continue
                if line.startswith("*."):
                    line = line[2:]
                line = line.lstrip(".")
                if VALID_DOMAIN_RE.match(line):
                    mydomain_list.append(f"*.{line}")
        mydomain_list = list(set(mydomain_list))
        mycidr_list = list(set(mycidr_list))
        print(f"   自定义域名(mydomain.txt)：{len(mydomain_list)} 条")
        print(f"   自定义CIDR(mydomain.txt)：{len(mycidr_list)} 条")
    else:
        print(f"   未找到 {MYDOMAIN_FILE}，跳过自定义规则")
    return mydomain_list, mycidr_list

def get_cn_cidrs():
    r = requests.get(IP_URL, timeout=30)
    r.raise_for_status()
    cidrs = [x.strip() for x in r.text.splitlines() if x.strip() and not x.startswith("#")]
    print(f"   CN IP CIDR 数据源：{len(cidrs)} 条")
    return cidrs

def get_cn_domains():
    r = requests.get(DOMAIN_URL, timeout=30)
    r.raise_for_status()
    domains = []
    for line in r.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("DOMAIN-SUFFIX,"):
            line = line.replace("DOMAIN-SUFFIX,", "").strip()
        line = line.lstrip(".")
        if VALID_DOMAIN_RE.match(line):
            domains.append(f"*.{line}")
    unique_domains = list(set(domains))
    print(f"   通用CN域名总数：{len(unique_domains)}，限制取 {TARGET_COMMON_DOMAIN_NUM} 条")
    return unique_domains

def update_split_tunnels(cidrs, common_domains, custom_domains, custom_cidrs):
    routes = []
    remain_quota = MAX_RULES

    cidr_custom = [{"address": c, "description": "Custom CIDR(mydomain.txt)"} for c in custom_cidrs[:remain_quota]]
    routes.extend(cidr_custom)
    remain_quota -= len(cidr_custom)

    domain_custom = [{"host": d, "description": "Custom Host(mydomain.txt)"} for d in custom_domains[:remain_quota]]
    routes.extend(domain_custom)
    remain_quota -= len(domain_custom)

    count_common = 0
    count_ip = 0
    if remain_quota > 0:
        take_common = min(TARGET_COMMON_DOMAIN_NUM, remain_quota, len(common_domains))
        common_entries = [{"host": d, "description": "CN Domain(Common)"} for d in common_domains[:take_common]]
        routes.extend(common_entries)
        remain_quota -= len(common_entries)
        count_common = len(common_entries)

        if remain_quota > 0:
            ip_entries = [{"address": c, "description": "CN IP"} for c in cidrs[:remain_quota]]
            routes.extend(ip_entries)
            count_ip = len(ip_entries)

    print(f"   自定义CIDR:{len(cidr_custom)} | 自定义域名:{len(domain_custom)} | 通用域名:{count_common} | CN公网IP:{count_ip} | 总规则:{len(routes)}")
    if len(routes) > MAX_RULES:
        print(f"⚠️ 规则超上限，截断至 {MAX_RULES} 条")
        routes = routes[:MAX_RULES]

    # 无指定策略时更新默认设备策略，否则逐个更新目标策略
    targets = TARGET_PROFILES if TARGET_PROFILES else [None]
    for idx, profile_id in enumerate(targets, start=1):
        if profile_id:
            api_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/devices/policy/{profile_id}/{MODE}"
            label = f"策略[{idx}/{len(targets)}] {profile_id}"
        else:
            api_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/devices/policy/{MODE}"
            label = "默认策略"

        resp = requests.put(api_url, json=routes, headers=HEADERS)
        if resp.status_code in (200, 204):
            print(f"✅ 同步完成！{label} | 共 {len(routes)} 条路由，模式：{MODE}")
        else:
            print(f"❌ API请求失败！{label} | 状态码：{resp.status_code}")
            print("返回详情：", resp.text)
            resp.raise_for_status()

if __name__ == "__main__":
    print("🔄 开始拉取CN域名与IP数据...")
    cust_dom, cust_cidr = get_myhost_content()
    cn_domains = get_cn_domains()
    cn_cidr_list = get_cn_cidrs()
    update_split_tunnels(cn_cidr_list, cn_domains, cust_dom, cust_cidr)
