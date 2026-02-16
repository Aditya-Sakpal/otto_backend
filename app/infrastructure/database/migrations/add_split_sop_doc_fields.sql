-- Add csr_sop column safely
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS csr_sop_doc_url TEXT;

-- Add sales_sop column safely
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS sales_sop_doc_url TEXT;
