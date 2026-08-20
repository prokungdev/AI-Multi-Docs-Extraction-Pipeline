import os
import json
import uuid
import sqlite3
from datetime import datetime
from loguru import logger
from .connection import get_db_connection, get_db_session
from .models import DocumentSource, ApiCredential, MerchantMaster

def get_domains(settings_path: str = "configs/settings.json") -> list[dict]:
    """
    Returns list of domains from configs/settings.json.
    """
    if not os.path.exists(settings_path):
        logger.warning(f"Settings configuration file not found at: {settings_path}")
        return []
    try:
        from src.core.config_loader import load_system_settings
        settings = load_system_settings(settings_path)
        domains = settings.get("domains", [])
        formatted_domains = []
        for d in domains:
            formatted_domains.append({
                "domain_id": d.get("domain_id"),
                "display_name": d.get("display_name"),
                "is_active": 1 if d.get("is_active", True) else 0,
                "sort_order": d.get("sort_order", 0)
            })
        formatted_domains.sort(key=lambda x: x["sort_order"])
        return formatted_domains
    except Exception as e:
        logger.error(f"Failed to load domains from settings.json: {e}")
        return []

def get_sources(domain_id: str) -> list[dict]:
    """
    Returns list of sources for a domain from database using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            sources = session.query(DocumentSource).filter(DocumentSource.domain_id == domain_id).all()
            return [
                {
                    "source_id": s.source_id,
                    "domain_id": s.domain_id,
                    "display_name": s.display_name,
                    "is_active": s.is_active
                }
                for s in sources
            ]
    except Exception as e:
        logger.error(f"Failed to load sources for domain '{domain_id}': {e}")
        return []

def update_domain_active_status(domain_id: str, is_active: int, settings_path: str = "configs/settings.json") -> bool:
    """
    Toggles is_active for a domain inside configs/settings.json and clears the settings cache.
    """
    if not os.path.exists(settings_path):
        logger.error(f"Settings configuration file not found at: {settings_path}")
        return False
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
            
        domains = settings.get("domains", [])
        updated = False
        for d in domains:
            if d.get("domain_id") == domain_id:
                d["is_active"] = True if is_active == 1 else False
                updated = True
                break
                
        if updated:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            # Invalidate in-memory LRU cache so subsequent reads get fresh data
            try:
                from src.core.config_loader import load_system_settings
                load_system_settings.cache_clear()
            except Exception:
                pass
            logger.info(f"Updated domain '{domain_id}' active status to {is_active == 1} in {settings_path}")
            return True
        else:
            logger.warning(f"Domain '{domain_id}' not found in {settings_path}")
            return False
    except Exception as e:
        logger.error(f"Failed to update domain active status in {settings_path}: {e}")
        return False

def update_source_active_status(source_id: str, is_active: int) -> bool:
    """
    Toggles is_active for a source.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE document_sources SET is_active = ? WHERE source_id = ?", (is_active, source_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to toggle source active status: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_active_credentials(provider: str, model_name: str) -> list[dict]:
    """
    Retrieves all active API credentials for a specific provider and model using SQLAlchemy ORM.
    Sorted by last_active_at DESC (last working key first).
    """
    try:
        with get_db_session() as session:
            creds = session.query(ApiCredential).filter(
                ApiCredential.provider == provider,
                ApiCredential.model_name == model_name,
                ApiCredential.is_active == 1
            ).order_by(ApiCredential.last_active_at.desc(), ApiCredential.credential_id.asc()).all()

            return [
                {
                    "credential_id": c.credential_id,
                    "provider": c.provider,
                    "model_name": c.model_name,
                    "api_key_env": c.api_key_env,
                    "is_active": c.is_active,
                    "last_active_at": c.last_active_at,
                    "error_count": c.error_count
                }
                for c in creds
            ]
    except Exception as e:
        logger.error(f"Failed to get active credentials: {e}")
        return []

def update_credential_status(credential_id: str, last_active_at: str = None, error_count: int = None, is_active: int = None) -> bool:
    """
    Updates status, error_count, and last_active_at timestamp for a credential.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if last_active_at is not None:
            updates.append("last_active_at = ?")
            params.append(last_active_at)
        if error_count is not None:
            updates.append("error_count = ?")
            params.append(error_count)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(is_active)
            
        if not updates:
            return True
            
        params.append(credential_id)
        query = f"UPDATE api_credentials SET {', '.join(updates)} WHERE credential_id = ?"
        
        cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update credential status: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_merchants(conn: sqlite3.Connection = None) -> list[dict]:
    """
    Retrieves all merchants from merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchant_master ORDER BY merchant_name ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to get merchants: {e}")
        return []
    finally:
        if should_close and conn:
            conn.close()

def upsert_merchant(merchant_id: str, tax_id: str, merchant_name: str,
                    default_wht_rate: float = 0.0, is_vat_registered: int = 1,
                    conn: sqlite3.Connection = None) -> bool:
    """
    Inserts or updates a merchant record in merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        
        # Check by merchant_id first
        cursor.execute("SELECT merchant_id FROM merchant_master WHERE merchant_id = ?", (merchant_id,))
        exists_by_id = cursor.fetchone()
        
        # Check by tax_id
        exists_by_tax = None
        if tax_id and tax_id.strip():
            cursor.execute("SELECT merchant_id FROM merchant_master WHERE tax_id = ?", (tax_id.strip(),))
            exists_by_tax = cursor.fetchone()
            
        if exists_by_id:
            cursor.execute("""
                UPDATE merchant_master
                SET tax_id = ?, merchant_name = ?, default_wht_rate = ?, is_vat_registered = ?, updated_at = ?
                WHERE merchant_id = ?
            """, (tax_id, merchant_name, default_wht_rate, is_vat_registered, now_str, merchant_id))
        elif exists_by_tax:
            cursor.execute("""
                UPDATE merchant_master
                SET merchant_name = ?, default_wht_rate = ?, is_vat_registered = ?, updated_at = ?
                WHERE tax_id = ?
            """, (merchant_name, default_wht_rate, is_vat_registered, now_str, tax_id))
        else:
            cursor.execute("""
                INSERT INTO merchant_master (merchant_id, tax_id, merchant_name, default_wht_rate, is_vat_registered, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (merchant_id, tax_id, merchant_name, default_wht_rate, is_vat_registered, now_str))
            
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert merchant: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def match_merchant(tax_id: str, name: str, conn: sqlite3.Connection = None) -> str | None:
    """
    Matches a merchant from merchant_master by tax_id first, then by merchant_name.
    Returns merchant_id if matched, otherwise None.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        # 1. Match by Tax ID (exact match)
        if tax_id and tax_id.strip():
            cursor.execute("SELECT merchant_id FROM merchant_master WHERE tax_id = ?", (tax_id.strip(),))
            row = cursor.fetchone()
            if row:
                return row["merchant_id"]
        # 2. Match by Merchant Name (exact case-insensitive match)
        if name and name.strip():
            cursor.execute("SELECT merchant_id FROM merchant_master WHERE LOWER(merchant_name) = ?", (name.strip().lower(),))
            row = cursor.fetchone()
            if row:
                return row["merchant_id"]
    except Exception as e:
        logger.error(f"Error matching merchant: {e}")
    finally:
        if should_close and conn:
            conn.close()
    return None

def delete_merchant(merchant_id: str, conn: sqlite3.Connection = None) -> bool:
    """
    Deletes a merchant record from merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM merchant_master WHERE merchant_id = ?", (merchant_id,))
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete merchant: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()

def insert_relational_receipt(document_id: str, payload: dict, original_filename: str, conn: sqlite3.Connection = None) -> bool:
    """
    Parses extracted JSON payload and inserts header and items into relational tables.
    Also auto-registers new merchants in merchant_master.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        
        # 1. Extract merchant & receipt information with fallbacks
        merchant_obj = payload.get("merchant", {})
        receipt_info = payload.get("receipt_info", {})
        totals_obj = payload.get("totals", {}) or payload.get("financial_summary", {})

        merchant_name = merchant_obj.get("name") or payload.get("merchant_name")
        tax_id = merchant_obj.get("tax_id") or payload.get("tax_id")
        
        if not merchant_name:
            merchant_name = "Unknown Merchant"
        if tax_id:
            tax_id = tax_id.strip()
            
        # 2. Match merchant in merchant_master
        merchant_id = match_merchant(tax_id, merchant_name, conn=conn)
        if not merchant_id:
            merchant_id = f"mer_{uuid.uuid4().hex[:12]}"
            upsert_merchant(
                merchant_id=merchant_id,
                tax_id=tax_id,
                merchant_name=merchant_name,
                default_wht_rate=0.0,
                is_vat_registered=1,
                conn=conn
            )
            
        # 3. Clean up any existing receipt for this document_id (updates/re-runs)
        cursor.execute("SELECT receipt_id FROM expense_receipt WHERE document_id = ?", (document_id,))
        existing_receipt = cursor.fetchone()
        if existing_receipt:
            receipt_id = existing_receipt["receipt_id"]
            cursor.execute("DELETE FROM expense_receipt_d WHERE receipt_id = ?", (receipt_id,))
            cursor.execute("DELETE FROM expense_receipt WHERE receipt_id = ?", (receipt_id,))
        else:
            receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
            
        # 4. Save Header
        subtotal = totals_obj.get("subtotal", 0.0)
        discount = totals_obj.get("discount", 0.0)
        vat_amount = totals_obj.get("vat_amount", 0.0)
        net_amount = totals_obj.get("net_amount", 0.0)
        
        transaction_date = receipt_info.get("transaction_date") or payload.get("transaction_date")
        expense_category = receipt_info.get("expense_category") or payload.get("expense_category")
        payment_method = receipt_info.get("payment_method") or payload.get("payment_method")

        cursor.execute("""
            INSERT INTO expense_receipt (
                receipt_id, document_id, merchant_id, transaction_date, merchant_name, tax_id,
                expense_category, subtotal, discount, vat_amount, net_amount, payment_method,
                source_file_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            receipt_id, document_id, merchant_id, transaction_date,
            merchant_name, tax_id, expense_category, subtotal,
            discount, vat_amount, net_amount, payment_method,
            original_filename, now_str
        ))
        
        # 5. Save Details (concatenated line items)
        for item in payload.get("items", []):
            item_id = f"itm_{uuid.uuid4().hex[:12]}"
            item_name = item.get("name")
            if not item_name:
                continue
            qty = item.get("qty", 1)
            unit_price = item.get("unit_price", 0.0)
            total_price = item.get("total_price", 0.0)
            
            cursor.execute("""
                INSERT INTO expense_receipt_d (item_id, receipt_id, item_name, qty, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (item_id, receipt_id, item_name, qty, unit_price, total_price))
            
        if should_close:
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to insert relational receipt for doc '{document_id}': {e}")
        if should_close and conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if should_close and conn:
            conn.close()
