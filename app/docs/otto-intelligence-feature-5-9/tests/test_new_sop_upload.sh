#!/bin/bash
set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
COMPANY_ID="test_company_123"

echo "========================================================================"
echo "TESTING NEW SOP UPLOAD WITH FIXED PIPELINE"
echo "========================================================================"
echo ""

# Create a test SOP document
TEST_FILE="test_support_sop.pdf"

echo "Creating test Support SOP document..."
python3 << PDFEOF
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    
    c = canvas.Canvas("$TEST_FILE", pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1*inch, height - 1*inch, "Customer Support Standard Operating Procedure")
    
    # Content
    c.setFont("Helvetica", 11)
    y = height - 1.5*inch
    
    content = [
        "",
        "1. INTRODUCTION",
        "This SOP defines the customer support process for handling inbound support calls.",
        "",
        "2. CALL ANSWERING PROTOCOL",
        "Support representatives must:",
        "- Answer within 3 rings",
        "- Greet customer warmly",
        "- State name and department",
        "- Ask how they can help",
        "",
        "Performance Metric: Average Answer Time",
        "Target: < 15 seconds",
        "Weight: 15%",
        "",
        "3. ISSUE TRIAGE",
        "Representatives must:",
        "- Listen actively to customer issue",
        "- Ask clarifying questions",
        "- Categorize issue (Technical/Billing/General)",
        "- Assess urgency level",
        "",
        "Performance Metric: Triage Accuracy Rate",
        "Target: 95%",
        "Weight: 20%",
        "",
        "4. RESOLUTION PROCESS",
        "- Check knowledge base for solutions",
        "- Apply documented fixes",
        "- Escalate if needed",
        "- Follow up with customer",
        "",
        "Performance Metric: First Call Resolution Rate",
        "Target: 80%",
        "Weight: 25%",
    ]
    
    for line in content:
        c.drawString(1*inch, y, line)
        y -= 0.2*inch
        if y < 1*inch:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - 1*inch
    
    c.save()
    print("✓ Created test SOP PDF")
    
except ImportError:
    print("reportlab not available, creating text file")
    with open("$TEST_FILE", "w") as f:
        f.write("""CUSTOMER SUPPORT STANDARD OPERATING PROCEDURE

1. INTRODUCTION
This SOP defines the customer support process for handling inbound support calls.

2. CALL ANSWERING PROTOCOL
Support representatives must:
- Answer within 3 rings
- Greet customer warmly
- State name and department
- Ask how they can help

Performance Metric: Average Answer Time
Target: < 15 seconds
Weight: 15%

3. ISSUE TRIAGE
Representatives must:
- Listen actively to customer issue
- Ask clarifying questions
- Categorize issue (Technical/Billing/General)
- Assess urgency level

Performance Metric: Triage Accuracy Rate
Target: 95%
Weight: 20%

4. RESOLUTION PROCESS
- Check knowledge base for solutions
- Apply documented fixes
- Escalate if needed
- Follow up with customer

Performance Metric: First Call Resolution Rate
Target: 80%
Weight: 25%
""")
PDFEOF

if [ ! -f "$TEST_FILE" ]; then
    echo "❌ Failed to create test file"
    exit 1
fi

echo "✓ Test file created: $TEST_FILE"
echo ""

# Upload SOP
echo "Uploading SOP document..."
UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/sop/documents/upload" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@$TEST_FILE" \
  -F "company_id=$COMPANY_ID" \
  -F "sop_name=Test Support SOP v1.0" \
  -F "target_role=support_rep")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

JOB_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")
SOP_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('sop_id', ''))")

if [ -z "$JOB_ID" ]; then
    echo "❌ Upload failed"
    exit 1
fi

echo ""
echo "✓ Upload initiated"
echo "  Job ID: $JOB_ID"
echo "  SOP ID: $SOP_ID"
echo ""

# Poll status
echo "Polling job status..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
    
    STATUS_RESPONSE=$(curl -s -X GET "$BASE_URL/api/v1/sop/documents/status/$JOB_ID" \
      -H "X-API-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"company_id\": \"$COMPANY_ID\"}")
    
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('progress', {}).get('percent', 0))")
    STEP=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('progress', {}).get('current_step', ''))")
    
    echo "  [$ATTEMPT/$MAX_ATTEMPTS] Status: $STATUS | Progress: $PROGRESS% | Step: $STEP"
    
    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo "✓ Processing completed!"
        echo ""
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        break
    elif [ "$STATUS" = "failed" ]; then
        echo ""
        echo "❌ Processing failed!"
        echo ""
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo ""
    echo "⚠ Timeout waiting for processing"
    exit 1
fi

echo ""
echo "========================================="
echo "Checking Milvus Indexing"
echo "========================================="

source venv/bin/activate && python3 << 'CHECKMILVUS'
from pymilvus import MilvusClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MilvusClient(
    uri=os.getenv("MILVUS_URI"),
    token=os.getenv("MILVUS_TOKEN")
)

collection_name = os.getenv("MILVUS_COLLECTION")

# Query for this specific SOP
import sys
sop_id = sys.argv[1] if len(sys.argv) > 1 else None
if not sop_id:
    print("No SOP ID provided")
    sys.exit(1)

results = client.query(
    collection_name=collection_name,
    filter=f'doc_id == "{sop_id}"',
    output_fields=["id", "corpus_type", "doc_id", "text_content"],
    limit=100
)

print(f"✓ Found {len(results)} vectors for SOP {sop_id}")

if len(results) > 0:
    # Group by corpus type
    by_corpus = {}
    for r in results:
        ct = r.get('corpus_type', 'unknown')
        by_corpus[ct] = by_corpus.get(ct, 0) + 1
    
    print("\nBy corpus type:")
    for ct, count in sorted(by_corpus.items()):
        print(f"  {ct}: {count}")
    
    print("\nSample vectors:")
    for r in results[:3]:
        print(f"  - {r['corpus_type']}: {r['text_content'][:80]}...")
else:
    print("❌ No vectors found in Milvus!")
    sys.exit(1)
CHECKMILVUS $SOP_ID

echo ""
echo "========================================================================"
echo "TEST COMPLETE"
echo "========================================================================"

# Cleanup
rm -f "$TEST_FILE"
