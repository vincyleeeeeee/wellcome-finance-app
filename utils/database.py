"""Database module — Supabase (PostgreSQL) backend."""

import os
import hashlib
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from supabase import create_client

_supabase = None


def _get_config():
    """Lazy-init: get Supabase config when first needed."""
    # Try Streamlit secrets first (only works after st is loaded)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            url = st.secrets.get('SUPABASE_URL', '') or ''
            key = st.secrets.get('SUPABASE_KEY', '') or ''
            if url and key:
                return url, key
    except Exception:
        pass
    # Fall back to env vars
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")


def _get_sb():
    global _supabase
    if _supabase is None:
        url, key = _get_config()
        if not url:
            raise RuntimeError(
                "Supabase 未配置。请在 Streamlit Cloud → Settings → Secrets 添加 "
                "SUPABASE_URL 和 SUPABASE_KEY。"
            )
        _supabase = create_client(url, key)
    return _supabase


def init_db():
    """Tables already created via Supabase SQL Editor. No-op for compatibility."""
    pass


# ============================================================
# Password helpers
# ============================================================
def _hash_password(password: str) -> str:
    return hashlib.sha256((password + "wellcome_salt_2026").encode()).hexdigest()


# ============================================================
# User operations
# ============================================================
def create_user(email: str, username: str, password: str) -> Tuple[bool, str]:
    sb = _get_sb()
    try:
        existing = sb.table("users").select("id").eq("email", email).execute()
        if existing.data:
            return False, "该邮箱已被注册"

        count_resp = sb.table("users").select("id", count="exact").execute()
        is_first = count_resp.count == 0

        sb.table("users").insert({
            "email": email,
            "username": username,
            "password_hash": _hash_password(password),
            "role": "admin" if is_first else "user",
            "approved": is_first,
        }).execute()
        if is_first:
            return True, "管理员注册成功！请登录"
        return True, "注册成功！请等待管理员审核"
    except Exception as e:
        return False, f"注册失败：{e}"


def authenticate(email: str, password: str) -> Optional[Dict]:
    sb = _get_sb()
    try:
        result = sb.table("users").select("*").eq("email", email).eq(
            "password_hash", _hash_password(password)
        ).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def is_approved(user_id: int) -> bool:
    sb = _get_sb()
    try:
        result = sb.table("users").select("approved").eq("id", user_id).execute()
        return result.data[0]["approved"] if result.data else False
    except Exception:
        return False


def get_pending_users() -> List[Dict]:
    sb = _get_sb()
    result = sb.table("users").select("*").eq("approved", False).neq("role", "admin").order("created_at", desc=True).execute()
    return result.data or []


def approve_user(user_id: int) -> bool:
    sb = _get_sb()
    sb.table("users").update({"approved": True}).eq("id", user_id).execute()
    return True


def reject_user(user_id: int) -> bool:
    sb = _get_sb()
    sb.table("users").delete().eq("id", user_id).neq("role", "admin").execute()
    return True


def get_all_users() -> List[Dict]:
    sb = _get_sb()
    result = sb.table("users").select("*").order("created_at", desc=True).execute()
    return result.data or []


def get_connection():
    """For session restore compatibility."""
    return _get_sb()


# ============================================================
# Client operations
# ============================================================
def get_clients() -> List[Dict]:
    sb = _get_sb()
    result = sb.table("clients").select("*").order("short_name").execute()
    return result.data or []


def get_client_by_short_name(short_name: str) -> Optional[Dict]:
    sb = _get_sb()
    result = sb.table("clients").select("*").eq("short_name", short_name).execute()
    return result.data[0] if result.data else None


def get_client_by_id(client_id: int) -> Optional[Dict]:
    sb = _get_sb()
    result = sb.table("clients").select("*").eq("id", client_id).execute()
    return result.data[0] if result.data else None


def upsert_client(short_name: str, full_name: str, address: str,
                  contact: str, phone: str, email: str, created_by: int) -> Tuple[bool, str]:
    sb = _get_sb()
    try:
        existing = sb.table("clients").select("id").eq("short_name", short_name).execute()
        if existing.data:
            sb.table("clients").update({
                "full_name": full_name, "address": address,
                "contact": contact, "phone": phone, "email": email,
                "updated_at": "now()"
            }).eq("short_name", short_name).execute()
            return True, f"已更新客户「{short_name}」"
        else:
            sb.table("clients").insert({
                "short_name": short_name, "full_name": full_name,
                "address": address, "contact": contact,
                "phone": phone, "email": email, "created_by": created_by
            }).execute()
            return True, f"已新增客户「{short_name}」"
    except Exception as e:
        return False, f"操作失败：{e}"


def delete_client(short_name: str) -> Tuple[bool, str]:
    sb = _get_sb()
    try:
        sb.table("clients").delete().eq("short_name", short_name).execute()
        return True, f"已删除客户「{short_name}」"
    except Exception as e:
        return False, f"删除失败：{e}"


# ============================================================
# Project operations
# ============================================================
def save_project(project_data: dict) -> int:
    sb = _get_sb()
    result = sb.table("projects").insert({
        "project_code": project_data["project_code"],
        "project_name": project_data["project_name"],
        "client_id": project_data["client_id"],
        "brand_name": project_data["brand_name"],
        "amount": project_data["amount"],
        "currency": project_data.get("currency", "USD"),
        "venue": project_data["venue"],
        "execution_period": project_data["execution_period"],
        "shooting_date": project_data["shooting_date"],
        "total_posts": project_data["total_posts"],
        "invoice_date": str(project_data["invoice_date"])[:10],
        "due_date": str(project_data["due_date"])[:10],
        "content_type": project_data.get("content_type", "UGC铺量"),
        "platform": project_data.get("platform", "小红书"),
        "status": project_data.get("status", "draft"),
        "estimated_cost": project_data.get("estimated_cost", 0),
        "cost_currency": project_data.get("cost_currency", "USD"),
        "cost_breakdown": project_data.get("cost_breakdown", ""),
        "feishu_approved": project_data.get("feishu_approved", False),
        "expected_payment_date": project_data.get("expected_payment_date"),
        "created_by": project_data["created_by"],
    }).execute()
    return result.data[0]["id"] if result.data else 0


def get_projects(limit: int = 50, status: str = None) -> List[Dict]:
    sb = _get_sb()
    query = sb.table("projects").select("*, clients(short_name, full_name)").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    data = result.data or []
    for p in data:
        if p.get("clients"):
            p["client_short"] = p["clients"]["short_name"] if isinstance(p["clients"], dict) else ""
            p["client_full"] = p["clients"]["full_name"] if isinstance(p["clients"], dict) else ""
    return data


def get_project_by_id(project_id: int) -> Dict:
    sb = _get_sb()
    result = sb.table("projects").select("*, clients(short_name, full_name)").eq("id", project_id).execute()
    if result.data:
        p = result.data[0]
        if p.get("clients"):
            p["client_short"] = p["clients"]["short_name"] if isinstance(p["clients"], dict) else ""
            p["client_full"] = p["clients"]["full_name"] if isinstance(p["clients"], dict) else ""
        return p
    return None


# ============================================================
# Approval operations
# ============================================================
def submit_for_approval(project_id: int) -> bool:
    sb = _get_sb()
    sb.table("projects").update({"status": "pending"}).eq("id", project_id).execute()
    return True


def approve_project(project_id: int, finance_user_id: int, pdf_path: str) -> bool:
    sb = _get_sb()
    sb.table("projects").update({
        "status": "approved",
        "approved_by": finance_user_id,
        "approved_at": datetime.now().isoformat(),
        "stamped_pdf_path": pdf_path,
    }).eq("id", project_id).execute()
    return True


def reject_project(project_id: int, finance_user_id: int) -> bool:
    sb = _get_sb()
    sb.table("projects").update({
        "status": "rejected",
        "approved_by": finance_user_id,
        "approved_at": datetime.now().isoformat(),
    }).eq("id", project_id).execute()
    return True


def get_pending_approvals() -> List[Dict]:
    sb = _get_sb()
    result = sb.table("projects").select("*, clients(short_name, full_name), creator:created_by(username)").eq("status", "pending").order("created_at", desc=True).execute()
    data = result.data or []
    for p in data:
        if p.get("clients"):
            p["client_short"] = p["clients"]["short_name"] if isinstance(p["clients"], dict) else ""
            p["client_full"] = p["clients"]["full_name"] if isinstance(p["clients"], dict) else ""
        if p.get("creator") and isinstance(p["creator"], dict):
            p["created_by_name"] = p["creator"]["username"]
    return data


# ============================================================
# Project code generation
# ============================================================
def generate_project_code(code_date: str) -> str:
    """
    Generate next project code: WELL + YYMMDD + XX (2-digit sequence).
    code_date: 'YYYY-MM-DD' format.
    Returns: e.g., 'WELL26071501'
    """
    sb = _get_sb()
    from datetime import datetime as dt
    d = dt.strptime(code_date, "%Y-%m-%d")
    prefix = f"WELL{d.strftime('%y%m%d')}"
    result = sb.table("projects").select("id", count="exact").like("project_code", f"{prefix}%").execute()
    seq = (result.count or 0) + 1
    return f"{prefix}{seq:03d}"


def get_next_code_for_month(year: int, month: int) -> str:
    """
    Get the next available project code for a given month.
    Uses the earliest unused day+sequence combination.
    Returns: e.g., 'WELL26080101'
    """
    sb = _get_sb()
    from datetime import datetime as dt
    prefix = f"WELL{year % 100:02d}{month:02d}"
    first_day = dt(year, month, 1)
    day_prefix = first_day.strftime('%y%m%d')
    day_result = sb.table("projects").select("id", count="exact").like("project_code", f"WELL{day_prefix}%").execute()
    day_count = (day_result.count or 0)
    return f"WELL{day_prefix}{day_count + 1:03d}"


# ============================================================
# User role management
# ============================================================
def set_user_role(user_id: int, role: str) -> bool:
    sb = _get_sb()
    sb.table("users").update({"role": role}).eq("id", user_id).execute()
    return True
