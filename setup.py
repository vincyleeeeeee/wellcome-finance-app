#!/usr/bin/env python3
"""Setup script: initialize database and import existing clients."""

import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(__file__))
from utils.database import init_db, create_user, upsert_client, get_clients

# ============================================================
# 1. Initialize DB tables
# ============================================================
print("📦 初始化数据库...")
init_db()
print("   ✅ 数据表已创建")

# ============================================================
# 2. Create admin (if not exists)
# ============================================================
print("\n👤 创建管理员账号...")
print("   请输入管理员信息（第一个用户自动成为管理员）：")

email = input("   邮箱: ").strip()
username = input("   用户名: ").strip()
password = input("   密码: ").strip()

success, msg = create_user(email, username, password)
print(f"   {'✅' if success else '❌'} {msg}")

# ============================================================
# 3. Import existing clients from markdown profile
# ============================================================
print("\n📋 导入现有客户档案...")
import_md = input("   是否从 cc-客户信息 导入现有客户？(y/n): ").strip().lower()

if import_md == 'y':
    profile_path = "/Users/vincy/Documents/Wellcome/项目/cc-客户信息/客户基础信息.md"
    if not os.path.exists(profile_path):
        print(f"   ❌ 文件不存在: {profile_path}")
    else:
        count = _import_from_markdown(profile_path)
        print(f"   ✅ 已导入 {count} 个客户")

# ============================================================
# 4. Verify
# ============================================================
print("\n" + "=" * 50)
print("📊 当前状态：")
clients = get_clients()
print(f"   客户数: {len(clients)}")
for c in clients:
    print(f"   - {c['short_name']}: {c['full_name']}")

print(f"\n🎉 初始化完成！运行命令启动应用：")
print(f"   cd {os.path.dirname(__file__)}")
print(f"   streamlit run app.py")


def _import_from_markdown(path: str) -> int:
    """Parse the markdown client profile and import clients."""
    import re
    with open(path, 'r') as f:
        content = f.read()

    # Split by ## sections (each client)
    sections = re.split(r'\n## ', content)
    count = 0

    for section in sections[1:]:  # Skip header
        lines = section.strip().split('\n')
        data = {}
        for line in lines:
            # Match "- **字段**：值"
            m = re.match(r'- \*\*(.+?)\*\*[：:]\s*(.+)', line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                # Skip "待补充" values
                if val == '（待补充）':
                    val = ''
                data[key] = val

        short_name = data.get('简称', '')
        full_name = data.get('公司全称', '')
        address = data.get('公司地址', '')
        contact = data.get('提交人/联系人', '')
        phone = data.get('电话', '')
        email = data.get('邮箱', '')

        if short_name and full_name:
            success, _ = upsert_client(short_name, full_name, address, contact, phone, email, 1)
            if success:
                count += 1

    return count


if __name__ == '__main__':
    _import_from_markdown
