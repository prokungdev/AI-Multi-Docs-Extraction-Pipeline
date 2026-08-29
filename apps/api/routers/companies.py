"""Company management REST API endpoints with Dependency Injection."""

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from src.infrastructure.database import (
    get_db_session_dep,
    get_all_companies,
    get_company,
    get_company_by_code,
    create_company,
    update_company,
    delete_company,
)
from src.application.usecases.initializer import initialize_storage_directories

router = APIRouter(prefix="/companies", tags=["Companies"])


class CompanyCreateSchema(BaseModel):
    company_code: str = Field(..., description="Unique company code slug, e.g. C00001_TRD")
    company_name: str = Field(..., description="Full legal registered company name")
    short_name: Optional[str] = Field(None, description="Short brand or business name")
    tax_id: Optional[str] = Field(None, description="13-digit Thai Tax Identification Number")
    branch_code: Optional[str] = Field("00000", description="5-digit branch code, e.g. 00000")


class CompanyUpdateSchema(BaseModel):
    company_name: Optional[str] = None
    short_name: Optional[str] = None
    tax_id: Optional[str] = None
    branch_code: Optional[str] = None
    is_active: Optional[int] = None


@router.get("", summary="List all registered companies")
def list_companies(
    active_only: bool = Query(False, description="Filter active companies only"),
    db: Session = Depends(get_db_session_dep)
):
    """
    Returns list of all registered client companies.
    """
    return get_all_companies(active_only=active_only)


@router.get("/{company_id_or_code}", summary="Get company details")
def get_company_details(
    company_id_or_code: str,
    db: Session = Depends(get_db_session_dep)
):
    """
    Retrieves company details by UUID company_id or unique company_code.
    """
    comp = get_company(company_id_or_code)
    if not comp:
        comp = get_company_by_code(company_id_or_code)
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")
    return comp


@router.post("", summary="Create a new client company", status_code=201)
def create_new_company(
    payload: CompanyCreateSchema,
    db: Session = Depends(get_db_session_dep)
):
    """
    Registers a new company in the database and provisions its storage directories.
    """
    existing = get_company_by_code(payload.company_code)
    if existing:
        raise HTTPException(status_code=409, detail=f"Company with code '{payload.company_code}' already exists")

    try:
        created = create_company(
            company_code=payload.company_code,
            company_name=payload.company_name,
            short_name=payload.short_name,
            tax_id=payload.tax_id,
            branch_code=payload.branch_code,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=409, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to create company record: {err}")

    if not created:
        raise HTTPException(status_code=500, detail="Failed to create company record")

    # Bootstrap storage folders
    initialize_storage_directories()

    if isinstance(created, dict):
        return created
    return get_company(str(created))


@router.patch("/{company_id}", summary="Update company details")
def update_company_details(
    company_id: str,
    payload: CompanyUpdateSchema,
    db: Session = Depends(get_db_session_dep)
):
    """
    Updates details or active status of an existing company.
    """
    existing = get_company(company_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Company not found")

    update_fields = payload.model_dump(exclude_unset=True)
    if not update_fields:
        return existing

    try:
        success = update_company(company_id, **update_fields)
    except ValueError as val_err:
        raise HTTPException(status_code=409, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to update company record: {err}")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update company record")

    return get_company(company_id)


@router.delete("/{company_id_or_code}", summary="Delete a company")
def delete_company_endpoint(
    company_id_or_code: str,
    db: Session = Depends(get_db_session_dep)
):
    """
    Deletes a company record by UUID company_id or unique company_code.
    """
    success = delete_company(company_id_or_code)
    if not success:
        raise HTTPException(status_code=404, detail=f"Company '{company_id_or_code}' not found or failed to delete")
    return {"status": "success", "message": f"Company '{company_id_or_code}' deleted successfully"}

