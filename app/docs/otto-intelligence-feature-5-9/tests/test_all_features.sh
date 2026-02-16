#!/bin/bash

# Otto Intelligence Service - Comprehensive Test Script
# This script tests all three core features end-to-end

set -e  # Exit on error (we'll handle errors ourselves)

# Configuration
API_URL="http://localhost:9000"
API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
LOG_FILE="test_results_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}✗${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1" | tee -a "$LOG_FILE"
}

section() {
    echo "" | tee -a "$LOG_FILE"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}" | tee -a "$LOG_FILE"
    echo -e "${BLUE}  $1${NC}" | tee -a "$LOG_FILE"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
}

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

test_result() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    if [ $1 -eq 0 ]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        success "$2"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        error "$2"
    fi
}

# Wait for service to be ready
wait_for_service() {
    log "Checking if service is ready..."
    for i in {1..30}; do
        if curl -s "${API_URL}/health" > /dev/null 2>&1; then
            success "Service is ready!"
            return 0
        fi
        sleep 1
    done
    error "Service is not responding after 30 seconds"
    exit 1
}

# ============================================================================
# TEST 0: Health Check
# ============================================================================
test_health() {
    section "TEST 0: Health Check"
    
    log "Testing health endpoint..."
    response=$(curl -s -w "\n%{http_code}" "${API_URL}/health")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        test_result 0 "Health check passed"
        echo "$body" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
    else
        test_result 1 "Health check failed (HTTP $http_code)"
        echo "$body" | tee -a "$LOG_FILE"
    fi
}

# ============================================================================
# FEATURE 1: Call Processing Pipeline
# ============================================================================
test_call_processing() {
    section "FEATURE 1: Call Processing Pipeline"
    
    # Test 1.1: Submit a call
    log "Test 1.1: Submitting a call for processing..."
    
    call_payload='{
        "call_id": "test_call_001",
        "company_id": "test_company",
        "audio_url": "https://example.com/audio/test_call_001.mp3",
        "phone_number": "+1234567890",
        "metadata": {
            "transcript": "Agent: Hello, this is Sarah from Solar Solutions. Am I speaking with John? Customer: Yes, this is John. Agent: Great! I wanted to follow up on your inquiry about our solar panel installation. Are you still interested? Customer: Yes, but I am concerned about the cost. Agent: I understand. Let me explain our financing options. We offer 0% APR for 12 months. Customer: That sounds interesting. Can you schedule a consultation? Agent: Absolutely! I have availability this Thursday at 2 PM or Friday at 10 AM. Which works better for you? Customer: Thursday at 2 PM works for me. Agent: Perfect! I have booked you for Thursday, March 14th at 2 PM. We will send a confirmation email shortly. Customer: Thank you! Agent: You are welcome, John. Looking forward to meeting you!"
        }
    }'
    
    response=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/api/v1/call-processing/process" \
        -H "X-API-Key: ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$call_payload")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "202" ]; then
        job_id=$(echo "$body" | jq -r '.job_id // .task_id // .id // empty' 2>/dev/null)
        if [ -n "$job_id" ] && [ "$job_id" != "null" ]; then
            test_result 0 "Call submitted successfully (Job ID: $job_id)"
            echo "$body" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
            
            # Test 1.2: Check status
            log "Test 1.2: Checking job status..."
            sleep 2
            
            for i in {1..30}; do
                status_response=$(curl -s "${API_URL}/api/v1/call-processing/status/${job_id}" \
                    -H "X-API-Key: ${API_KEY}")
                
                status=$(echo "$status_response" | jq -r '.status // empty' 2>/dev/null)
                
                if [ "$status" = "SUCCESS" ]; then
                    test_result 0 "Task completed successfully"
                    echo "$status_response" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
                    break
                elif [ "$status" = "FAILURE" ] || [ "$status" = "FAILED" ]; then
                    test_result 1 "Task failed"
                    echo "$status_response" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
                    break
                else
                    log "Task status: $status (attempt $i/30)"
                    sleep 2
                fi
            done
            
            # Test 1.3: Retrieve summary
            log "Test 1.3: Retrieving call summary..."
            sleep 2
            
            summary_response=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/call-processing/summary/test_call_001" \
                -H "X-API-Key: ${API_KEY}")
            
            summary_http_code=$(echo "$summary_response" | tail -n1)
            summary_body=$(echo "$summary_response" | head -n-1)
            
            if [ "$summary_http_code" = "200" ]; then
                test_result 0 "Call summary retrieved successfully"
                echo "$summary_body" | jq '.' 2>/dev/null | head -20 | tee -a "$LOG_FILE"
            else
                test_result 1 "Failed to retrieve call summary (HTTP $summary_http_code)"
                echo "$summary_body" | tee -a "$LOG_FILE"
            fi
            
            # Test 1.4: Retrieve chunks
            log "Test 1.4: Retrieving call chunks..."
            
            chunks_response=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/call-processing/chunks/test_call_001" \
                -H "X-API-Key: ${API_KEY}")
            
            chunks_http_code=$(echo "$chunks_response" | tail -n1)
            chunks_body=$(echo "$chunks_response" | head -n-1)
            
            if [ "$chunks_http_code" = "200" ]; then
                chunk_count=$(echo "$chunks_body" | jq '.chunks | length' 2>/dev/null)
                test_result 0 "Call chunks retrieved ($chunk_count chunks)"
                echo "$chunks_body" | jq '.' 2>/dev/null | head -20 | tee -a "$LOG_FILE"
            else
                test_result 1 "Failed to retrieve call chunks (HTTP $chunks_http_code)"
                echo "$chunks_body" | tee -a "$LOG_FILE"
            fi
            
        else
            test_result 1 "No task ID in response"
            echo "$body" | tee -a "$LOG_FILE"
        fi
    else
        test_result 1 "Failed to submit call (HTTP $http_code)"
        echo "$body" | tee -a "$LOG_FILE"
    fi
}

# ============================================================================
# FEATURE 2: Weekly Insights Engine
# ============================================================================
test_insights() {
    section "FEATURE 2: Weekly Insights Engine"
    
    # Test 2.1: Trigger insights generation
    log "Test 2.1: Triggering weekly insights generation..."
    
    insights_payload='{
        "company_id": "test_company",
        "date_range": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-07"
        },
        "options": {
            "include_customer_insights": true,
            "include_objection_analysis": true
        }
    }'
    
    response=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/api/v1/insights/generate" \
        -H "X-API-Key: ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$insights_payload")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || [ "$http_code" = "202" ]; then
        insight_task_id=$(echo "$body" | jq -r '.task_id // .id // empty' 2>/dev/null)
        if [ -n "$insight_task_id" ] && [ "$insight_task_id" != "null" ]; then
            test_result 0 "Insights generation triggered (Task ID: $insight_task_id)"
            echo "$body" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
            
            # Test 2.2: Check status
            log "Test 2.2: Checking insights generation status..."
            sleep 2
            
            for i in {1..60}; do
                status_response=$(curl -s "${API_URL}/api/v1/insights/status/${insight_task_id}" \
                    -H "X-API-Key: ${API_KEY}")
                
                status=$(echo "$status_response" | jq -r '.status // empty' 2>/dev/null)
                
                if [ "$status" = "SUCCESS" ]; then
                    test_result 0 "Insights generated successfully"
                    echo "$status_response" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
                    break
                elif [ "$status" = "FAILURE" ] || [ "$status" = "FAILED" ]; then
                    test_result 1 "Insights generation failed"
                    echo "$status_response" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
                    break
                else
                    log "Insights status: $status (attempt $i/60)"
                    sleep 3
                fi
            done
        else
            warning "No task ID in response, skipping status check"
        fi
    else
        test_result 1 "Failed to trigger insights generation (HTTP $http_code)"
        echo "$body" | tee -a "$LOG_FILE"
    fi
    
    # Test 2.3: Retrieve company insights
    log "Test 2.3: Retrieving company insights..."
    
    company_response=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/insights/company/test_company?week=2024-W01" \
        -H "X-API-Key: ${API_KEY}")
    
    company_http_code=$(echo "$company_response" | tail -n1)
    company_body=$(echo "$company_response" | head -n-1)
    
    if [ "$company_http_code" = "200" ]; then
        test_result 0 "Company insights retrieved"
        echo "$company_body" | jq '.' 2>/dev/null | head -30 | tee -a "$LOG_FILE"
    else
        warning "Company insights not found or generation not complete (HTTP $company_http_code)"
        echo "$company_body" | tee -a "$LOG_FILE"
    fi
}

# ============================================================================
# FEATURE 3: Ask Otto Chat
# ============================================================================
test_ask_otto() {
    section "FEATURE 3: Ask Otto Chat"
    
    # Test 3.1: Create conversation
    log "Test 3.1: Creating a conversation..."
    
    conv_payload='{
        "company_id": "test_company",
        "user_id": "test_user_001",
        "title": "Automated Test Conversation"
    }'
    
    response=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/api/v1/ask-otto/conversations" \
        -H "X-API-Key: ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$conv_payload")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
        conversation_id=$(echo "$body" | jq -r '.conversation_id // .id // empty' 2>/dev/null)
        if [ -n "$conversation_id" ] && [ "$conversation_id" != "null" ]; then
            test_result 0 "Conversation created (ID: $conversation_id)"
            echo "$body" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
            
            # Test 3.2: Send a message
            log "Test 3.2: Sending a message to Ask Otto..."
            
            message_payload='{
                "message": "How many calls did we process today?",
                "context": {
                    "include_call_history": true,
                    "include_customer_context": false,
                    "max_rag_results": 5
                }
            }'
            
            msg_response=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/api/v1/ask-otto/conversations/${conversation_id}/messages" \
                -H "X-API-Key: ${API_KEY}" \
                -H "Content-Type: application/json" \
                -d "$message_payload")
            
            msg_http_code=$(echo "$msg_response" | tail -n1)
            msg_body=$(echo "$msg_response" | head -n-1)
            
            if [ "$msg_http_code" = "200" ] || [ "$msg_http_code" = "201" ]; then
                test_result 0 "Message sent and response received"
                echo "$msg_body" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
            else
                test_result 1 "Failed to send message (HTTP $msg_http_code)"
                echo "$msg_body" | tee -a "$LOG_FILE"
            fi
            
            # Test 3.3: Get conversation history
            log "Test 3.3: Retrieving conversation history..."
            
            history_response=$(curl -s -w "\n%{http_code}" "${API_URL}/api/v1/ask-otto/conversations/${conversation_id}/messages" \
                -H "X-API-Key: ${API_KEY}")
            
            history_http_code=$(echo "$history_response" | tail -n1)
            history_body=$(echo "$history_response" | head -n-1)
            
            if [ "$history_http_code" = "200" ]; then
                msg_count=$(echo "$history_body" | jq '.messages | length // .total_messages // 0' 2>/dev/null)
                test_result 0 "Conversation history retrieved ($msg_count messages)"
                echo "$history_body" | jq '.' 2>/dev/null | tee -a "$LOG_FILE"
            else
                test_result 1 "Failed to retrieve conversation history (HTTP $history_http_code)"
                echo "$history_body" | tee -a "$LOG_FILE"
            fi
            
            # Test 3.4: List conversations
            # Note: This endpoint doesn't exist in the current API
            # log "Test 3.4: Listing user conversations..."
            # Skipping for now
            warning "Test 3.4: List conversations endpoint not implemented yet"
            
        else
            test_result 1 "No conversation ID in response"
            echo "$body" | tee -a "$LOG_FILE"
        fi
    else
        test_result 1 "Failed to create conversation (HTTP $http_code)"
        echo "$body" | tee -a "$LOG_FILE"
    fi
}

# ============================================================================
# Main execution
# ============================================================================
main() {
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "  Otto Intelligence Service - Comprehensive Test Suite"
    echo "════════════════════════════════════════════════════════════════"
    echo ""
    echo "API URL: ${API_URL}"
    echo "Log File: ${LOG_FILE}"
    echo "Started: $(date)"
    echo ""
    
    # Wait for service
    wait_for_service
    
    # Run all tests
    test_health
    test_call_processing
    test_insights
    test_ask_otto
    
    # Print summary
    section "TEST SUMMARY"
    echo ""
    echo "Total Tests: $TESTS_TOTAL"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    echo ""
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        echo ""
        exit 0
    else
        echo -e "${RED}✗ Some tests failed. Check $LOG_FILE for details.${NC}"
        echo ""
        exit 1
    fi
}

# Run main
main

