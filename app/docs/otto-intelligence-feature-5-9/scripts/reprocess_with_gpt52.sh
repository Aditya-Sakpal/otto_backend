#!/bin/bash
# Reprocess Calls Script - Regenerates summaries with new GPT-5.2 model
# Takes call IDs and audio URLs from analysis JSON and reprocesses them

set -e

# Configuration
API_KEY="${API_KEY:-5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
INPUT_JSON="./analysis_results/all_calls_analysis.json"
OUTPUT_DIR="./analysis_results/gpt52_reprocessed"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "==========================================="
echo "  Reprocess Calls with GPT-5.2 Model"
echo "==========================================="
echo ""
echo "Configuration:"
echo "  Base URL: $BASE_URL"
echo "  Input JSON: $INPUT_JSON"
echo "  Output Directory: $OUTPUT_DIR"
echo ""

# Extract call IDs and audio URLs from JSON
echo -e "${BLUE}Extracting call data from JSON...${NC}"
CALL_DATA=$(python3 << 'EOF'
import json
with open("./analysis_results/all_calls_analysis.json", 'r') as f:
    data = json.load(f)

calls = []
for item in data:
    if item.get("call_data") and item["call_data"].get("audio_url"):
        calls.append({
            "call_id": str(item["call_id"]),
            "audio_url": item["call_data"]["audio_url"]
        })

for call in calls:
    print(f"{call['call_id']}|{call['audio_url']}")
EOF
)

TOTAL_CALLS=$(echo "$CALL_DATA" | wc -l)
echo -e "${GREEN}✓ Found $TOTAL_CALLS calls to reprocess${NC}"
echo ""

# Initialize counters
SUCCESSFUL=0
FAILED=0

# Log file
LOG_FILE="$OUTPUT_DIR/reprocessing_$(date +%Y%m%d_%H%M%S).log"
echo "Log file: $LOG_FILE"
echo ""

# Function to process a single call
process_call() {
    local CALL_ID="$1"
    local AUDIO_URL="$2"
    local INDEX="$3"
    
    echo "═══════════════════════════════════════════" | tee -a "$LOG_FILE"
    echo "Reprocessing Call $INDEX/$TOTAL_CALLS" | tee -a "$LOG_FILE"
    echo "Call ID: $CALL_ID" | tee -a "$LOG_FILE"
    echo "═══════════════════════════════════════════" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # Submit call for reprocessing (will regenerate if exists)
    echo -e "${BLUE}[1/3] Submitting for reprocessing...${NC}" | tee -a "$LOG_FILE"
    
    PROCESS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/v1/call-processing/process" \
      -H "X-API-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "call_id": "'"$CALL_ID"'",
        "company_id": "gpt52_test",
        "audio_url": "'"$AUDIO_URL"'",
        "phone_number": "+14805551234"
      }')
    
    HTTP_STATUS=$(echo "$PROCESS_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
    RESPONSE_BODY=$(echo "$PROCESS_RESPONSE" | sed '/HTTP_STATUS/d')
    
    if [ "$HTTP_STATUS" != "202" ] && [ "$HTTP_STATUS" != "200" ]; then
        echo -e "${RED}✗ Failed to submit (HTTP $HTTP_STATUS)${NC}" | tee -a "$LOG_FILE"
        echo "Response: $RESPONSE_BODY" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        return 1
    fi
    
    JOB_ID=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)
    echo -e "${GREEN}✓ Submitted (Job ID: $JOB_ID)${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # Poll for completion
    echo -e "${BLUE}[2/3] Waiting for completion...${NC}" | tee -a "$LOG_FILE"
    MAX_ATTEMPTS=120  # 10 minutes max
    ATTEMPT=0
    STATUS="queued"
    
    while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ] && [ "$STATUS" != "completed" ] && [ "$STATUS" != "failed" ]; do
        sleep 5
        ATTEMPT=$((ATTEMPT + 1))
        
        STATUS_RESPONSE=$(curl -s "$BASE_URL/api/v1/call-processing/status/$JOB_ID" \
          -H "X-API-Key: $API_KEY")
        
        STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")
        
        if [ $((ATTEMPT % 6)) -eq 0 ]; then  # Print every 30 seconds
            echo -e "  Attempt $ATTEMPT/$MAX_ATTEMPTS - Status: ${YELLOW}$STATUS${NC}" | tee -a "$LOG_FILE"
        fi
    done
    
    echo "" | tee -a "$LOG_FILE"
    
    # Check final status
    if [ "$STATUS" = "completed" ]; then
        echo -e "${GREEN}✓ Processing completed!${NC}" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        
        # Fetch summary
        echo -e "${BLUE}[3/3] Fetching summary...${NC}" | tee -a "$LOG_FILE"
        SUMMARY_RESPONSE=$(curl -s "$BASE_URL/api/v1/call-processing/summary/$CALL_ID" \
          -H "X-API-Key: $API_KEY")
        
        # Check if summary was retrieved
        if echo "$SUMMARY_RESPONSE" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
            # Save summary to file
            SUMMARY_FILE="$OUTPUT_DIR/call_${CALL_ID}_new.json"
            echo "$SUMMARY_RESPONSE" | python3 -m json.tool > "$SUMMARY_FILE"
            echo -e "${GREEN}✓ Summary saved: $SUMMARY_FILE${NC}" | tee -a "$LOG_FILE"
            echo "" | tee -a "$LOG_FILE"
            return 0
        else
            echo -e "${RED}✗ Failed to retrieve summary${NC}" | tee -a "$LOG_FILE"
            echo "Response: $SUMMARY_RESPONSE" | tee -a "$LOG_FILE"
            echo "" | tee -a "$LOG_FILE"
            return 1
        fi
    elif [ "$STATUS" = "failed" ]; then
        echo -e "${RED}✗ Processing failed${NC}" | tee -a "$LOG_FILE"
        ERROR_MSG=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null || echo "Unknown error")
        echo "Error: $ERROR_MSG" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        return 1
    else
        echo -e "${RED}✗ Timeout (Status: $STATUS)${NC}" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"
        return 1
    fi
}

# Process each call
INDEX=1
while IFS='|' read -r CALL_ID AUDIO_URL; do
    if [ -n "$CALL_ID" ] && [ -n "$AUDIO_URL" ]; then
        if process_call "$CALL_ID" "$AUDIO_URL" "$INDEX"; then
            SUCCESSFUL=$((SUCCESSFUL + 1))
        else
            FAILED=$((FAILED + 1))
        fi
        
        INDEX=$((INDEX + 1))
        
        # Small delay between calls
        if [ "$INDEX" -le "$TOTAL_CALLS" ]; then
            sleep 2
        fi
    fi
done <<< "$CALL_DATA"

# Final summary
echo "" | tee -a "$LOG_FILE"
echo "╔═══════════════════════════════════════════╗" | tee -a "$LOG_FILE"
echo "║      Reprocessing Complete (GPT-5.2)      ║" | tee -a "$LOG_FILE"
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

if [ "$SUCCESSFUL" -gt 0 ]; then
    echo -e "${GREEN}✓ Now run: python scripts/compare_old_vs_new.py${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
fi

