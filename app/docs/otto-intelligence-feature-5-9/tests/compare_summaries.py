#!/usr/bin/env python3
"""
LLM-Based Comparative Analysis Script
Compares Otto Intelligence summaries with reference summaries using Groq LLM
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Color codes for terminal output
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    MAGENTA = '\033[0;35m'
    NC = '\033[0m'  # No Color
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.NC}\n")


def print_section(text: str):
    """Print a section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{text}{Colors.NC}")
    print(f"{Colors.BLUE}{'-'*len(text)}{Colors.NC}")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.NC}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.NC}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.NC}")


def read_otto_summary(json_path: Path) -> Dict[str, Any]:
    """Read Otto Intelligence summary JSON file"""
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Failed to read Otto summary: {e}")


def read_reference_summary(txt_path: Path) -> str:
    """Read reference summary text file"""
    try:
        with open(txt_path, 'r') as f:
            return f.read()
    except Exception as e:
        raise Exception(f"Failed to read reference summary: {e}")


def extract_otto_key_fields(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key fields from Otto summary for comparison"""
    extracted = {
        "call_id": summary.get("call_id"),
        "company_id": summary.get("company_id"),
        "processed_at": summary.get("processed_at"),
    }
    
    # Summary section
    if "summary" in summary:
        extracted["summary"] = {
            "call_summary": summary["summary"].get("call_summary"),
            "key_points": summary["summary"].get("key_points", []),
            "action_items": summary["summary"].get("action_items", []),
            "sentiment_score": summary["summary"].get("sentiment_score"),
        }
    
    # Qualification section
    if "qualification" in summary:
        qual = summary["qualification"]
        extracted["qualification"] = {
            "overall_score": qual.get("overall_score"),
            "qualification_status": qual.get("qualification_status"),
            "booking_status": qual.get("booking_status"),
            "call_outcome_category": qual.get("call_outcome_category"),
            "appointment_date": qual.get("appointment_date"),
            "appointment_confirmed": qual.get("appointment_confirmed"),
            "customer_name": qual.get("customer_details", {}).get("name"),
            "customer_email": qual.get("customer_details", {}).get("email"),
            "customer_phone": qual.get("customer_details", {}).get("phone"),
            "address": qual.get("customer_details", {}).get("address"),
            "property_details": qual.get("property_details", {}),
            "urgency_signals": qual.get("urgency_signals", []),
            "budget_indicators": qual.get("budget_indicators", []),
        }
    
    # Compliance section
    if "compliance" in summary:
        comp = summary["compliance"]
        extracted["compliance"] = {
            "target_role": comp.get("target_role"),
            "sop_compliance_score": comp.get("sop_compliance", {}).get("score"),
            "stages_followed": comp.get("sop_compliance", {}).get("stages", {}).get("followed", []),
            "stages_missed": comp.get("sop_compliance", {}).get("stages", {}).get("missed", []),
            "issues": comp.get("sop_compliance", {}).get("issues", []),
            "positive_behaviors": comp.get("sop_compliance", {}).get("positive_behaviors", []),
        }
    
    # Objections section
    if "objections" in summary:
        obj = summary["objections"]
        extracted["objections"] = {
            "total_objections": obj.get("total_objections", 0),
            "objections_overcome": obj.get("objections_overcome", 0),
            "objections_list": [
                {
                    "category": o.get("category_text"),
                    "text": o.get("objection_text"),
                    "overcome": o.get("overcome"),
                    "speaker": o.get("speaker_id"),
                    "severity": o.get("severity"),
                }
                for o in obj.get("objections", [])
            ]
        }
    
    return extracted


async def analyze_with_llm(
    otto_data: Dict[str, Any],
    reference_summary: str,
    call_id: str,
    client: AsyncGroq
) -> Dict[str, Any]:
    """Use LLM to perform detailed comparative analysis"""
    
    print_section(f"Analyzing Call {call_id} with LLM")
    print("Sending request to Groq API...")
    
    prompt = f"""You are an expert call analysis system evaluator. You will compare two call summaries:
1. **Otto Intelligence Summary** (JSON format) - Our new system
2. **Reference Summary** (Text format) - Existing system

Your task is to perform a DETAILED comparative analysis and identify:
- What Otto got RIGHT that the reference system also captured
- What Otto got WRONG (hallucinations, incorrect information)
- What Otto MISSED that the reference system captured
- What Otto ADDED that the reference system missed (could be good or bad)
- Specific accuracy issues (names, dates, addresses, numbers, etc.)
- Objection detection accuracy
- Customer information accuracy
- Appointment details accuracy
- Property details accuracy

**OTTO INTELLIGENCE SUMMARY:**
```json
{json.dumps(otto_data, indent=2)}
```

**REFERENCE SUMMARY:**
```
{reference_summary}
```

Please provide a structured analysis in the following JSON format:

{{
  "overall_assessment": {{
    "accuracy_rating": "<score 0-100>",
    "summary": "<brief overall assessment>"
  }},
  "correct_extractions": [
    {{
      "category": "<category name>",
      "field": "<specific field>",
      "value": "<extracted value>",
      "note": "<why this is correct>"
    }}
  ],
  "incorrect_extractions": [
    {{
      "category": "<category name>",
      "field": "<specific field>",
      "otto_value": "<what Otto extracted>",
      "expected_value": "<what should have been extracted>",
      "severity": "<critical|high|medium|low>",
      "issue": "<detailed explanation>"
    }}
  ],
  "missed_information": [
    {{
      "category": "<category name>",
      "information": "<what was missed>",
      "importance": "<critical|high|medium|low>",
      "note": "<why this matters>"
    }}
  ],
  "additional_information": [
    {{
      "category": "<category name>",
      "information": "<what Otto added>",
      "correctness": "<correct|incorrect|uncertain>",
      "note": "<evaluation of this addition>"
    }}
  ],
  "specific_issues": {{
    "customer_information": [
      {{
        "field": "<field name>",
        "issue": "<description>",
        "severity": "<critical|high|medium|low>"
      }}
    ],
    "appointment_details": [
      {{
        "field": "<field name>",
        "issue": "<description>",
        "severity": "<critical|high|medium|low>"
      }}
    ],
    "objections": [
      {{
        "objection_text": "<objection>",
        "issue": "<description>",
        "severity": "<critical|high|medium|low>"
      }}
    ],
    "property_details": [
      {{
        "field": "<field name>",
        "issue": "<description>",
        "severity": "<critical|high|medium|low>"
      }}
    ],
    "compliance_evaluation": [
      {{
        "aspect": "<aspect name>",
        "issue": "<description>",
        "severity": "<critical|high|medium|low>"
      }}
    ]
  }},
  "recommendations": [
    "<specific recommendation for improvement>"
  ],
  "key_strengths": [
    "<what Otto does well>"
  ]
}}

Be extremely thorough and specific. Compare every detail. Look for:
- Name spelling accuracy (especially if customer spelled it out)
- Address accuracy (street names, postal codes)
- Date and time accuracy (did it capture full datetime or just day?)
- Decision maker identification
- Speaker attribution (who said what)
- False positive objections
- Missing key details mentioned in the call
- Property characteristics (roof type, HOA, solar, pets, etc.)
"""

    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert call analysis evaluator. Provide detailed, accurate, and structured analysis in JSON format."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,  # Low temperature for consistent analysis
            max_tokens=8000,
        )
        
        analysis_text = response.choices[0].message.content
        
        # Try to extract JSON from the response
        try:
            # Find JSON in markdown code blocks if present
            if "```json" in analysis_text:
                json_start = analysis_text.find("```json") + 7
                json_end = analysis_text.find("```", json_start)
                analysis_text = analysis_text[json_start:json_end].strip()
            elif "```" in analysis_text:
                json_start = analysis_text.find("```") + 3
                json_end = analysis_text.find("```", json_start)
                analysis_text = analysis_text[json_start:json_end].strip()
            
            analysis = json.loads(analysis_text)
            print_success("Analysis completed")
            return analysis
            
        except json.JSONDecodeError as e:
            print_warning(f"Could not parse LLM response as JSON: {e}")
            # Return raw text if JSON parsing fails
            return {
                "overall_assessment": {
                    "accuracy_rating": "N/A",
                    "summary": "Failed to parse structured analysis"
                },
                "raw_analysis": analysis_text
            }
    
    except Exception as e:
        print_error(f"LLM analysis failed: {e}")
        return {
            "error": str(e),
            "overall_assessment": {
                "accuracy_rating": "N/A",
                "summary": f"Analysis failed: {e}"
            }
        }


def format_analysis_report(call_id: str, analysis: Dict[str, Any]) -> str:
    """Format the analysis into a readable report"""
    
    report = []
    report.append("=" * 80)
    report.append(f"COMPARATIVE ANALYSIS REPORT - Call ID: {call_id}")
    report.append("=" * 80)
    report.append("")
    
    # Overall Assessment
    if "overall_assessment" in analysis:
        assessment = analysis["overall_assessment"]
        report.append("OVERALL ASSESSMENT")
        report.append("-" * 80)
        report.append(f"Accuracy Rating: {assessment.get('accuracy_rating', 'N/A')}/100")
        report.append(f"Summary: {assessment.get('summary', 'N/A')}")
        report.append("")
    
    # Correct Extractions
    if "correct_extractions" in analysis and analysis["correct_extractions"]:
        report.append("✓ CORRECT EXTRACTIONS")
        report.append("-" * 80)
        for item in analysis["correct_extractions"]:
            report.append(f"  • {item.get('category')} - {item.get('field')}")
            report.append(f"    Value: {item.get('value')}")
            report.append(f"    Note: {item.get('note')}")
            report.append("")
    
    # Incorrect Extractions
    if "incorrect_extractions" in analysis and analysis["incorrect_extractions"]:
        report.append("✗ INCORRECT EXTRACTIONS")
        report.append("-" * 80)
        for item in analysis["incorrect_extractions"]:
            severity_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢"
            }.get(item.get('severity', 'medium'), "⚪")
            
            report.append(f"  {severity_emoji} {item.get('category')} - {item.get('field')} [{item.get('severity', 'N/A')}]")
            report.append(f"    Otto Extracted: {item.get('otto_value')}")
            report.append(f"    Expected: {item.get('expected_value')}")
            report.append(f"    Issue: {item.get('issue')}")
            report.append("")
    
    # Missed Information
    if "missed_information" in analysis and analysis["missed_information"]:
        report.append("⚠ MISSED INFORMATION")
        report.append("-" * 80)
        for item in analysis["missed_information"]:
            importance_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢"
            }.get(item.get('importance', 'medium'), "⚪")
            
            report.append(f"  {importance_emoji} {item.get('category')} [{item.get('importance', 'N/A')}]")
            report.append(f"    Information: {item.get('information')}")
            report.append(f"    Note: {item.get('note')}")
            report.append("")
    
    # Additional Information
    if "additional_information" in analysis and analysis["additional_information"]:
        report.append("+ ADDITIONAL INFORMATION (Not in Reference)")
        report.append("-" * 80)
        for item in analysis["additional_information"]:
            correctness_emoji = {
                "correct": "✓",
                "incorrect": "✗",
                "uncertain": "?"
            }.get(item.get('correctness', 'uncertain'), "?")
            
            report.append(f"  {correctness_emoji} {item.get('category')} [{item.get('correctness', 'N/A')}]")
            report.append(f"    Information: {item.get('information')}")
            report.append(f"    Note: {item.get('note')}")
            report.append("")
    
    # Specific Issues
    if "specific_issues" in analysis:
        report.append("SPECIFIC ISSUES BY CATEGORY")
        report.append("-" * 80)
        
        for category, issues in analysis["specific_issues"].items():
            if issues:
                report.append(f"\n  {category.replace('_', ' ').title()}:")
                for issue in issues:
                    severity = issue.get('severity', 'N/A')
                    severity_emoji = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢"
                    }.get(severity, "⚪")
                    
                    if 'field' in issue:
                        report.append(f"    {severity_emoji} {issue.get('field')}: {issue.get('issue')}")
                    elif 'objection_text' in issue:
                        report.append(f"    {severity_emoji} '{issue.get('objection_text')}': {issue.get('issue')}")
                    elif 'aspect' in issue:
                        report.append(f"    {severity_emoji} {issue.get('aspect')}: {issue.get('issue')}")
                report.append("")
    
    # Recommendations
    if "recommendations" in analysis and analysis["recommendations"]:
        report.append("RECOMMENDATIONS FOR IMPROVEMENT")
        report.append("-" * 80)
        for i, rec in enumerate(analysis["recommendations"], 1):
            report.append(f"  {i}. {rec}")
        report.append("")
    
    # Key Strengths
    if "key_strengths" in analysis and analysis["key_strengths"]:
        report.append("KEY STRENGTHS")
        report.append("-" * 80)
        for i, strength in enumerate(analysis["key_strengths"], 1):
            report.append(f"  {i}. {strength}")
        report.append("")
    
    # Raw Analysis (if structured parsing failed)
    if "raw_analysis" in analysis:
        report.append("RAW ANALYSIS (Structured parsing failed)")
        report.append("-" * 80)
        report.append(analysis["raw_analysis"])
        report.append("")
    
    report.append("=" * 80)
    report.append("")
    
    return "\n".join(report)


async def compare_single_call(
    call_id: str,
    otto_summary_path: Path,
    reference_summary_path: Path,
    output_dir: Path,
    client: AsyncGroq
) -> bool:
    """Compare a single call's summaries"""
    
    print_header(f"Comparing Call ID: {call_id}")
    
    try:
        # Read files
        print(f"Reading Otto summary: {otto_summary_path}")
        otto_summary = read_otto_summary(otto_summary_path)
        
        print(f"Reading reference summary: {reference_summary_path}")
        reference_summary = read_reference_summary(reference_summary_path)
        
        # Extract key fields from Otto summary
        print("Extracting key fields from Otto summary...")
        otto_data = extract_otto_key_fields(otto_summary)
        
        # Perform LLM analysis
        analysis = await analyze_with_llm(otto_data, reference_summary, call_id, client)
        
        # Generate report
        report_text = format_analysis_report(call_id, analysis)
        
        # Save analysis to JSON
        analysis_json_path = output_dir / f"{call_id}_analysis.json"
        with open(analysis_json_path, 'w') as f:
            json.dump(analysis, indent=2, fp=f)
        print_success(f"Analysis JSON saved: {analysis_json_path}")
        
        # Save report to text file
        report_txt_path = output_dir / f"{call_id}_report.txt"
        with open(report_txt_path, 'w') as f:
            f.write(report_text)
        print_success(f"Analysis report saved: {report_txt_path}")
        
        # Print report to console
        print(report_text)
        
        return True
        
    except Exception as e:
        print_error(f"Failed to compare call {call_id}: {e}")
        return False


async def compare_batch(
    otto_summaries_dir: Path,
    reference_summaries_dir: Path,
    output_dir: Path,
    call_ids: List[str] = None
):
    """Compare multiple calls in batch"""
    
    print_header("Batch Comparative Analysis")
    
    # Initialize Groq client
    if not GROQ_API_KEY:
        print_error("GROQ_API_KEY not found in environment variables")
        print("Please set it in your .env file or export it:")
        print("  export GROQ_API_KEY='your_api_key_here'")
        sys.exit(1)
    
    client = AsyncGroq(api_key=GROQ_API_KEY)
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all Otto summaries if no specific call IDs provided
    if not call_ids:
        otto_files = list(otto_summaries_dir.glob("*_summary.json"))
        call_ids = [f.stem.replace("_summary", "") for f in otto_files]
        print(f"Found {len(call_ids)} Otto summaries to compare")
    
    if not call_ids:
        print_error("No summaries found to compare")
        return
    
    # Process each call
    successful = 0
    failed = 0
    
    for call_id in call_ids:
        otto_path = otto_summaries_dir / f"{call_id}_summary.json"
        reference_path = reference_summaries_dir / f"{call_id}.txt"
        
        # Check if both files exist
        if not otto_path.exists():
            print_error(f"Otto summary not found: {otto_path}")
            failed += 1
            continue
        
        if not reference_path.exists():
            print_error(f"Reference summary not found: {reference_path}")
            failed += 1
            continue
        
        # Compare
        if await compare_single_call(call_id, otto_path, reference_path, output_dir, client):
            successful += 1
        else:
            failed += 1
        
        # Small delay between API calls
        if call_ids.index(call_id) < len(call_ids) - 1:
            await asyncio.sleep(1)
    
    # Final summary
    print_header("Batch Comparison Complete")
    print(f"Total Calls: {len(call_ids)}")
    print_success(f"Successful: {successful}")
    if failed > 0:
        print_error(f"Failed: {failed}")
    print(f"\nResults saved in: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare Otto Intelligence summaries with reference summaries using LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare all summaries in directories
  python compare_summaries.py -o ./batch_results -r ./reference_summaries -out ./comparison_results

  # Compare specific call IDs
  python compare_summaries.py -o ./batch_results -r ./reference_summaries -out ./comparison_results -c 430 431 432

  # Single call comparison
  python compare_summaries.py -o ./batch_results -r ./reference_summaries -out ./comparison_results -c 430

Environment Variables:
  GROQ_API_KEY  - Your Groq API key (required)
  GROQ_MODEL    - Model to use (default: llama-3.3-70b-versatile)
        """
    )
    
    parser.add_argument(
        "-o", "--otto-dir",
        type=str,
        required=True,
        help="Directory containing Otto summary JSON files (e.g., ./batch_results)"
    )
    
    parser.add_argument(
        "-r", "--reference-dir",
        type=str,
        required=True,
        help="Directory containing reference summary TXT files"
    )
    
    parser.add_argument(
        "-out", "--output-dir",
        type=str,
        required=True,
        help="Directory to save comparison results"
    )
    
    parser.add_argument(
        "-c", "--call-ids",
        type=str,
        nargs="+",
        help="Specific call IDs to compare (optional, compares all if not specified)"
    )
    
    args = parser.parse_args()
    
    # Convert to Path objects
    otto_dir = Path(args.otto_dir)
    reference_dir = Path(args.reference_dir)
    output_dir = Path(args.output_dir)
    
    # Validate directories
    if not otto_dir.exists():
        print_error(f"Otto summaries directory not found: {otto_dir}")
        sys.exit(1)
    
    if not reference_dir.exists():
        print_error(f"Reference summaries directory not found: {reference_dir}")
        sys.exit(1)
    
    # Run comparison
    asyncio.run(compare_batch(otto_dir, reference_dir, output_dir, args.call_ids))


if __name__ == "__main__":
    main()


