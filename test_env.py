# test_env.py
import os

def test_load_env():
    print("读取.env测试")
    with open(".env", "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
    for idx, l in enumerate(lines):
        raw = repr(l)
        clean = l.strip().replace("\t","").replace("　","")
        print(f"第{idx+1}行 原始:{raw} 清洗后:{clean}")
        if "=" in clean:
            k,v = clean.split("=",1)
            print(f"  -> key='{k.strip()}' val='{v.strip()}'")

test_load_env()
