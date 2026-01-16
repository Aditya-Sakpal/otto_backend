# Dashboard API Mapping

This document maps each frontend dashboard section to the appropriate backend APIs based on the screenshots provided.

## 📊 Section 1: Dashboard Overview

**Frontend Display:**
- Booking Rate: 65%
- Total Leads: 56
- Qualified Leads: 34
- Booked Appointments: 22
- Booking Rate Improvement graph (line chart showing trend over time)

**Recommended APIs:**

### Primary Endpoints:
1. **GET `/api/v1/metrics/exec/company-overview`**
   - **Purpose**: Get total leads, qualified leads, booked appointments, total calls, missed calls
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `start_date` (optional): YYYY-MM-DD format, defaults to 30 days ago
     - `end_date` (optional): YYYY-MM-DD format, defaults to today
   - **Response Fields**:
     - `total_leads`: Total number of leads
     - `qualified_leads`: Number of qualified leads
     - `total_appointments`: Number of booked appointments
     - `total_calls`: Total number of calls
     - `missed_calls`: Number of missed calls
     - `conversion_rate`: Conversion rate percentage
     - `total_revenue`: Total revenue

2. **GET `/api/v1/metrics/booking-rate-improvement`**
   - **Purpose**: Get booking rate improvement data for the graph
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `start_date` (optional): Start of current period, defaults to 30 days ago
     - `end_date` (optional): End of current period, defaults to today
   - **Response Fields**:
     - `current_rate`: Current booking rate percentage
     - `previous_rate`: Previous period booking rate percentage
     - `improvement_percentage`: Improvement percentage
     - `current_bookings`: Number of bookings in current period
     - `previous_bookings`: Number of bookings in previous period
     - `current_qualified`: Number of qualified leads in current period
     - `previous_qualified`: Number of qualified leads in previous period

### Optional Endpoints:
3. **GET `/api/v1/metrics/bookings/summary`**
   - **Purpose**: Get detailed bookings summary (total, confirmed, pending, cancelled)
   - **Query Parameters**: Same as above
   - **Response Fields**:
     - `total_bookings`: Total bookings
     - `confirmed_bookings`: Confirmed bookings
     - `pending_bookings`: Pending bookings
     - `cancelled_bookings`: Cancelled bookings
     - `bookings_today`: Bookings created today

---

## 📋 Section 2: Unbooked Appointments Card

**Frontend Display:**
- Table showing unbooked appointments with:
  - Name (with audio playback icon)
  - Phone Number
  - Reason for Not Booking
  - Last Spoken With (date)
  - Details (full explanation)

**Recommended APIs:**

### Primary Endpoint:
1. **GET `/api/v1/metrics/leads/unbooked`**
   - **Purpose**: Get unbooked leads with detailed information
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `start_date` (optional): YYYY-MM-DD format
     - `end_date` (optional): YYYY-MM-DD format
     - `limit` (optional): Maximum number of leads (default: 20, max: 100)
   - **Response Fields**:
     - `total_unbooked`: Total number of unbooked leads
     - `qualified_unbooked`: Number of qualified unbooked leads
     - `avg_days_unbooked`: Average days unbooked
     - `leads`: Array of lead objects with:
       - `id`: Lead UUID
       - `status`: Lead status
       - `contact_card`: Contact card object with:
         - `first_name`, `last_name`
         - `primary_phone`, `secondary_phone`
         - `email`
       - `created_at`: Creation timestamp
       - `last_call_date`: Date of last call (if available)

### Alternative Endpoint:
2. **GET `/api/v1/leads?status=qualified_unbooked`**
   - **Purpose**: Alternative endpoint to get unbooked leads
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `status`: "qualified_unbooked"
     - `limit` (optional): Maximum number of leads
   - **Response**: Array of Lead objects

**Note**: To get the "Reason for Not Booking" and "Details", you may need to:
- Check the lead's `status` field for reason
- Query call analyses for the lead to get objection details
- Use `/api/v1/analytics/objection-calls?objection={type}` to get objection details

---

## 🎯 Section 3: Top Objections

**Frontend Display:**
- List of objections with horizontal progress bars showing frequency
- Objections shown: Service unavailability, Unhappy existing customer, Scheduling Conflicts, etc.

**Recommended APIs:**

### Primary Endpoint:
1. **GET `/api/v1/metrics/objections/top`**
   - **Purpose**: Get top objections with counts and percentages
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `start_date` (optional): YYYY-MM-DD format
     - `end_date` (optional): YYYY-MM-DD format
     - `limit` (optional): Number of top objections (default: 5, max: 20)
   - **Response Fields**:
     - `objections`: Array of objection objects with:
       - `objection_type`: Type of objection (price, timing, authority, need, competitor, other)
       - `count`: Number of times this objection appeared
       - `percentage`: Percentage of total objections

### Alternative Endpoint:
2. **GET `/api/v1/analytics/top-objections`**
   - **Purpose**: Alternative endpoint for top objections
   - **Query Parameters**:
     - `company_id` (required): UUID
   - **Response**: Array of objection objects with `objection_type` and `count`

### Optional Endpoint:
3. **GET `/api/v1/metrics/objections/summary`**
   - **Purpose**: Get objections summary statistics
   - **Query Parameters**: Same as primary endpoint
   - **Response Fields**:
     - `total_objections`: Total number of objections
     - `unique_types`: Number of unique objection types
     - `top_objection`: Most common objection
     - `breakdown`: Breakdown by objection type

---

## 📥 Section 4: Queued Leads Ready for Booking

**Frontend Display:**
- Table showing leads ready for booking with:
  - Name
  - Phone Number
  - Service Requested
  - Availability
  - Address
  - Details (captured by Otto AI)

**Recommended APIs:**

### Primary Endpoint:
1. **GET `/api/v1/metrics/csr/auto-queued-leads`**
   - **Purpose**: Get auto-queued leads prioritized by status (hot > warm > new)
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `start_date` (optional): YYYY-MM-DD format
     - `end_date` (optional): YYYY-MM-DD format
     - `limit` (optional): Maximum number of leads (default: 20, max: 100)
   - **Response Fields**:
     - `total`: Total number of leads
     - `hot_leads`: Number of hot leads
     - `warm_leads`: Number of warm leads
     - `new_leads`: Number of new leads
     - `leads`: Array of lead objects with:
       - `id`: Lead UUID
       - `status`: Lead status (hot, warm, new)
       - `contact_card`: Contact card object with name, phone, email, address
       - `deal_size`: Deal size if available
       - `created_at`: Creation timestamp

**Note**: The leads are automatically prioritized by status (hot > warm > new) and sorted by creation date (newest first).

---

## ⚡ Section 5: Leads by Priority

**Frontend Display:**
- Table showing leads with:
  - Name
  - Phone Number
  - Reason Not Booked
  - Last Touched (date)
  - Urgency (High/Medium/Low badge)
  - Objection & Response (detailed explanation)

**Recommended APIs:**

### Primary Endpoint:
1. **GET `/api/v1/leads?sort=priority`**
   - **Purpose**: Get leads sorted by priority/urgency
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `sort`: "priority" (required for this view)
     - `limit` (optional): Maximum number of leads (default: 100)
   - **Response**: Array of Lead objects sorted by priority (hot > warm > new > others)
   - **Lead Object Fields**:
     - `id`: Lead UUID
     - `status`: Lead status (determines urgency)
     - `contact_card`: Contact card with name, phone
     - `created_at`: Creation timestamp (for "Last Touched")
     - `deal_status`: Deal status
     - `priority`: Priority level (if available)

### For Objection & Response Column:
2. **GET `/api/v1/analytics/objection-calls`**
   - **Purpose**: Get calls with specific objections (for "Objection & Response" column)
   - **Query Parameters**:
     - `company_id` (required): UUID
     - `objection` (required): Objection type (e.g., "price", "timing", "authority")
     - `owner_id` (optional): Filter by CSR/owner UUID
   - **Response**: Array of call objects with:
     - `call_id`: Call UUID
     - `contact_card`: Contact card object
     - `audio_url`: URL to call audio recording
     - `qualification_status`: Qualification status from analysis
     - `booking_status`: Booking status from analysis
     - `objections`: Array of objections raised in the call

**Note**: To get the full "Objection & Response" details, you may need to:
1. Query `/api/v1/analytics/objection-calls` for each objection type
2. Match calls to leads by `contact_card_id`
3. Extract objection details and responses from call analyses

---

## 🔧 Implementation Notes

### Date Range Handling
- All metrics endpoints support `start_date` and `end_date` query parameters
- If not provided, defaults to last 30 days
- Date format: `YYYY-MM-DD` (e.g., "2025-01-15")

### Error Handling
- All endpoints return appropriate HTTP status codes
- 400: Bad Request (missing/invalid parameters)
- 404: Not Found (resource doesn't exist)
- 500: Internal Server Error (server-side error)

### Authentication
- All endpoints require authentication (JWT token)
- Some endpoints have role-based access control (RBAC)
- Check endpoint documentation for required roles

### Response Format
- Most endpoints return JSON objects
- Some endpoints return arrays directly
- All timestamps are in ISO 8601 format

---

## 📝 Testing

A test script is available at `backend/test_dashboard_apis.py` that tests all the above endpoints with sample data.

To run the tests:
```bash
cd backend
python test_dashboard_apis.py
```

Make sure the backend server is running on `http://localhost:8001` before running the tests.

---

## 🎯 Quick Reference

| Frontend Section | Primary API | Alternative API |
|----------------|-------------|-----------------|
| Dashboard Overview | `/api/v1/metrics/exec/company-overview` | `/api/v1/metrics/bookings/summary` |
| Booking Rate Graph | `/api/v1/metrics/booking-rate-improvement` | - |
| Unbooked Appointments | `/api/v1/metrics/leads/unbooked` | `/api/v1/leads?status=qualified_unbooked` |
| Top Objections | `/api/v1/metrics/objections/top` | `/api/v1/analytics/top-objections` |
| Queued Leads | `/api/v1/metrics/csr/auto-queued-leads` | - |
| Leads by Priority | `/api/v1/leads?sort=priority` | - |
| Objection Details | `/api/v1/analytics/objection-calls` | - |
