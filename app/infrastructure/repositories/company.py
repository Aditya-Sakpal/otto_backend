from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database.models.company import CompanyORM
import logging

logger = logging.getLogger(__name__)


class CompanyRepository:
    """Repository for Company database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        reference_doc_url: str,
        csr_sop_doc_url: str | None = None,
        sales_sop_doc_url: str | None = None,
        phone_number: str | None = None,
        address: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CompanyORM:
        """
        Create a new company record.

        Args:
            name: Company name
            reference_doc_url: URL to reference document in S3
            csr_sop_doc_url: URL to CSR SOP document in S3 (optional)
            sales_sop_doc_url: URL to Sales SOP document in S3 (optional)
            phone_number: Company phone number (optional)
            address: Company address (optional)
            extra_metadata: Additional metadata (optional)

        Returns:
            Created CompanyORM instance
        """
        company_orm = CompanyORM(
            name=name,
            phone_number=phone_number,
            address=address,
            reference_doc_url=reference_doc_url,
            csr_sop_doc_url=csr_sop_doc_url,
            sales_sop_doc_url=sales_sop_doc_url,
            extra_metadata=extra_metadata or {}
        )
        self.db.add(company_orm)
        await self.db.flush()
        await self.db.refresh(company_orm)

        logger.info(f"Created company: {name} (ID: {company_orm.id})")
        return company_orm

    async def get_by_id(self, company_id: UUID) -> CompanyORM | None:
        """
        Retrieve a company by ID.

        Args:
            company_id: Company UUID

        Returns:
            CompanyORM instance or None if not found
        """
        result = await self.db.execute(
            select(CompanyORM).where(CompanyORM.id == company_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        company_id: UUID,
        name: str | None = None,
        phone_number: str | None = None,
        address: str | None = None,
        reference_doc_url: str | None = None,
        csr_sop_doc_url: str | None = None,
        sales_sop_doc_url: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CompanyORM | None:
        """
        Update a company record.

        Args:
            company_id: Company UUID
            name: Company name (optional)
            phone_number: Company phone number (optional)
            address: Company address (optional)
            reference_doc_url: URL to reference document (optional)
            csr_sop_doc_url: URL to CSR SOP document (optional)
            sales_sop_doc_url: URL to Sales SOP document (optional)
            extra_metadata: Additional metadata (optional)

        Returns:
            Updated CompanyORM instance or None if not found
        """
        company = await self.get_by_id(company_id)
        if not company:
            return None

        if name is not None:
            company.name = name
        if phone_number is not None:
            company.phone_number = phone_number
        if address is not None:
            company.address = address
        if reference_doc_url is not None:
            company.reference_doc_url = reference_doc_url
        if csr_sop_doc_url is not None:
            company.csr_sop_doc_url = csr_sop_doc_url
        if sales_sop_doc_url is not None:
            company.sales_sop_doc_url = sales_sop_doc_url
        if extra_metadata is not None:
            company.extra_metadata = extra_metadata

        await self.db.flush()
        await self.db.refresh(company)

        logger.info(f"Updated company: {company.name} (ID: {company_id})")
        return company

    async def delete(self, company_id: UUID) -> bool:
        """
        Delete a company record.

        Args:
            company_id: Company UUID

        Returns:
            True if deleted, False if not found
        """
        company = await self.get_by_id(company_id)
        if not company:
            return False

        await self.db.delete(company)
        await self.db.flush()

        logger.info(f"Deleted company ID: {company_id}")
        return True
