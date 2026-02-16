# Batch Call Processing and Comparison Scripts

This directory contains scripts for batch processing calls and comparing Otto Intelligence summaries with reference summaries.

## Scripts

### 1. `batch_process_calls.sh`
Processes multiple S3 audio files through the Otto Intelligence API and saves their summaries.

### 2. `compare_summaries.py`
Uses Groq LLM to perform detailed comparative analysis between Otto summaries and reference summaries.

---

## Prerequisites

### For Batch Processing
- Otto Intelligence API running (default: `http://localhost:9000`)
- Valid API key
- S3 audio files accessible

### For Comparison
- Python 3.8+
- Groq API key
- Python packages:
  ```bash
  pip install groq python-dotenv
  ```

---

## Usage Guide

### Step 1: Create S3 Links File

Create a text file with one S3 URL per line:

```bash
# s3_links.txt
https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/1323570943-redacted.mp3
https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/1323580300-redacted.mp3
https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/1323597077-redacted.mp3
```

### Step 2: Run Batch Processing

```bash
# Make script executable
chmod +x batch_process_calls.sh

# Run with default settings
./batch_process_calls.sh s3_links.txt

# Run with custom settings
COMPANY_ID="az_roofers" \
REP_ROLE="customer_rep" \
STARTING_CALL_ID="430" \
OUTPUT_DIR="./results_430_432" \
./batch_process_calls.sh s3_links.txt
```

**Environment Variables:**
- `API_KEY` - API key (default: uses hardcoded key)
- `BASE_URL` - API base URL (default: `http://localhost:9000`)
- `COMPANY_ID` - Company identifier (default: `az_roofers`)
- `REP_ROLE` - Representative role: `customer_rep` or `sales_rep` (default: `customer_rep`)
- `TIMEZONE` - Timezone (default: `America/Phoenix`)
- `OUTPUT_DIR` - Output directory (default: `./batch_results`)
- `STARTING_CALL_ID` - Starting call ID number (default: `1000`)

**Output:**
- `{OUTPUT_DIR}/{call_id}_summary.json` - Otto summary for each call
- `{OUTPUT_DIR}/batch_processing_{timestamp}.log` - Processing log

### Step 3: Prepare Reference Summaries

Create a directory with reference summaries as text files:

```bash
# reference_summaries/
reference_summaries/430.txt
reference_summaries/431.txt
reference_summaries/432.txt
```

Each file should contain the reference summary text for that call ID.

### Step 4: Run Comparative Analysis

```bash
# Make script executable
chmod +x compare_summaries.py

# Set Groq API key
export GROQ_API_KEY="your_groq_api_key_here"

# Compare all summaries
python3 compare_summaries.py \
  -o ./results_430_432 \
  -r ./reference_summaries \
  -out ./comparison_results

# Compare specific call IDs only
python3 compare_summaries.py \
  -o ./results_430_432 \
  -r ./reference_summaries \
  -out ./comparison_results \
  -c 430 431 432
```

**Arguments:**
- `-o`, `--otto-dir` - Directory with Otto summary JSON files (required)
- `-r`, `--reference-dir` - Directory with reference summary TXT files (required)
- `-out`, `--output-dir` - Directory to save comparison results (required)
- `-c`, `--call-ids` - Specific call IDs to compare (optional)

**Output:**
- `{OUTPUT_DIR}/{call_id}_analysis.json` - Structured analysis JSON
- `{OUTPUT_DIR}/{call_id}_report.txt` - Human-readable report

---

## Complete Workflow Example

```bash
# 1. Create S3 links file
cat > s3_links.txt << EOF
https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/1323570943-redacted.mp3
https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/1323580300-redacted.mp3
https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/1323597077-redacted.mp3
EOF

# 2. Process calls
COMPANY_ID="az_roofers" \
REP_ROLE="customer_rep" \
STARTING_CALL_ID="430" \
OUTPUT_DIR="./otto_summaries" \
./batch_process_calls.sh s3_links.txt

# 3. Create reference summaries directory
mkdir -p reference_summaries

# 4. Add reference summaries (example)
cat > reference_summaries/430.txt << EOF
Customer called about roof inspection. Appointment confirmed for Thursday.
No objections raised. CSR explained appointment process well.
EOF

cat > reference_summaries/431.txt << EOF
Mother-in-law is the homeowner. Her name is [Name].
Single story tile roof, not in HOA, not gated.
Customer spelled out name letter by letter: [Spelling].
EOF

# 5. Run comparison
export GROQ_API_KEY="your_api_key"
python3 compare_summaries.py \
  -o ./otto_summaries \
  -r ./reference_summaries \
  -out ./comparison_results \
  -c 430 431

# 6. View results
cat comparison_results/430_report.txt
cat comparison_results/431_report.txt
```

---

## Analysis Report Structure

The comparison script produces detailed reports with:

### Overall Assessment
- Accuracy rating (0-100)
- Summary assessment

### Correct Extractions
- What Otto got right
- Matches with reference summary

### Incorrect Extractions
- What Otto got wrong
- Severity levels (critical, high, medium, low)
- Expected vs actual values

### Missed Information
- Information in reference but not in Otto
- Importance levels

### Additional Information
- Information Otto extracted but not in reference
- Correctness evaluation

### Specific Issues by Category
- Customer information issues
- Appointment details issues
- Objection detection issues
- Property details issues
- Compliance evaluation issues

### Recommendations
- Specific suggestions for improvement

### Key Strengths
- What Otto does well

---

## Troubleshooting

### Batch Processing Issues

**API Connection Failed:**
```bash
# Check if API is running
curl http://localhost:9000/health

# Check if using correct base URL
BASE_URL="http://your-api-url:port" ./batch_process_calls.sh s3_links.txt
```

**Authentication Failed:**
```bash
# Verify API key
API_KEY="your_actual_api_key" ./batch_process_calls.sh s3_links.txt
```

**Job Timeout:**
- Increase `MAX_ATTEMPTS` in the script (default: 120 = 10 minutes)
- Check API logs for processing errors

### Comparison Issues

**Groq API Key Not Found:**
```bash
# Set in environment
export GROQ_API_KEY="your_key"

# Or add to .env file
echo "GROQ_API_KEY=your_key" >> .env
```

**JSON Parsing Failed:**
- The script will save raw analysis if JSON parsing fails
- Check `{call_id}_analysis.json` for raw output

**File Not Found:**
- Ensure Otto summaries are named: `{call_id}_summary.json`
- Ensure reference summaries are named: `{call_id}.txt`

---

## Configuration

### Batch Processing Configuration

Edit the script or use environment variables:
```bash
# In batch_process_calls.sh
API_KEY="${API_KEY:-your_default_key}"
BASE_URL="${BASE_URL:-http://localhost:9000}"
COMPANY_ID="${COMPANY_ID:-az_roofers}"
REP_ROLE="${REP_ROLE:-customer_rep}"
```

### LLM Configuration

Edit your `.env` file:
```bash
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile  # or other Groq models
```

Available Groq models:
- `llama-3.3-70b-versatile` (recommended for analysis)
- `llama-3.1-70b-versatile`
- `mixtral-8x7b-32768`

---

## Tips

1. **Start Small:** Test with 1-2 calls before processing large batches
2. **Check Logs:** Review `batch_processing_*.log` for detailed processing info
3. **Rate Limiting:** Script includes 2-second delays between calls
4. **Long Running:** Processing 10 calls can take 30-60 minutes depending on audio length
5. **Groq Limits:** Free tier has rate limits; consider pauses for large batches

---

## Example Output

### Batch Processing Output
```
═══════════════════════════════════════════
Processing Call 1/3
Call ID: 430
Audio URL: https://...
═══════════════════════════════════════════

[1/3] Submitting call for processing...
✓ Call submitted (Job ID: job_xyz)

[2/3] Polling for job completion...
  Attempt 1/120 - Status: processing, Progress: 20%, Step: transcribing
  ...
✓ Job completed successfully

[3/3] Fetching call summary...
✓ Summary saved to: ./otto_summaries/430_summary.json

Key Metrics:
  - Overall Score: 0.82
  - Qualification Status: hot
  - Booking Status: booked
  - Call Outcome: qualified_and_booked
  - SOP Compliance Score: 0.89
  - Total Objections: 2
  - Objections Overcome: 1
```

### Comparison Report Output
```
================================================================================
COMPARATIVE ANALYSIS REPORT - Call ID: 430
================================================================================

OVERALL ASSESSMENT
--------------------------------------------------------------------------------
Accuracy Rating: 85/100
Summary: Otto captured most key information accurately but missed appointment
time details and had minor speaker attribution issues.

✓ CORRECT EXTRACTIONS
--------------------------------------------------------------------------------
  • Customer Information - Phone Number
    Value: +14805551234
    Note: Correctly extracted from call

  • Appointment - Date
    Value: Thursday
    Note: Day correctly identified

✗ INCORRECT EXTRACTIONS
--------------------------------------------------------------------------------
  🟠 Appointment Details - Time [high]
    Otto Extracted: null
    Expected: 2:00 PM
    Issue: Only captured day (Thursday) but not the time (2:00 PM)

  🟡 Objections - False Positive [medium]
    Otto Extracted: "Let me tell you about our process"
    Expected: No objection here
    Issue: This was the rep speaking, not an objection from customer
```

---

## Support

For issues or questions:
1. Check this README
2. Review script logs
3. Check API documentation
4. Contact development team

---

**Last Updated:** January 16, 2026


