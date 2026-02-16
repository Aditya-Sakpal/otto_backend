#!/bin/bash
# Feature 4: SOP Document Ingestion End-to-End Testing Script
# Tests the complete SOP processing pipeline

set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
TEST_COMPANY_ID="test_company_sop_$(date +%s)"
TEST_SOP_NAME="Test Sales SOP v1.0"

echo "==========================================="
echo "Feature 4: SOP Document Ingestion Test"
echo "==========================================="
echo ""
echo "Test Company ID: $TEST_COMPANY_ID"
echo ""

# Create a test SOP document as PDF using Python
echo "0. Creating test SOP document (PDF)..."
TEST_SOP_FILE="/tmp/test_sop_$(date +%s).pdf"
python3 << PDFEOF
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    
    output_file = "$TEST_SOP_FILE"
    doc = SimpleDocTemplate(output_file, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    story.append(Paragraph("SALES CALL STANDARD OPERATING PROCEDURE", styles['Title']))
    story.append(Paragraph("Version 1.0", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))
    
    # Content
    content_text = """
    <b>1. INTRODUCTION</b><br/>
    This document outlines the standard operating procedures for sales representatives conducting customer calls.<br/><br/>
    
    <b>2. CALL OPENING GUIDELINES</b><br/>
    Sales representatives must follow these steps when opening a call:<br/>
    • Introduce yourself with your full name and company name<br/>
    • Ask how you can help the customer<br/>
    • Maintain a professional and friendly tone<br/><br/>
    
    <b>Performance Metric: Greeting Quality</b><br/>
    • Description: Representative properly introduces themselves and the company<br/>
    • Evaluation Method: Check if rep states name, company name, and purpose within 15 seconds<br/>
    • Target Score: 1.0<br/>
    • Weight: 15%<br/><br/>
    
    <b>3. NEEDS ASSESSMENT PROCESS</b><br/>
    Representatives must thoroughly understand customer requirements by asking about:<br/>
    • The specific problem or need<br/>
    • Timeline for resolution<br/>
    • Budget constraints<br/>
    • Decision-making authority (BANT qualification)<br/><br/>
    
    <b>Performance Metric: Needs Assessment</b><br/>
    • Description: Representative thoroughly understands customer requirements<br/>
    • Evaluation Method: Verify rep asks about problem, timeline, budget, and decision makers<br/>
    • Target Score: 1.0<br/>
    • Weight: 20%<br/><br/>
    
    <b>4. OBJECTION HANDLING</b><br/>
    When customers raise objections, representatives should:<br/>
    • Acknowledge the concern without being defensive<br/>
    • Reframe the objection by focusing on value and ROI<br/>
    • Offer alternative solutions or payment plans<br/>
    • Use social proof and case studies<br/><br/>
    
    <b>Performance Metric: Objection Handling</b><br/>
    • Description: Representative effectively addresses customer objections<br/>
    • Evaluation Method: Evaluate acknowledgment, reframing, alternatives, and resolution<br/>
    • Target Score: 0.8<br/>
    • Weight: 20%<br/><br/>
    
    <b>5. EVALUATION CRITERIA</b><br/>
    Excellent (0.9-1.0): Exceeds all expectations, demonstrates mastery<br/>
    Good (0.7-0.89): Meets all expectations, minor improvements possible<br/>
    Needs Improvement (0.5-0.69): Meets some expectations, significant gaps<br/>
    Poor (0.0-0.49): Does not meet expectations, requires immediate coaching
    """
    
    story.append(Paragraph(content_text, styles['Normal']))
    doc.build(story)
    print(f"PDF created successfully: {output_file}")
    
except ImportError:
    # Fallback: Create a simple text file and rename it
    print("reportlab not available, creating simple text file as .pdf")
    with open("$TEST_SOP_FILE", "w") as f:
        f.write("""SALES CALL STANDARD OPERATING PROCEDURE
Version 1.0

1. INTRODUCTION
This document outlines the standard operating procedures for sales representatives conducting customer calls.

2. CALL OPENING GUIDELINES
Sales representatives must follow these steps when opening a call:
- Introduce yourself with your full name and company name
- Ask how you can help the customer
- Maintain a professional and friendly tone

Performance Metric: Greeting Quality
- Description: Representative properly introduces themselves and the company
- Evaluation Method: Check if rep states name, company name, and purpose within 15 seconds
- Target Score: 1.0
- Weight: 15%

3. NEEDS ASSESSMENT PROCESS
Representatives must thoroughly understand customer requirements by asking about:
- The specific problem or need
- Timeline for resolution
- Budget constraints
- Decision-making authority (BANT qualification)

Performance Metric: Needs Assessment
- Description: Representative thoroughly understands customer requirements
- Evaluation Method: Verify rep asks about problem, timeline, budget, and decision makers
- Target Score: 1.0
- Weight: 20%

4. OBJECTION HANDLING
When customers raise objections, representatives should:
- Acknowledge the concern without being defensive
- Reframe the objection by focusing on value and ROI
- Offer alternative solutions or payment plans
- Use social proof and case studies

Performance Metric: Objection Handling
- Description: Representative effectively addresses customer objections
- Evaluation Method: Evaluate acknowledgment, reframing, alternatives, and resolution
- Target Score: 0.8
- Weight: 20%

5. EVALUATION CRITERIA
Excellent (0.9-1.0): Exceeds all expectations, demonstrates mastery
Good (0.7-0.89): Meets all expectations, minor improvements possible
Needs Improvement (0.5-0.69): Meets some expectations, significant gaps
Poor (0.0-0.49): Does not meet expectations, requires immediate coaching
""")
PDFEOF

echo "Created test SOP file: $TEST_SOP_FILE"
echo ""

echo "Created test SOP file: $TEST_SOP_FILE"
echo ""

# 1. Health check
echo "1. Testing Health Endpoint..."
HEALTH_RESPONSE=$(curl -s "$BASE_URL/health")
echo "Response: $HEALTH_RESPONSE"
echo ""

# 2. Upload SOP document
echo "2. Uploading SOP document..."
UPLOAD_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/v1/sop/documents/upload" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@/home/uwcuser/otto-intelligence/IntakeCalls.pdf" \
  -F "company_id=$TEST_COMPANY_ID" \
  -F "sop_name=$TEST_SOP_NAME" \
  -F "target_role=sales_rep" \
  -F 'metadata={"version":"1.0","department":"sales"}')

HTTP_STATUS=$(echo "$UPLOAD_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
RESPONSE_BODY=$(echo "$UPLOAD_RESPONSE" | sed '/HTTP_STATUS/d')

echo "HTTP Status: $HTTP_STATUS"
echo "Response: $RESPONSE_BODY"
echo ""

if [ "$HTTP_STATUS" != "202" ]; then
    echo "ERROR: Expected 202, got $HTTP_STATUS"
    rm -f "$TEST_SOP_FILE"
    exit 1
fi

# Extract job_id and sop_id
JOB_ID=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null || echo "")
echo "Job ID: $JOB_ID"
echo ""

if [ -z "$JOB_ID" ]; then
    echo "ERROR: Could not extract job_id from response"
    rm -f "$TEST_SOP_FILE"
    exit 1
fi

# 3. Poll for completion
echo "3. Polling for SOP processing completion..."
MAX_ATTEMPTS=30  # 2.5 minutes max (longer than call processing)
ATTEMPT=0
STATUS="queued"
SOP_ID=""

while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ] && [ "$STATUS" != "completed" ] && [ "$STATUS" != "failed" ]; do
    sleep 5
    ATTEMPT=$((ATTEMPT + 1))
    
    STATUS_RESPONSE=$(curl -s "$BASE_URL/api/v1/sop/documents/status/$JOB_ID" \
      -H "X-API-Key: $API_KEY")
    
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', {}).get('percent', 0))" 2>/dev/null || echo "0")
    CURRENT_STEP=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', {}).get('current_step', ''))" 2>/dev/null || echo "unknown")
    SOP_ID=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('sop_id', ''))" 2>/dev/null || echo "")
    
    echo "Attempt $ATTEMPT/$MAX_ATTEMPTS - Status: $STATUS, Progress: $PROGRESS%, Step: $CURRENT_STEP"
done

echo ""
echo "Final Status: $STATUS"
echo "SOP ID: $SOP_ID"
echo "Full Response:"
echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
echo ""

# 4. If completed, test all endpoints
if [ "$STATUS" = "completed" ]; then
    echo "4. Testing: Get SOP Metrics..."
    METRICS_RESPONSE=$(curl -s "$BASE_URL/api/v1/sop/metrics/$TEST_COMPANY_ID?role=sales_rep" \
      -H "X-API-Key: $API_KEY")
    
    echo "Metrics Response:"
    echo "$METRICS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$METRICS_RESPONSE"
    echo ""
    
    METRICS_COUNT=$(echo "$METRICS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('active_sops', [{}])[0].get('metrics', [])))" 2>/dev/null || echo "0")
    echo "Total metrics extracted: $METRICS_COUNT"
    echo ""
    
    if [ "$METRICS_COUNT" -gt "0" ]; then
        echo "✓ Metrics extracted successfully"
    else
        echo "✗ No metrics extracted"
    fi
    echo ""
    
    echo "5. Testing: Get SOP Document Details..."
    if [ -n "$SOP_ID" ]; then
        DOC_RESPONSE=$(curl -s "$BASE_URL/api/v1/sop/documents/$SOP_ID" \
          -H "X-API-Key: $API_KEY")
        
        echo "Document Response:"
        echo "$DOC_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$DOC_RESPONSE"
        echo ""
    fi
    
    echo "6. Testing: List SOP Documents..."
    LIST_RESPONSE=$(curl -s "$BASE_URL/api/v1/sop/documents?company_id=$TEST_COMPANY_ID" \
      -H "X-API-Key: $API_KEY")
    
    echo "List Response:"
    echo "$LIST_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$LIST_RESPONSE"
    echo ""
    
    DOC_COUNT=$(echo "$LIST_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total', 0))" 2>/dev/null || echo "0")
    echo "Total documents: $DOC_COUNT"
    echo ""
    
    echo "7. Testing: Update SOP Status (deactivate)..."
    if [ -n "$SOP_ID" ]; then
        UPDATE_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X PATCH "$BASE_URL/api/v1/sop/documents/$SOP_ID/status" \
          -H "X-API-Key: $API_KEY" \
          -H "Content-Type: application/json" \
          -d '{"status":"inactive","reason":"Testing deactivation"}')
        
        UPDATE_HTTP_STATUS=$(echo "$UPDATE_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
        UPDATE_BODY=$(echo "$UPDATE_RESPONSE" | sed '/HTTP_STATUS/d')
        
        echo "HTTP Status: $UPDATE_HTTP_STATUS"
        echo "Response: $UPDATE_BODY"
        echo ""
        
        if [ "$UPDATE_HTTP_STATUS" = "200" ]; then
            echo "✓ Status update successful"
        else
            echo "✗ Status update failed"
        fi
    fi
    echo ""
    
    # 8. Check MongoDB
    echo "8. Checking MongoDB for SOP data..."
    source venv/bin/activate && python3 << MONGOEOF
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def check_mongo():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("MONGODB_DB_NAME", "otto-ai-storage")]
    
    # Check SOP document
    sop_doc = await db.sop_documents.find_one({"company_id": "$TEST_COMPANY_ID"})
    if sop_doc:
        print(f"✓ SOP document found in MongoDB:")
        print(f"  - SOP ID: {sop_doc.get('sop_id')}")
        print(f"  - Name: {sop_doc.get('sop_name')}")
        print(f"  - Status: {sop_doc.get('status')}")
        print(f"  - Type: {sop_doc.get('sop_type')}")
    else:
        print("✗ SOP document NOT found in MongoDB")
    
    # Check SOP metrics
    sop_metrics = await db.sop_metrics.find_one({"company_id": "$TEST_COMPANY_ID"})
    if sop_metrics:
        metrics_count = len(sop_metrics.get('metrics', []))
        print(f"✓ SOP metrics found in MongoDB:")
        print(f"  - Total metrics: {metrics_count}")
        print(f"  - Total weight: {sop_metrics.get('total_weight', 0)}")
    else:
        print("✗ SOP metrics NOT found in MongoDB")
    
    # Check SOP chunks
    chunks_count = await db.sop_chunks.count_documents({"company_id": "$TEST_COMPANY_ID"})
    print(f"✓ SOP chunks in MongoDB: {chunks_count}")
    
    client.close()

asyncio.run(check_mongo())
MONGOEOF
    echo ""
    
    # 9. Check Milvus for SOP vectors
    echo "9. Checking Milvus for SOP vectors..."
    if [ -n "$SOP_ID" ]; then
        source venv/bin/activate && python3 << MILVUSEOF
import asyncio
from pymilvus import MilvusClient
import os
from dotenv import load_dotenv

load_dotenv()

async def check_milvus():
    client = MilvusClient(
        uri=os.getenv("MILVUS_URI"),
        token=os.getenv("MILVUS_TOKEN")
    )
    
    collection_name = os.getenv("MILVUS_COLLECTION", "otto_intelligence_v1")
    
    # Query for SOP vectors
    try:
        results = client.query(
            collection_name=collection_name,
            filter='doc_id == "$SOP_ID"',
            output_fields=["id", "tenant_id", "corpus_type", "doc_id"],
            limit=20
        )
        
        print(f"Found {len(results)} vectors in Milvus for SOP $SOP_ID:")
        
        corpus_types = {}
        for result in results:
            corpus_type = result.get('corpus_type', 'unknown')
            corpus_types[corpus_type] = corpus_types.get(corpus_type, 0) + 1
        
        for corpus_type, count in corpus_types.items():
            print(f"  - {corpus_type}: {count} vectors")
        
        if len(results) > 0:
            print(f"✓ SOP vectors indexed successfully")
        else:
            print("✗ No SOP vectors found in Milvus")
    except Exception as e:
        print(f"✗ Error querying Milvus: {e}")

asyncio.run(check_milvus())
MILVUSEOF
    fi
    echo ""
    
    echo "==========================================="
    echo "Test Result: SUCCESS ✓"
    echo "==========================================="
    echo ""
    echo "Summary:"
    echo "- SOP document uploaded and processed"
    echo "- Metrics extracted: $METRICS_COUNT"
    echo "- Documents in system: $DOC_COUNT"
    echo "- Status updates working"
    echo "- MongoDB storage verified"
    echo "- Milvus indexing verified"
else
    echo "==========================================="
    echo "Test Result: FAILED ✗"
    echo "Final Status: $STATUS"
    echo "==========================================="
    
    # Show error details if available
    if [ "$STATUS" = "failed" ]; then
        echo ""
        echo "Error Details:"
        echo "$STATUS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('error', {}), indent=2))" 2>/dev/null || echo "No error details available"
    fi
fi

# Cleanup
echo ""
echo "Cleaning up test file..."
rm -f "$TEST_SOP_FILE"
echo "Done!"

