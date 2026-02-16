#!/usr/bin/env python3
"""
Extract text from the Sales Intelligence PDFs for analysis.
"""

import pdfplumber
import os
import json

# PDF files to process
PDF_FILES = [
    "Fundamental Sales Priinciples from sales manager.pdf",
    "Overview.pdf",
    "Sales Intelligence & Coaching Bible.pdf"
]

OUTPUT_DIR = "./analysis_results/pdf_extracts"

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
    except Exception as e:
        print(f"Error extracting {pdf_path}: {e}")
        return f"Error: {e}"
    return text

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_extracts = {}
    
    for pdf_file in PDF_FILES:
        pdf_path = os.path.join("/home/ubuntu/otto-intelligence", pdf_file)
        
        if not os.path.exists(pdf_path):
            print(f"File not found: {pdf_path}")
            continue
            
        print(f"Extracting: {pdf_file}")
        text = extract_text_from_pdf(pdf_path)
        
        # Save individual text file
        safe_name = pdf_file.replace(" ", "_").replace(".pdf", ".txt")
        output_path = os.path.join(OUTPUT_DIR, safe_name)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        
        print(f"  Saved to: {output_path}")
        print(f"  Characters: {len(text)}")
        
        all_extracts[pdf_file] = {
            "path": output_path,
            "length": len(text),
            "preview": text[:500] + "..." if len(text) > 500 else text
        }
    
    # Save summary
    summary_path = os.path.join(OUTPUT_DIR, "extraction_summary.json")
    with open(summary_path, "w") as f:
        json.dump(all_extracts, f, indent=2)
    
    print(f"\nSummary saved to: {summary_path}")
    print("\nDone!")

if __name__ == "__main__":
    main()

