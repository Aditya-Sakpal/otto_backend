#!/bin/bash
# Batch Call Processing Script
# Processes multiple S3 audio files and saves their summaries

set -e

# Configuration
API_KEY="${API_KEY:-5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP}"
BASE_URL="${BASE_URL:-http://ottoai.shunyalabs.ai}"
COMPANY_ID="${COMPANY_ID:-az_roofers}"
REP_ROLE="${REP_ROLE:-customer_rep}"
TIMEZONE="${TIMEZONE:-America/Phoenix}"
OUTPUT_DIR="${OUTPUT_DIR:-./batch_results}"
STARTING_CALL_ID="${STARTING_CALL_ID:-1000}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "==========================================="
echo "  Batch Call Processing Script"
echo "==========================================="
echo ""
echo "Configuration:"
echo "  Base URL: $BASE_URL"
echo "  Company ID: $COMPANY_ID"
echo "  Rep Role: $REP_ROLE"
echo "  Starting Call ID: $STARTING_CALL_ID"
echo "  Output Directory: $OUTPUT_DIR"
echo ""

# Check if S3 links file is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <s3_links_file>"
    echo ""
    echo "The s3_links_file should contain one S3 URL per line, e.g.:"
    echo "  https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/call1.mp3"
    echo "  https://otto-call-recording.s3.us-east-1.amazonaws.com/v1/call2.mp3"
    echo ""
    echo "Environment variables (optional):"
    echo "  API_KEY           - API key for authentication"
    echo "  BASE_URL          - Base URL of the API (default: http://localhost:9000)"
    echo "  COMPANY_ID        - Company identifier (default: az_roofers)"
    echo "  REP_ROLE          - Rep role: customer_rep or sales_rep (default: customer_rep)"
    echo "  TIMEZONE          - Timezone (default: America/Phoenix)"
    echo "  OUTPUT_DIR        - Output directory (default: ./batch_results)"
    echo "  STARTING_CALL_ID  - Starting call ID number (default: 1000)"
    exit 1
fi

S3_LINKS_FILE="$1"

# Check if S3 links file exists
if [ ! -f "$S3_LINKS_FILE" ]; then
    echo -e "${RED}ERROR: S3 links file not found: $S3_LINKS_FILE${NC}"
    exit 1
fi

# Read S3 links into array
mapfile -t S3_LINKS < "$S3_LINKS_FILE"
TOTAL_CALLS=${#S3_LINKS[@]}

echo "Found $TOTAL_CALLS S3 links to process"
echo ""

# Health check
echo -e "${BLUE}Checking API health...${NC}"
HEALTH_RESPONSE=$(curl -s "$BASE_URL/health" || echo "failed")
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}✓ API is healthy${NC}"
else
    echo -e "${RED}✗ API health check failed${NC}"
    echo "Response: $HEALTH_RESPONSE"
    exit 1
fi
echo ""

# Initialize counters
SUCCESSFUL=0
FAILED=0
CURRENT_CALL_ID=$STARTING_CALL_ID

# Log file
LOG_FILE="$OUTPUT_DIR/batch_processing_$(date +%Y%m%d_%H%M%S).log"
echo "Log file: $LOG_FILE"
echo ""

# Function to process a single call
process_call() {
    local AUDIO_URL="$1"
    local CALL_ID="$2"
    local INDEX="$3"
    
    echo "═══════════════════════════════════════════" | tee -a "$LOG_FILE"
    echo "Processing Call $INDEX/$TOTAL_CALLS" | tee -a "$LOG_FILE"
    echo "Call ID: $CALL_ID" | tee -a "$LOG_FILE"
    echo "Audio URL: $AUDIO_URL" | tee -a "$LOG_FILE"
    echo "═══════════════════════════════════════════" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # Submit call for processing
    echo -e "${BLUE}[1/3] Submitting call for processing...${NC}" | tee -a "$LOG_FILE"
    
    PROCESS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/v1/call-processing/process" \
      -H "X-API-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "call_id": "'"$CALL_ID"'",
        "company_id": "'"$COMPANY_ID"'",
        "audio_url": "'"$AUDIO_URL"'",
        "phone_number": "+14805551234",
        "rep_role": "'"$REP_ROLE"'",
        "timezone": "'"$TIMEZONE"'",
        "call_date": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "metadata": {
          "batch_processing": true,
          "batch_index": '"$INDEX"'
        },
        "options": {
          "skip_rag_indexing": false,
          "skip_summary_generation": false,
          "priority": "normal"
        }
      }')
    
    HTTP_STATUS=$(echo "$PROCESS_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
    RESPONSE_BODY=$(echo "$PROCESS_RESPONSE" | sed '/HTTP_STATUS/d')
    
    if [ "$HTTP_STATUS" != "202" ]; then
        echo -e "${RED}✗ Failed to submit call (HTTP $HTTP_STATUS)${NC}" | tee -a "$LOG_FILE"
        echo "Response: $RESPONSE_BODY" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        return 1
    fi
    
    JOB_ID=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)
    echo -e "${GREEN}✓ Call submitted (Job ID: $JOB_ID)${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # Poll for completion
    echo -e "${BLUE}[2/3] Polling for job completion...${NC}" | tee -a "$LOG_FILE"
    MAX_ATTEMPTS=120  # 10 minutes max
    ATTEMPT=0
    STATUS="queued"
    
    while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ] && [ "$STATUS" != "completed" ] && [ "$STATUS" != "failed" ]; do
        sleep 5
        ATTEMPT=$((ATTEMPT + 1))
        
        STATUS_RESPONSE=$(curl -s "$BASE_URL/api/v1/call-processing/status/$JOB_ID" \
          -H "X-API-Key: $API_KEY")
        
        STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")
        PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', {}).get('percent', 0))" 2>/dev/null || echo "0")
        CURRENT_STEP=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', {}).get('current_step', ''))" 2>/dev/null || echo "unknown")
        
        echo -e "  Attempt $ATTEMPT/$MAX_ATTEMPTS - Status: ${YELLOW}$STATUS${NC}, Progress: $PROGRESS%, Step: $CURRENT_STEP" | tee -a "$LOG_FILE"
    done
    
    echo "" | tee -a "$LOG_FILE"
    
    # Check final status
    if [ "$STATUS" = "completed" ]; then
        echo -e "${GREEN}✓ Job completed successfully${NC}" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        
        # Fetch summary
        echo -e "${BLUE}[3/3] Fetching call summary...${NC}" | tee -a "$LOG_FILE"
        SUMMARY_RESPONSE=$(curl -s "$BASE_URL/api/v1/call-processing/summary/$CALL_ID" \
          -H "X-API-Key: $API_KEY")
        
        # Check if summary was retrieved successfully
        if echo "$SUMMARY_RESPONSE" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
            # Save summary to file
            SUMMARY_FILE="$OUTPUT_DIR/${CALL_ID}_summary.json"
            echo "$SUMMARY_RESPONSE" | python3 -m json.tool > "$SUMMARY_FILE"
            echo -e "${GREEN}✓ Summary saved to: $SUMMARY_FILE${NC}" | tee -a "$LOG_FILE"
            echo "" | tee -a "$LOG_FILE"
            
            # Extract key metrics
            echo "Key Metrics:" | tee -a "$LOG_FILE"
            python3 << EOF | tee -a "$LOG_FILE"
import json
summary = json.loads('''$SUMMARY_RESPONSE''')

if 'qualification' in summary:
    qual = summary['qualification']
    print(f"  - Overall Score: {qual.get('overall_score', 'N/A')}")
    print(f"  - Qualification Status: {qual.get('qualification_status', 'N/A')}")
    print(f"  - Booking Status: {qual.get('booking_status', 'N/A')}")
    print(f"  - Call Outcome: {qual.get('call_outcome_category', 'N/A')}")
    
if 'compliance' in summary and 'sop_compliance' in summary['compliance']:
    comp = summary['compliance']['sop_compliance']
    print(f"  - SOP Compliance Score: {comp.get('score', 'N/A')}")
    
if 'objections' in summary:
    obj = summary['objections']
    print(f"  - Total Objections: {obj.get('total_objections', 0)}")
    print(f"  - Objections Overcome: {obj.get('objections_overcome', 0)}")
EOF
            echo "" | tee -a "$LOG_FILE"
            
            return 0
        else
            echo -e "${RED}✗ Failed to retrieve or parse summary${NC}" | tee -a "$LOG_FILE"
            echo "Response: $SUMMARY_RESPONSE" | tee -a "$LOG_FILE"
            echo "" | tee -a "$LOG_FILE"
            return 1
        fi
    elif [ "$STATUS" = "failed" ]; then
        echo -e "${RED}✗ Job failed${NC}" | tee -a "$LOG_FILE"
        ERROR_MSG=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', {}).get('message', 'Unknown error'))" 2>/dev/null || echo "Unknown error")
        echo "Error: $ERROR_MSG" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        return 1
    else
        echo -e "${RED}✗ Job timed out (Status: $STATUS)${NC}" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        return 1
    fi
}

# Process each S3 link
for i in "${!S3_LINKS[@]}"; do
    AUDIO_URL="${S3_LINKS[$i]}"
    INDEX=$((i + 1))
    
    if process_call "$AUDIO_URL" "$CURRENT_CALL_ID" "$INDEX"; then
        SUCCESSFUL=$((SUCCESSFUL + 1))
    else
        FAILED=$((FAILED + 1))
    fi
    
    CURRENT_CALL_ID=$((CURRENT_CALL_ID + 1))
    
    # Add delay between calls to avoid rate limiting
    if [ "$INDEX" -lt "$TOTAL_CALLS" ]; then
        echo "Waiting 2 seconds before next call..." | tee -a "$LOG_FILE"
        sleep 2
        echo "" | tee -a "$LOG_FILE"
    fi
done

# Final summary
echo "" | tee -a "$LOG_FILE"
echo "╔═══════════════════════════════════════════╗" | tee -a "$LOG_FILE"
echo "║         Batch Processing Complete         ║" | tee -a "$LOG_FILE"
echo "╚═══════════════════════════════════════════╝" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Results:" | tee -a "$LOG_FILE"
echo "  Total Calls: $TOTAL_CALLS" | tee -a "$LOG_FILE"
echo -e "  ${GREEN}Successful: $SUCCESSFUL${NC}" | tee -a "$LOG_FILE"
echo -e "  ${RED}Failed: $FAILED${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Output directory: $OUTPUT_DIR" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}✓ All calls processed successfully!${NC}" | tee -a "$LOG_FILE"
    exit 0
else
    echo -e "${YELLOW}⚠ Some calls failed. Check the log for details.${NC}" | tee -a "$LOG_FILE"
    exit 1
fi


